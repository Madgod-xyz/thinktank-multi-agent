"""Durable, per-conversation event cursors and snapshots for ThinkTank sync.

This module deliberately uses only the Python standard library so the installed
FastAPI backend can use it without adding a runtime dependency.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional


class SyncEventStore:
    """Atomically persist each conversation snapshot and its ordered events."""

    def __init__(self, db_path: str, retention: int = 150) -> None:
        if retention < 1:
            raise ValueError("retention must be at least 1")
        self.db_path = str(db_path)
        self.retention = int(retention)
        self._lock = threading.RLock()
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        # One connection is shared by the synchronous FastAPI handlers and
        # serialized by _lock. WAL lets readers in other processes proceed.
        self._db = sqlite3.connect(
            self.db_path, timeout=10.0, isolation_level=None, check_same_thread=False
        )
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=NORMAL")
        self._db.execute("PRAGMA busy_timeout=5000")
        self._db.execute("PRAGMA temp_store=MEMORY")
        self._db.execute("PRAGMA foreign_keys=ON")
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                conversation_id TEXT PRIMARY KEY,
                generation TEXT NOT NULL,
                seq INTEGER NOT NULL DEFAULT 0,
                snapshot_json TEXT NOT NULL DEFAULT '{}',
                updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                conversation_id TEXT NOT NULL,
                seq INTEGER NOT NULL,
                event_id TEXT NOT NULL,
                generation TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                source TEXT NOT NULL,
                created_at REAL NOT NULL,
                PRIMARY KEY (conversation_id, seq),
                UNIQUE (conversation_id, event_id),
                FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id)
                    ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS events_cursor_idx
                ON events (conversation_id, seq);
            """
        )

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _decode_event(row: sqlite3.Row, duplicate: bool = False) -> dict[str, Any]:
        return {
            "conversation_id": row["conversation_id"],
            "generation": row["generation"],
            "seq": row["seq"],
            "event_id": row["event_id"],
            "type": row["event_type"],
            "payload": json.loads(row["payload_json"]),
            "source": row["source"],
            "created_at": row["created_at"],
            "duplicate": duplicate,
        }

    def _ensure_conversation(self, conversation_id: str) -> sqlite3.Row:
        if not isinstance(conversation_id, str) or not conversation_id.strip():
            raise ValueError("conversation_id must be a non-empty string")
        row = self._db.execute(
            "SELECT * FROM conversations WHERE conversation_id = ?", (conversation_id,)
        ).fetchone()
        if row is None:
            now = time.time()
            self._db.execute(
                "INSERT INTO conversations (conversation_id, generation, seq, snapshot_json, updated_at) "
                "VALUES (?, ?, 0, '{}', ?)",
                (conversation_id, str(uuid.uuid4()), now),
            )
            row = self._db.execute(
                "SELECT * FROM conversations WHERE conversation_id = ?", (conversation_id,)
            ).fetchone()
        return row

    def cursor(self, conversation_id: str) -> dict[str, Any]:
        with self._lock:
            row = self._ensure_conversation(conversation_id)
            latest = self._db.execute(
                "SELECT event_type FROM events WHERE conversation_id = ? ORDER BY seq DESC LIMIT 1",
                (conversation_id,),
            ).fetchone()
            return {
                "conversation_id": row["conversation_id"],
                "generation": row["generation"],
                "seq": row["seq"],
                "updated_at": row["updated_at"],
                "last_event_type": latest["event_type"] if latest else None,
            }

    def snapshot(self, conversation_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            row = self._db.execute(
                "SELECT snapshot_json FROM conversations WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
            return json.loads(row["snapshot_json"]) if row else None

    def find_event_id(self, event_id: str) -> Optional[dict[str, Any]]:
        """Find an event by its globally random HTTP idempotency key."""
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM events WHERE event_id = ? ORDER BY created_at DESC LIMIT 1",
                (event_id,),
            ).fetchone()
            return self._decode_event(row, duplicate=True) if row else None

    def commit(
        self,
        *,
        conversation_id: str,
        event_id: str,
        event_type: str,
        payload: dict[str, Any],
        snapshot: dict[str, Any],
        source: str = "backend",
    ) -> dict[str, Any]:
        if not event_id or not event_type:
            raise ValueError("event_id and event_type must be non-empty")
        payload_json = self._json(payload)
        snapshot_json = self._json(snapshot)
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                conv = self._ensure_conversation(conversation_id)
                existing = self._db.execute(
                    "SELECT * FROM events WHERE conversation_id = ? AND event_id = ?",
                    (conversation_id, event_id),
                ).fetchone()
                if existing is not None:
                    self._db.execute("COMMIT")
                    return self._decode_event(existing, duplicate=True)

                seq = conv["seq"] + 1
                now = time.time()
                self._db.execute(
                    "UPDATE conversations SET seq = ?, snapshot_json = ?, updated_at = ? WHERE conversation_id = ?",
                    (seq, snapshot_json, now, conversation_id),
                )
                self._db.execute(
                    "INSERT INTO events (conversation_id, seq, event_id, generation, event_type, payload_json, source, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (conversation_id, seq, event_id, conv["generation"], event_type, payload_json, source, now),
                )
                self._db.execute(
                    "DELETE FROM events WHERE conversation_id = ? AND seq <= ?",
                    (conversation_id, seq - self.retention),
                )
                row = self._db.execute(
                    "SELECT * FROM events WHERE conversation_id = ? AND seq = ?",
                    (conversation_id, seq),
                ).fetchone()
                self._db.execute("COMMIT")
                return self._decode_event(row)
            except BaseException:
                self._db.execute("ROLLBACK")
                raise

    def replay(self, conversation_id: str, generation: str, after_seq: int) -> dict[str, Any]:
        if not isinstance(after_seq, int) or after_seq < 0:
            raise ValueError("after_seq must be a non-negative integer")
        with self._lock:
            conv = self._db.execute(
                "SELECT generation, seq FROM conversations WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
            if conv is None:
                return {"status": "snapshot_required", "events": []}
            bounds = self._db.execute(
                "SELECT MIN(seq) AS first_seq FROM events WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
            first_seq = bounds["first_seq"]
            if (
                generation != conv["generation"]
                or after_seq > conv["seq"]
                or (first_seq is not None and after_seq < first_seq - 1)
            ):
                return {"status": "snapshot_required", "events": []}
            rows = self._db.execute(
                "SELECT * FROM events WHERE conversation_id = ? AND seq > ? ORDER BY seq",
                (conversation_id, after_seq),
            ).fetchall()
            return {
                "status": "replay",
                "generation": conv["generation"],
                "seq": conv["seq"],
                "events": [self._decode_event(row) for row in rows],
            }

    def load_conversations(self) -> dict[str, dict[str, Any]]:
        """Return persisted snapshots keyed by conversation ID."""
        with self._lock:
            rows = self._db.execute(
                "SELECT conversation_id, generation, seq, snapshot_json, updated_at FROM conversations ORDER BY conversation_id"
            ).fetchall()
            return {
                row["conversation_id"]: {
                    "generation": row["generation"],
                    "seq": row["seq"],
                    "snapshot": json.loads(row["snapshot_json"]),
                    "updated_at": row["updated_at"],
                }
                for row in rows
            }

    @staticmethod
    def compact_tool_entry(entry: Any) -> Any:
        if not isinstance(entry, dict):
            return entry
        compact = dict(entry)
        for field in ("output", "error"):
            val = compact.get(field)
            if isinstance(val, str) and len(val) > 240:
                compact[field] = val[:240]
        raw_args = compact.get("args")
        if isinstance(raw_args, dict):
            trimmed: dict[str, Any] = {}
            for idx, (k, v) in enumerate(raw_args.items()):
                if idx >= 8:
                    break
                if isinstance(v, str) and len(v) > 160:
                    trimmed[k] = v[:160]
                elif isinstance(v, (list, dict)):
                    s = json.dumps(v, ensure_ascii=False, separators=(",", ":"))
                    trimmed[k] = s[:160] if len(s) > 160 else v
                else:
                    trimmed[k] = v
            compact["args"] = trimmed
        return compact

    @classmethod
    def compact_telemetry_store(cls, telemetry: Any, *, max_calls: int = 25) -> dict[str, Any]:
        if not isinstance(telemetry, dict):
            return {"toolCalls": [], "terminalLogs": [], "backgroundTasks": []}
        out = dict(telemetry)
        calls = out.get("toolCalls")
        if isinstance(calls, list):
            out["toolCalls"] = [cls.compact_tool_entry(c) for c in calls[:max_calls]]
        logs = out.get("terminalLogs")
        if isinstance(logs, list):
            trimmed_logs = []
            for item in logs[:max_calls]:
                if isinstance(item, dict) and isinstance(item.get("output"), str) and len(item["output"]) > 400:
                    trimmed_logs.append({**item, "output": item["output"][:400]})
                else:
                    trimmed_logs.append(item)
            out["terminalLogs"] = trimmed_logs
        return out

    def save_snapshot_only(self, conversation_id: str, snapshot: dict[str, Any]) -> None:
        """Persist conversation snapshot and updated_at without creating an events row or advancing seq."""
        snapshot_json = self._json(snapshot)
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                self._ensure_conversation(conversation_id)
                now = time.time()
                self._db.execute(
                    "UPDATE conversations SET snapshot_json = ?, updated_at = ? WHERE conversation_id = ?",
                    (snapshot_json, now, conversation_id),
                )
                self._db.execute("COMMIT")
            except BaseException:
                self._db.execute("ROLLBACK")
                raise

    def prune_bloat(
        self,
        *,
        telemetry_keep: int = 20,
        max_events_per_conv: Optional[int] = None,
        vacuum: bool = True,
    ) -> dict[str, int]:
        """Remove legacy TELEMETRY_UPDATE bloat rows and trim stored snapshot telemetry."""
        limit = max(1, int(max_events_per_conv or self.retention))
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                cur = self._db.execute("DELETE FROM events WHERE event_type = 'TELEMETRY_UPDATE'")
                deleted_telemetry_rows = cur.rowcount if cur.rowcount >= 0 else 0
                cur_ret = self._db.execute(
                    """
                    DELETE FROM events
                    WHERE EXISTS (
                        SELECT 1 FROM conversations c
                        WHERE c.conversation_id = events.conversation_id
                          AND events.seq <= c.seq - ?
                    )
                    """,
                    (limit,),
                )
                deleted_retention_rows = cur_ret.rowcount if cur_ret.rowcount >= 0 else 0

                compacted_snapshots = 0
                rows = self._db.execute("SELECT conversation_id, snapshot_json FROM conversations").fetchall()
                for row in rows:
                    try:
                        snap = json.loads(row["snapshot_json"])
                    except Exception:
                        continue
                    if not isinstance(snap, dict) or not isinstance(snap.get("telemetry"), dict):
                        continue
                    compacted = self.compact_telemetry_store(snap["telemetry"], max_calls=telemetry_keep)
                    if compacted != snap["telemetry"]:
                        snap["telemetry"] = compacted
                        self._db.execute(
                            "UPDATE conversations SET snapshot_json = ? WHERE conversation_id = ?",
                            (self._json(snap), row["conversation_id"]),
                        )
                        compacted_snapshots += 1
                self._db.execute("COMMIT")
            except BaseException:
                self._db.execute("ROLLBACK")
                raise

            if vacuum:
                self._db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                if self.db_path != ":memory:":
                    self._db.execute("VACUUM")
                    self._db.execute("PRAGMA wal_checkpoint(TRUNCATE)")

            return {
                "deletedTelemetryRows": deleted_telemetry_rows,
                "deletedRetentionRows": deleted_retention_rows,
                "compactedSnapshots": compacted_snapshots,
            }

    def close(self) -> None:
        with self._lock:
            self._db.close()
