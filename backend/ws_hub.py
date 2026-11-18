"""Single-commit CASE_EVENT and TRANSIENT_PULSE WebSocket hub for ThinkTank v4.0."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any, Callable, Optional

try:
    from .governance import role_usage
    from .ledger_domain import build_interaction_graph, compute_origin_counts
except ImportError:
    from governance import role_usage
    from ledger_domain import build_interaction_graph, compute_origin_counts


class WebSocketHub:
    SEND_TIMEOUT_SECONDS = 1.0

    def __init__(self, store: Any) -> None:
        self.store = store
        self.active_connections: dict[Any, str] = {}
        self.lock = asyncio.Lock()

    async def _send(self, websocket: Any, message: dict[str, Any]) -> None:
        await asyncio.wait_for(websocket.send_json(message), timeout=self.SEND_TIMEOUT_SECONDS)

    def disconnect(self, websocket: Any) -> None:
        self.active_connections.pop(websocket, None)

    @staticmethod
    def _event_to_wire(event: dict[str, Any]) -> dict[str, Any]:
        payload = dict(event["payload"])
        payload.update({
            "convId": event["conversation_id"],
            "generation": event["generation"],
            "seq": event["seq"],
            "eventId": event["event_id"],
        })
        return payload

    async def connect(
        self,
        websocket: Any,
        conv_id: str,
        generation: Optional[str],
        after_seq: Optional[int],
        build_snapshot_fn: Callable[[str], dict[str, Any]],
    ) -> None:
        await websocket.accept()
        async with self.lock:
            self.active_connections[websocket] = conv_id
            cursor = self.store.cursor(conv_id)
            try:
                if generation is not None and after_seq is not None:
                    result = self.store.replay(conv_id, generation, after_seq)
                    if result["status"] == "replay":
                        await self._send(websocket, {
                            "type": "SYNC_REPLAY",
                            "convId": conv_id,
                            "generation": result["generation"],
                            "seq": result["seq"],
                            "events": [self._event_to_wire(ev) for ev in result["events"]],
                        })
                        return
                snap = build_snapshot_fn(conv_id)
                cursor = self.store.cursor(conv_id)
                await self._send(websocket, {
                    "type": "SYNC_SNAPSHOT",
                    "convId": conv_id,
                    "parentConvId": snap["parentConvId"],
                    "workspaceUri": snap.get("workspaceUri"),
                    "hasSession": snap["hasSession"],
                    "isClosed": snap["isClosed"],
                    "conversationsList": snap["conversationsList"],
                    "generation": cursor["generation"],
                    "seq": cursor["seq"],
                    "updatedAt": cursor["updated_at"],
                    "updatedAtMs": snap["updatedAtMs"],
                    "snapshot": snap,
                })
            except Exception:
                self.disconnect(websocket)
                try:
                    await websocket.close()
                except Exception:
                    pass
                raise

    async def commit_and_broadcast(
        self,
        conv_id: str,
        conv: dict[str, Any],
        event_kind: str,
        changed_slices: list[str] | tuple[str, ...],
        *,
        extra: Optional[dict[str, Any]] = None,
        event_id: Optional[str] = None,
        conversations_list: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        now_epoch_ms = int(time.time() * 1000)
        conv["updatedAtMs"] = now_epoch_ms
        conv["updated_at"] = now_epoch_ms / 1000.0
        eff_event_id = event_id or str(uuid.uuid4())
        slices = list(dict.fromkeys(changed_slices))
        payload: dict[str, Any] = {
            "type": "CASE_EVENT",
            "eventKind": event_kind,
            "changedSlices": slices,
            "convId": conv_id,
            "updatedAtMs": now_epoch_ms,
            "thinkTank": conv.get("thinkTank"),
            "agents": conv.get("agents", []),
            "subtasks": conv.get("subtasks", []),
            "fileLocks": conv.get("fileLocks", []),
            "findings": conv.get("findings", []),
            "messages": conv.get("messages", []),
            "interactions": conv.get("interactions", []),
            "collaborations": conv.get("collaborations", []),
            "graph": build_interaction_graph(conv),
            "proposal": conv.get("proposal"),
            "review": conv.get("review"),
            "originCounts": compute_origin_counts(conv),
            "roleUsage": role_usage(conv.get("messages", [])),
            "closureReceipt": (conv.get("thinkTank") or {}).get("closureReceipt"),
        }
        if conversations_list is not None:
            payload["conversationsList"] = conversations_list
        if "telemetry" in slices:
            payload["telemetry"] = conv.get("telemetry")
        if extra:
            payload.update(extra)

        async with self.lock:
            envelope = self.store.commit(
                conversation_id=conv_id,
                event_id=eff_event_id,
                event_type="CASE_EVENT",
                payload=payload,
                snapshot=conv,
                source="api",
            )
            if envelope["duplicate"]:
                return envelope
            wire = self._event_to_wire(envelope)
            for connection, sub_conv in list(self.active_connections.items()):
                if sub_conv != conv_id:
                    continue
                try:
                    await self._send(connection, wire)
                except Exception:
                    self.disconnect(connection)
            return envelope

    async def broadcast_pulse(self, conv_id: str, pulse_kind: str, extra: Optional[dict[str, Any]] = None) -> None:
        if not conv_id:
            return
        message: dict[str, Any] = {
            "type": "TRANSIENT_PULSE",
            "pulseKind": pulse_kind,
            "convId": conv_id,
            "updatedAtMs": int(time.time() * 1000),
        }
        if extra:
            message.update(extra)
        async with self.lock:
            for connection, sub_conv in list(self.active_connections.items()):
                if sub_conv != conv_id:
                    continue
                try:
                    await self._send(connection, message)
                except Exception:
                    self.disconnect(connection)

    async def handle_client_message(self, websocket: Any, raw_message: str) -> None:
        try:
            msg = json.loads(raw_message)
        except (TypeError, json.JSONDecodeError):
            return
        if isinstance(msg, dict) and msg.get("type") == "SYNC_PING":
            await self._send(websocket, {"type": "SYNC_PONG", "clientTime": msg.get("clientTime"), "serverTime": time.time()})
