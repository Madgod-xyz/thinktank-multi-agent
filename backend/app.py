"""FastAPI REST and WebSocket server for ThinkTank v4.0 Case Ledger."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
from contextvars import ContextVar
import json
import os
import re
import time
import uuid
from typing import Any, Optional

from fastapi import Body, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

try:
    from .bridge import execute_subagent_command
    from .bridge_transport import flush_outbox_fast
    from .catalog import (
        infer_request_type as _infer_request_type,
        load_role_catalog,
        normalize_agent_id,
        normalize_workspace_uri,
    )
    from .ledger_domain import (
        CaseGateError,
        apply_agent_update,
        apply_chat_send,
        apply_collaborate,
        apply_finding_action,
        apply_governance_compress,
        apply_governance_extend,
        apply_governance_reopen,
        apply_proposal_action,
        apply_proposal_update,
        apply_proposal_vote,
        apply_review_decision,
        apply_review_decision_dispatch,
        apply_review_dispatch,
        apply_review_submit,
        apply_subtask_upsert,
        apply_task_update,
        apply_telemetry_tool,
        build_conversations_list,
        build_interaction_graph,
        build_status_snapshot,
        compute_origin_counts,
        create_empty_conversation,
        get_conv_sort_ts,
        has_thinktank_activity,
        is_phantom_child_conv,
        is_unclosed_thinktank,
        normalize_conversation,
        now_hms,
        now_ms,
        role_usage,
        upsert_agent_state,
    )
    from .outbox_recovery import outbox_recovery_loop
    from .session_resolver import (
        SessionResolver,
        resolve_session_file,
        resolve_subagent_links_file,
    )
    from .store import SyncEventStore
    from .ws_hub import WebSocketHub
except ImportError:
    from bridge import execute_subagent_command
    from bridge_transport import flush_outbox_fast
    from catalog import (
        infer_request_type as _infer_request_type,
        load_role_catalog,
        normalize_agent_id,
        normalize_workspace_uri,
    )
    from ledger_domain import (
        CaseGateError,
        apply_agent_update,
        apply_chat_send,
        apply_collaborate,
        apply_finding_action,
        apply_governance_compress,
        apply_governance_extend,
        apply_governance_reopen,
        apply_proposal_action,
        apply_proposal_update,
        apply_proposal_vote,
        apply_review_decision,
        apply_review_decision_dispatch,
        apply_review_dispatch,
        apply_review_submit,
        apply_subtask_upsert,
        apply_task_update,
        apply_telemetry_tool,
        build_conversations_list,
        build_interaction_graph,
        build_status_snapshot,
        compute_origin_counts,
        create_empty_conversation,
        get_conv_sort_ts,
        has_thinktank_activity,
        is_phantom_child_conv,
        is_unclosed_thinktank,
        normalize_conversation,
        now_hms,
        now_ms,
        role_usage,
        upsert_agent_state,
    )
    from outbox_recovery import outbox_recovery_loop
    from session_resolver import (
        SessionResolver,
        resolve_session_file,
        resolve_subagent_links_file,
    )
    from store import SyncEventStore
    from ws_hub import WebSocketHub


STATE_FILE = os.environ.get(
    "THINKTANK_STATE_FILE",
    os.path.join(os.path.expanduser("~"), ".gemini", "config", "think_tank_live_state.json"),
)
SYNC_DB_FILE = os.environ.get(
    "THINKTANK_SYNC_DB",
    os.path.join(os.path.dirname(STATE_FILE), "think_tank_sync.sqlite3"),
)

sync_store = SyncEventStore(SYNC_DB_FILE)
session_resolver = SessionResolver(sync_store)
ws_hub = WebSocketHub(sync_store)

conversations_store: dict[str, dict[str, Any]] = {}
subagent_session_map = session_resolver.subagent_session_map
sessions_by_workspace = session_resolver.sessions_by_workspace

request_event_id: ContextVar[Optional[str]] = ContextVar("thinktank_event_id", default=None)
request_project_id: ContextVar[Optional[str]] = ContextVar("thinktank_project_id", default=None)

_PROJECT_ID_RE = re.compile(r"^[A-Za-z0-9._:-]+$")


def _valid_project_id(raw: Any) -> Optional[str]:
    if not isinstance(raw, str):
        return None
    val = raw.strip()
    if not val or len(val) > 200 or not _PROJECT_ID_RE.fullmatch(val):
        return None
    return val


def project_matches(conv: dict[str, Any], project_id: Optional[str]) -> bool:
    owner = conv.get("projectId")
    if project_id:
        return owner == project_id
    return True


def _assert_project_access(conv: dict[str, Any], project_id: Optional[str], *, bind_if_empty: bool = False) -> bool:
    if not project_id:
        return False
    owner = conv.get("projectId")
    if owner and owner != project_id:
        raise CaseGateError(409, "This session belongs to a different project.")
    if not owner and bind_if_empty:
        conv["projectId"] = project_id
        return True
    return False


def get_or_create_conversation(conv_id: Optional[str]) -> dict[str, Any]:
    cid = (conv_id or session_resolver.active_conv_id or "default").strip()
    if cid not in conversations_store:
        conversations_store[cid] = create_empty_conversation(cid)
    return conversations_store[cid]


def require_conversation_id(conv_id: Optional[str]) -> str:
    cid = (conv_id or "").strip()
    if not cid or cid == "default":
        raise CaseGateError(400, "An explicit Antigravity conversation ID is required for writes.")
    existing = conversations_store.get(cid)
    if existing is not None:
        _assert_project_access(existing, request_project_id.get())
    return cid


def _ensure_writable_conv(conv_id: Optional[str]) -> tuple[str, dict[str, Any]]:
    cid = require_conversation_id(conv_id)
    conv = get_or_create_conversation(cid)
    _assert_project_access(conv, request_project_id.get(), bind_if_empty=True)
    return cid, conv


def load_persisted_state() -> None:
    sync_store.import_legacy_files(
        state_file=STATE_FILE,
        session_file=resolve_session_file(),
        links_file=resolve_subagent_links_file(),
    )
    loaded = sync_store.load_conversations()
    conversations_store.clear()
    for cid, row in loaded.items():
        snap = row.get("snapshot")
        if isinstance(snap, dict):
            conversations_store[cid] = snap

    session_resolver.subagent_session_map.clear()
    session_resolver.subagent_session_map.update(sync_store.load_subagent_links())
    for child_cid in list(session_resolver.subagent_session_map.keys()):
        if session_resolver.is_non_child(child_cid, conversations_store, is_phantom_child_conv):
            session_resolver.subagent_session_map.pop(child_cid, None)
            sync_store.delete_subagent_link(child_cid)
        elif child_cid in conversations_store and is_phantom_child_conv(conversations_store[child_cid]):
            conversations_store.pop(child_cid, None)
            sync_store.delete_conversation(child_cid)

    for cid, snapshot in list(conversations_store.items()):
        if normalize_conversation(cid, snapshot):
            sync_store.save_snapshot_only(cid, snapshot)

    session_resolver.sessions_by_workspace.clear()
    session_resolver.sessions_by_workspace.update(sync_store.load_workspace_sessions())
    for tier in (0, 1, 2):
        for cid, snapshot in sorted(conversations_store.items(), key=lambda kv: get_conv_sort_ts(kv[1])):
            has_tt = has_thinktank_activity(snapshot)
            is_closed = bool((snapshot.get("thinkTank") or {}).get("isClosed"))
            snap_tier = 2 if (has_tt and not is_closed) else (1 if has_tt else 0)
            if snap_tier != tier:
                continue
            norm_ws = normalize_workspace_uri(snapshot.get("workspaceUri"))
            if norm_ws and cid != "default" and "--run-" not in cid and not snapshot.get("isArchivedRun"):
                session_resolver.sessions_by_workspace[norm_ws] = {
                    "conversationId": cid,
                    "projectId": snapshot.get("projectId"),
                    "timestamp": get_conv_sort_ts(snapshot),
                }

    if session_resolver.active_conv_id in session_resolver.subagent_session_map:
        session_resolver.active_conv_id = session_resolver.subagent_session_map[session_resolver.active_conv_id]["parentConvId"]
    if session_resolver.active_conv_id not in conversations_store:
        session_resolver.active_conv_id = next(iter(conversations_store), "default")


def _convs_list(target_cid: str, *, include_target_if_in_store: bool = False) -> list[dict[str, Any]]:
    return build_conversations_list(
        conversations_store,
        target_cid,
        subagent_map=session_resolver.subagent_session_map,
        include_target_if_in_store=include_target_if_in_store,
    )


def _build_status_payload(target_cid: str) -> dict[str, Any]:
    mapped = session_resolver.ensure_subagent_mapping(target_cid, conversations_store, is_phantom_child_conv)
    if mapped:
        target_cid = mapped["parentConvId"]
    project_id = request_project_id.get()
    in_store = target_cid in conversations_store
    if in_store:
        conv = conversations_store[target_cid]
        if project_id and not conv.get("projectId"):
            conv["projectId"] = project_id
            sync_store.save_snapshot_only(target_cid, conv)
    else:
        conv = create_empty_conversation(target_cid)
    conv_list = _convs_list(target_cid, include_target_if_in_store=in_store)
    cursor = sync_store.cursor(target_cid)
    return build_status_snapshot(target_cid, conv, conv_list, cursor)


load_persisted_state()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    load_persisted_state()
    sync_store.prune_bloat(vacuum=False)
    recovery_task = asyncio.create_task(outbox_recovery_loop(flush_outbox_fast))
    try:
        yield
    finally:
        recovery_task.cancel()
        with suppress(asyncio.CancelledError):
            await recovery_task


app = FastAPI(title="ThinkTank v4.0 Case Ledger", version="4.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8780", "http://127.0.0.1:8780"],
    allow_origin_regex=r"^(https?://(localhost|127\.0\.0\.1)(:\d+)?|plugin://.*)$",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(CaseGateError)
async def handle_case_gate_error(_request: Any, exc: CaseGateError) -> JSONResponse:
    return JSONResponse({"status": "error", "detail": exc.detail}, status_code=exc.status_code)


@app.middleware("http")
async def idempotency_and_project_guard(request: Any, call_next: Any):
    supplied = request.headers.get("x-thinktank-event-id", "").strip()
    raw_project_id = request.headers.get("x-thinktank-project-id") or request.query_params.get("projectId")
    project_id = raw_project_id.strip() if isinstance(raw_project_id, str) else None
    if project_id and not _valid_project_id(project_id):
        return JSONResponse({"status": "error", "detail": "Invalid project ID."}, status_code=400)

    body_conv_id = None
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and "application/json" in request.headers.get("content-type", "").lower():
        try:
            body = json.loads(await request.body())
            if isinstance(body, dict):
                raw_bcid = body.get("convId") or body.get("parentConversationId") or body.get("conversationId")
                if isinstance(raw_bcid, str):
                    body_conv_id = raw_bcid.strip() or None
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

    query_conv_id = request.query_params.get("convId") or request.query_params.get("conv_id")
    if query_conv_id and body_conv_id and query_conv_id != body_conv_id:
        return JSONResponse({"status": "error", "detail": "Conversation IDs in the URL and request body do not match."}, status_code=400)

    conv_id = query_conv_id or body_conv_id
    mapped_conv_id = conv_id
    if conv_id and conv_id in session_resolver.subagent_session_map:
        mapped_conv_id = session_resolver.subagent_session_map[conv_id]["parentConvId"]

    conv = conversations_store.get(mapped_conv_id) if mapped_conv_id else None
    owner = conv.get("projectId") if conv else None
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and not request.url.path.endswith("/status") and project_id and owner and owner != project_id:
        return JSONResponse({"status": "error", "detail": "This session belongs to a different project."}, status_code=409)

    event_token = request_event_id.set(supplied[:200] or None)
    project_token = request_project_id.set(project_id)
    try:
        if supplied:
            previous = sync_store.find_event_id(supplied[:200])
            if previous:
                prev_cid = previous["conversation_id"]
                if not conv_id or (prev_cid != mapped_conv_id and prev_cid != conv_id):
                    return JSONResponse({"status": "error", "detail": "Idempotency key is already assigned to a different conversation."}, status_code=409)
                return JSONResponse({
                    "status": "duplicate",
                    "eventId": supplied[:200],
                    "convId": prev_cid,
                    "seq": previous["seq"],
                })
        return await call_next(request)
    finally:
        request_event_id.reset(event_token)
        request_project_id.reset(project_token)


async def _commit_event(
    cid: str,
    conv: dict[str, Any],
    event_kind: str,
    slices: list[str] | tuple[str, ...],
    *,
    extra: Optional[dict[str, Any]] = None,
    include_conversations_list: bool = False,
) -> dict[str, Any]:
    convs_list = _convs_list(cid) if include_conversations_list else None
    return await ws_hub.commit_and_broadcast(
        cid, conv, event_kind, slices,
        extra=extra, event_id=request_event_id.get(),
        conversations_list=convs_list,
    )


# --- Health, Catalog & Host Session Routes ---

@app.get("/api/health")
@app.get("/health")
def get_health() -> dict[str, Any]:
    return {
        "ok": True,
        "status": "ok",
        "version": "4.0.0",
        "syncMode": "durable-websocket",
        "conversationsCount": len(conversations_store),
    }


@app.get("/api/roles")
@app.get("/roles")
def get_roles() -> dict[str, Any]:
    return {"roles": load_role_catalog()}


@app.post("/api/host/active-session")
async def set_active_session(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    raw_cid = payload.get("conversationId")
    if not raw_cid or not isinstance(raw_cid, str) or not raw_cid.strip():
        return {"status": "error", "message": "Invalid conversationId"}
    raw_cid = raw_cid.strip()
    ev_source = str(payload.get("eventSource") or "").strip().lower()
    mapped = session_resolver.ensure_subagent_mapping(
        raw_cid, conversations_store, is_phantom_child_conv,
        parent_cid=payload.get("parentConversationId"),
        role_id=payload.get("roleId"),
        role_title=payload.get("roleTitle"),
    )
    cid = mapped["parentConvId"] if mapped else raw_cid

    req_pid = request_project_id.get()
    existing_conv = conversations_store.get(cid)
    if existing_conv is not None:
        _assert_project_access(existing_conv, req_pid)
    conv = get_or_create_conversation(cid)
    pid = req_pid or _valid_project_id(payload.get("projectId"))
    meta_dirty = False
    if pid and not conv.get("projectId"):
        conv["projectId"] = pid
        meta_dirty = True

    norm_ws = normalize_workspace_uri(payload.get("workspaceUri") or payload.get("workspace"))
    existing_ws_cid = str((session_resolver.sessions_by_workspace.get(norm_ws) or {}).get("conversationId") or "").strip() if norm_ws else ""
    existing_ws_conv = conversations_store.get(existing_ws_cid) if existing_ws_cid else None
    curr_active_conv = conversations_store.get(session_resolver.active_conv_id)

    can_claim = True
    if norm_ws and existing_ws_cid and existing_ws_cid != cid:
        if ev_source == "post-tool-use" and (not has_thinktank_activity(conv) or is_unclosed_thinktank(existing_ws_conv)):
            can_claim = False
        elif is_unclosed_thinktank(existing_ws_conv) and not has_thinktank_activity(conv):
            can_claim = False
    elif ev_source == "post-tool-use" and session_resolver.active_conv_id != cid and is_unclosed_thinktank(curr_active_conv) and not has_thinktank_activity(conv):
        can_claim = False

    prev_active_cid = session_resolver.active_conv_id
    if can_claim or not session_resolver.active_conv_id or session_resolver.active_conv_id == "default":
        session_resolver.active_conv_id = cid
        session_resolver.active_conv_workspace_uri = norm_ws or normalize_workspace_uri(conv.get("workspaceUri"))

    if norm_ws:
        if conv.get("workspaceUri") != norm_ws:
            conv["workspaceUri"] = norm_ws
            meta_dirty = True
        if can_claim:
            ts_now = time.time()
            session_resolver.sessions_by_workspace[norm_ws] = {
                "conversationId": cid, "projectId": conv.get("projectId"), "timestamp": ts_now,
            }
            sync_store.upsert_workspace_session(norm_ws, cid, conv.get("projectId"), updated_at=ts_now)

    agent_updated = False
    already_verified = False
    role_id = mapped.get("roleId") if mapped else None
    if mapped:
        tt = conv.get("thinkTank") or {}
        is_closed = bool(tt.get("isClosed")) or str(tt.get("status") or "").upper() in {"COMPLETED", "DONE", "CLOSED"}
        if not is_closed and role_id and role_id not in {"user", "subagent"}:
            norm_r = normalize_agent_id(role_id)
            already_verified = any(
                normalize_agent_id(ag.get("id")) == norm_r and ag.get("verifiedSubagent") and ag.get("subagentConvId") == raw_cid and ag.get("status") == "WORKING"
                for ag in conv.get("agents") or []
            )
            agent_updated = upsert_agent_state(
                conv, role_id, task=mapped.get("roleTitle") or None,
                status="WORKING", subagent_conv_id=raw_cid, verified_subagent=True,
            )

    if meta_dirty or agent_updated:
        sync_store.save_snapshot_only(cid, conv)

    if can_claim:
        focus_ws = norm_ws or normalize_workspace_uri(conv.get("workspaceUri"))
        cur_pid = conv.get("projectId")
        await ws_hub.broadcast_pulse(cid, "HOST_FOCUS", {"workspaceUri": focus_ws, "projectId": cur_pid, "activeConversationId": session_resolver.active_conv_id})
        if prev_active_cid and prev_active_cid != cid:
            prev_conv = conversations_store.get(prev_active_cid) or {}
            prev_ws = normalize_workspace_uri(prev_conv.get("workspaceUri"))
            prev_pid = prev_conv.get("projectId")
            same_ws = (prev_ws == focus_ws)
            same_pid = (not prev_pid or not cur_pid or prev_pid == cur_pid)
            if same_ws and same_pid:
                await ws_hub.broadcast_pulse(prev_active_cid, "HOST_FOCUS", {"convId": cid, "workspaceUri": focus_ws, "projectId": cur_pid, "activeConversationId": cid})

    if agent_updated and not already_verified:
        if has_thinktank_activity(conv):
            await _commit_event(cid, conv, "AGENTS_UPDATE", ["agents"])
        else:
            await ws_hub.broadcast_pulse(cid, "TELEMETRY", {"agentId": role_id, "roleId": role_id, "status": "WORKING"})

    return {"status": "ok", "activeConversationId": session_resolver.active_conv_id}


@app.get("/api/host/active-session")
@app.get("/api/host/context")
async def get_active_session(workspaceUri: Optional[str] = Query(None)) -> dict[str, Any]:
    resolved_cid, ws_matched, norm_ws = session_resolver.resolve_for_workspace(
        workspaceUri, conversations_store,
        has_thinktank_activity, is_unclosed_thinktank, is_phantom_child_conv, get_conv_sort_ts,
    )
    conv = conversations_store.get(resolved_cid, {}) if resolved_cid else {}
    return {
        "conversationId": resolved_cid,
        "convId": resolved_cid,
        "workspaceUri": norm_ws or conv.get("workspaceUri"),
        "workspaceMatched": ws_matched,
        "projectId": conv.get("projectId"),
        "project": (conv.get("thinkTank") or {}).get("project"),
        "status": (conv.get("thinkTank") or {}).get("status", "DISCONNECTED" if not resolved_cid else "ACTIVE"),
        "hasSession": has_thinktank_activity(conv),
    }


@app.get("/api/conversations")
async def list_conversations() -> dict[str, Any]:
    session_resolver.refresh_from_session_file(
        conversations_store, has_thinktank_activity, is_unclosed_thinktank, is_phantom_child_conv,
    )
    target_cid = session_resolver.active_conv_id or "default"
    return {"conversations": _convs_list(target_cid)}


@app.get("/api/status")
@app.get("/status")
async def get_status(
    convId: Optional[str] = Query(None),
    conv_id: Optional[str] = Query(None),
    workspaceUri: Optional[str] = Query(None),
) -> dict[str, Any]:
    explicit_cid = (convId or conv_id or "").strip()
    if explicit_cid:
        return _build_status_payload(explicit_cid)
    resolved_cid, ws_matched, _ = session_resolver.resolve_for_workspace(
        workspaceUri, conversations_store,
        has_thinktank_activity, is_unclosed_thinktank, is_phantom_child_conv, get_conv_sort_ts,
    )
    return _build_status_payload(resolved_cid if (ws_matched and resolved_cid) else "default")


@app.post("/api/status")
@app.post("/status")
async def post_status(
    payload: Optional[dict[str, Any]] = Body(None),
    convId: Optional[str] = Query(None),
    conv_id: Optional[str] = Query(None),
    workspaceUri: Optional[str] = Query(None),
) -> dict[str, Any]:
    body = payload or {}
    body_cid = str(body.get("convId") or body.get("conversationId") or body.get("conv_id") or "").strip()
    body_ws = str(body.get("workspaceUri") or body.get("workspace") or "").strip()
    query_cid = (convId or conv_id or "").strip()
    return await get_status(convId=query_cid or body_cid or None, workspaceUri=workspaceUri or body_ws or None)


# --- Task, WBS, Agent, Finding & Collaboration Mutations ---

class TaskUpdateRequest(BaseModel):
    project: Optional[str] = None
    directive: Optional[str] = None
    status: Optional[str] = None
    phase: Optional[str] = None
    progress: Optional[int] = None
    activeAgentIds: Optional[list[str]] = None
    round: Optional[int] = None
    maxRounds: Optional[int] = None
    roleCaps: Optional[dict[str, int]] = None
    roundStatus: Optional[str] = None
    triageDecision: Optional[dict[str, Any]] = None
    forceClose: bool = False
    forceReason: Optional[str] = None
    reopen: bool = False
    resetCase: bool = False
    newRun: bool = False
    summary: Optional[str] = None
    origin: Optional[str] = None
    subagentConvId: Optional[str] = None
    convId: Optional[str] = None
    model_config = {"extra": "allow"}


@app.post("/api/task/update")
async def update_task(req: TaskUpdateRequest) -> dict[str, Any]:
    cid = require_conversation_id(req.convId)
    if req.newRun and "--run-" in cid:
        cid = require_conversation_id(cid.split("--run-")[0])
    conv = get_or_create_conversation(cid)
    _assert_project_access(conv, request_project_id.get(), bind_if_empty=True)
    archived_run_id, slices = apply_task_update(cid, conv, req.model_dump(), conversations_store, store=sync_store)
    ws_uri = normalize_workspace_uri(conv.get("workspaceUri"))
    if ws_uri:
        ts_now = time.time()
        session_resolver.sessions_by_workspace[ws_uri] = {"conversationId": cid, "projectId": conv.get("projectId"), "timestamp": ts_now}
        sync_store.upsert_workspace_session(ws_uri, cid, conv.get("projectId"), updated_at=ts_now)
    env = await _commit_event(cid, conv, "STATE_UPDATE", slices, include_conversations_list=True)
    return {
        "status": "updated",
        "convId": cid,
        "thinkTank": conv["thinkTank"],
        "closureReceipt": conv["thinkTank"].get("closureReceipt"),
        "archivedRunId": archived_run_id,
        "seq": env["seq"],
    }


class SubtaskUpsertRequest(BaseModel):
    id: Optional[str] = None
    title: str
    assignee: str
    assigneeName: Optional[str] = None
    delegatedBy: Optional[str] = "team_manager"
    delegatedByName: Optional[str] = "مدیر تیم"
    status: str = "ASSIGNED"
    priority: str = "HIGH"
    deliverable: Optional[str] = ""
    thoughts: Optional[str] = None
    report: Optional[str] = None
    dependencies: Optional[list[str]] = None
    lockedFiles: Optional[list[str]] = None
    acceptanceCriteria: Optional[str] = None
    origin: Optional[str] = None
    subagentConvId: Optional[str] = None
    convId: Optional[str] = None
    model_config = {"extra": "allow"}


@app.post("/api/subtasks/upsert")
async def upsert_subtask(req: SubtaskUpsertRequest) -> dict[str, Any]:
    cid, conv = _ensure_writable_conv(req.convId)
    entry = apply_subtask_upsert(cid, conv, req.model_dump())
    slices = ["subtasks", "fileLocks", "agents", "thinkTank", "messages", "interactions", "graph"]
    env = await _commit_event(cid, conv, "SUBTASKS_UPDATE", slices)
    return {
        "status": "ok", "convId": cid, "subtask": entry,
        "subtasks": conv["subtasks"], "fileLocks": conv["fileLocks"], "seq": env["seq"],
    }


class AgentUpdateRequest(BaseModel):
    id: str
    name: Optional[str] = None
    role: Optional[str] = None
    code: Optional[str] = None
    icon: Optional[str] = None
    task: Optional[str] = None
    tool: Optional[str] = None
    thought: Optional[str] = None
    demo: Optional[str] = None
    status: Optional[str] = None
    progress: Optional[int] = None
    latency: Optional[int] = None
    collaboratingWith: Optional[list[str]] = None
    convId: Optional[str] = None
    model_config = {"extra": "allow"}


@app.post("/api/agent/update")
async def update_agent_endpoint(req: AgentUpdateRequest) -> dict[str, Any]:
    cid, conv = _ensure_writable_conv(req.convId)
    apply_agent_update(conv, req.model_dump())
    env = await _commit_event(cid, conv, "AGENTS_UPDATE", ["agents"])
    return {"status": "ok", "convId": cid, "agents": conv["agents"], "seq": env["seq"]}


class CollaborateRequest(BaseModel):
    fromAgent: str
    toAgent: str
    label: Optional[str] = "همکاری و مباحثه فعال"
    action: Optional[str] = "PEER_SYNC"
    requestType: Optional[str] = None
    channel: Optional[str] = None
    severity: Optional[str] = None
    parentSeq: Optional[int] = None
    result: Optional[str] = None
    returnToFixing: Optional[bool] = None
    crosstalkMessage: Optional[str] = None
    content: Optional[str] = None
    thoughts: Optional[str] = None
    thought: Optional[str] = None
    critique: Optional[str] = None
    question: Optional[str] = None
    report: Optional[str] = None
    fullReport: Optional[str] = None
    topic: Optional[str] = None
    origin: Optional[str] = None
    subagentConvId: Optional[str] = None
    findingId: Optional[str] = None
    workItemId: Optional[str] = None
    reproSteps: Optional[str] = None
    evidenceCommand: Optional[str] = None
    exitCode: Optional[int] = None
    evidenceExcerpt: Optional[str] = None
    runner: Optional[str] = None
    runnerReason: Optional[str] = None
    convId: Optional[str] = None
    model_config = {"extra": "allow"}


@app.post("/api/agent/collaborate")
async def collaborate_endpoint(req: CollaborateRequest) -> dict[str, Any]:
    cid, conv = _ensure_writable_conv(req.convId)
    finding, collab_msg = apply_collaborate(cid, conv, req.model_dump())
    action_upper = str(req.action or "PEER_SYNC").strip().upper()
    slices = ["thinkTank", "agents", "messages", "interactions", "graph"]
    if finding is not None or action_upper in {"RETURN_DEFECT", "WORKER_FIX", "REVIEW_QUERY", "QA_DISPATCH", "QA_REPORT"}:
        slices.append("findings")
    env = await _commit_event(
        cid, conv, "COLLABORATION_UPDATE", slices,
        extra={"message": collab_msg} if collab_msg else None,
    )
    return {
        "status": "ok",
        "convId": cid,
        "thinkTank": conv["thinkTank"],
        "collaborations": conv["collaborations"],
        "findings": conv["findings"],
        "finding": finding,
        "originCounts": compute_origin_counts(conv),
        "interactions": conv["interactions"],
        "graph": build_interaction_graph(conv),
        "message": collab_msg,
        "seq": env["seq"],
    }


class FindingActionRequest(BaseModel):
    convId: Optional[str] = None
    findingId: str
    action: str
    reason: Optional[str] = None


@app.post("/api/findings/action")
async def finding_action_endpoint(req: FindingActionRequest) -> dict[str, Any]:
    cid, conv = _ensure_writable_conv(req.convId)
    finding = apply_finding_action(conv, req.model_dump())
    env = await _commit_event(cid, conv, "FINDINGS_UPDATE", ["findings", "thinkTank"])
    return {"status": "ok", "convId": cid, "finding": finding, "findings": conv["findings"], "seq": env["seq"]}


# --- Proposal & Chat Routes ---

class ProposalUpdateRequest(BaseModel):
    id: str
    project: str
    title: str
    author: str
    summary: str
    decisionOptions: Optional[list[dict[str, Any]]] = None
    votes: Optional[list[dict[str, Any]]] = None
    convId: Optional[str] = None


@app.post("/api/proposal/update")
async def update_proposal(req: ProposalUpdateRequest) -> dict[str, Any]:
    cid, conv = _ensure_writable_conv(req.convId)
    prop = apply_proposal_update(cid, conv, req.model_dump())
    env = await _commit_event(cid, conv, "PROPOSAL_UPDATE", ["proposal", "thinkTank"])
    return {"status": "ok", "convId": cid, "proposal": prop, "seq": env["seq"]}


class ProposalActionRequest(BaseModel):
    action: str
    optionId: Optional[str] = None
    comment: Optional[str] = None
    convId: Optional[str] = None


@app.post("/api/proposal/action")
async def handle_proposal_action(req: ProposalActionRequest) -> dict[str, Any]:
    cid, conv = _ensure_writable_conv(req.convId)
    prop = apply_proposal_action(cid, conv, req.model_dump())
    slices = ["proposal", "thinkTank", "messages", "interactions", "graph"]
    env = await _commit_event(cid, conv, "PROPOSAL_UPDATE", slices)
    return {"status": "ok", "convId": cid, "proposal": prop, "thinkTank": conv["thinkTank"], "seq": env["seq"]}


class ProposalVoteRequest(BaseModel):
    voter: str
    voterName: Optional[str] = None
    voterRole: Optional[str] = None
    stance: str = "APPROVE"
    confidence: int = 90
    comment: str
    counterArgument: Optional[str] = None
    origin: Optional[str] = None
    subagentConvId: Optional[str] = None
    convId: Optional[str] = None


@app.post("/api/proposal/vote")
async def vote_proposal(req: ProposalVoteRequest) -> dict[str, Any]:
    cid, conv = _ensure_writable_conv(req.convId)
    vote_entry, prop, msg_entry = apply_proposal_vote(cid, conv, req.model_dump())
    slices = ["proposal", "thinkTank", "agents", "messages", "interactions", "graph"]
    env = await _commit_event(cid, conv, "PROPOSAL_UPDATE", slices, extra={"message": msg_entry})
    return {"status": "ok", "convId": cid, "vote": vote_entry, "proposal": prop, "seq": env["seq"]}


class ChatMessageRequest(BaseModel):
    id: Optional[str] = None
    channel: str = "MAIN"
    requestType: Optional[str] = None
    senderCode: str
    senderName: str
    senderRole: str
    recipientCode: Optional[str] = None
    recipientName: Optional[str] = None
    recipientRole: Optional[str] = None
    recipient: Optional[str] = None
    timestamp: Optional[str] = None
    content: str
    thoughts: Optional[str] = None
    thought: Optional[str] = None
    critique: Optional[str] = None
    counterArgument: Optional[str] = None
    question: Optional[str] = None
    questions: Optional[list[str]] = None
    report: Optional[str] = None
    fullReport: Optional[str] = None
    topic: Optional[str] = None
    isBtw: bool = False
    isOperator: bool = False
    isReview: bool = False
    reviewId: Optional[str] = None
    origin: Optional[str] = None
    subagentConvId: Optional[str] = None
    findingId: Optional[str] = None
    workItemId: Optional[str] = None
    reproSteps: Optional[str] = None
    convId: Optional[str] = None
    model_config = {"extra": "allow"}


@app.post("/api/chat/send")
@app.post("/api/messages/send")
async def send_chat(req: ChatMessageRequest) -> dict[str, Any]:
    cid, conv = _ensure_writable_conv(req.convId)
    msg_dict, is_dup, agents_modified = apply_chat_send(cid, conv, req.model_dump())
    if is_dup:
        return {"status": "duplicate", "convId": cid, "message": msg_dict}
    slices = ["thinkTank", "messages", "interactions", "graph"]
    if agents_modified:
        slices.append("agents")
    env = await _commit_event(cid, conv, "NEW_MESSAGE", slices, extra={"message": msg_dict})
    return {"status": "sent", "convId": cid, "message": msg_dict, "seq": env["seq"]}


# --- Deliberation Governance Routes ---

class ExtendRoundsRequest(BaseModel):
    additionalRounds: int = Field(default=3, ge=1, le=50)
    convId: Optional[str] = None


@app.post("/api/governance/extend_rounds")
async def extend_rounds_endpoint(req: ExtendRoundsRequest) -> dict[str, Any]:
    cid, conv = _ensure_writable_conv(req.convId)
    res, msg = apply_governance_extend(cid, conv, req.model_dump())
    env = await _commit_event(cid, conv, "GOVERNANCE_UPDATE", ["thinkTank", "messages", "interactions", "graph"], extra={"message": msg})
    return {**res, "seq": env["seq"]}


class ReopenCaseRequest(BaseModel):
    convId: Optional[str] = None


@app.post("/api/governance/reopen")
async def reopen_case_endpoint(req: ReopenCaseRequest) -> dict[str, Any]:
    cid, conv = _ensure_writable_conv(req.convId)
    _, slices = apply_governance_reopen(cid, conv, conversations_store, store=sync_store)
    env = await _commit_event(cid, conv, "STATE_UPDATE", slices, include_conversations_list=True)
    return {
        "status": "updated", "convId": cid,
        "thinkTank": conv["thinkTank"], "closureReceipt": conv["thinkTank"].get("closureReceipt"),
        "archivedRunId": None, "seq": env["seq"],
    }


class CompressFinalRequest(BaseModel):
    convId: Optional[str] = None


@app.post("/api/governance/compress_final")
async def compress_final_endpoint(req: CompressFinalRequest) -> dict[str, Any]:
    cid, conv = _ensure_writable_conv(req.convId)
    review = apply_governance_compress(cid, conv)
    env = await _commit_event(cid, conv, "GOVERNANCE_REVIEW_REQUEST", ["thinkTank", "review"])
    return {"status": "review_requested", "convId": cid, "review": review, "seq": env["seq"]}


class ReviewDispatchRequest(BaseModel):
    status: str = Field(pattern="^(sent|failed)$")
    error: Optional[str] = None
    convId: Optional[str] = None


@app.post("/api/governance/review_dispatch")
async def review_dispatch_endpoint(req: ReviewDispatchRequest) -> dict[str, Any]:
    cid, conv = _ensure_writable_conv(req.convId)
    review = apply_review_dispatch(cid, conv, req.model_dump())
    env = await _commit_event(cid, conv, "GOVERNANCE_REVIEW_DISPATCH", ["review", "thinkTank"])
    return {"status": "ok", "convId": cid, "review": review, "seq": env["seq"]}


class ReviewSubmissionRequest(BaseModel):
    reviewId: str = Field(min_length=1, max_length=200)
    managerSummary: str = Field(min_length=1, max_length=4000)
    mainSummary: str = Field(min_length=1, max_length=4000)
    confidence: int = Field(ge=0, le=100)
    recommendation: str = Field(pattern="^(continue|complete)$")
    continueReasons: list[str] = Field(min_length=1, max_length=8)
    completionReasons: list[str] = Field(min_length=1, max_length=8)
    evidence: list[str] = Field(min_length=1, max_length=12)
    convId: Optional[str] = None


@app.post("/api/governance/submit_review")
async def submit_review_endpoint(req: ReviewSubmissionRequest) -> dict[str, Any]:
    cid, conv = _ensure_writable_conv(req.convId)
    review = apply_review_submit(cid, conv, req.model_dump())
    closed_by_review = bool((conv.get("thinkTank") or {}).get("isClosed"))
    slices = (
        ["review", "thinkTank", "findings", "subtasks", "fileLocks", "agents", "messages", "interactions", "graph", "closureReceipt", "conversationsList"]
        if closed_by_review
        else ["review", "thinkTank"]
    )
    env = await _commit_event(cid, conv, "GOVERNANCE_REVIEW_SUBMITTED", slices, include_conversations_list=closed_by_review)
    return {"status": "ok", "convId": cid, "review": review, "thinkTank": conv["thinkTank"], "closureReceipt": conv["thinkTank"].get("closureReceipt"), "seq": env["seq"]}


class ReviewDecisionRequest(BaseModel):
    decision: str = Field(pattern="^(continue|stop)$")
    note: Optional[str] = Field(default=None, max_length=1200)
    convId: Optional[str] = None


@app.post("/api/governance/review_decision")
async def review_decision_endpoint(req: ReviewDecisionRequest) -> dict[str, Any]:
    cid, conv = _ensure_writable_conv(req.convId)
    review, msg = apply_review_decision(cid, conv, req.model_dump())
    env = await _commit_event(cid, conv, "GOVERNANCE_REVIEW_DECISION", ["review", "thinkTank", "messages", "interactions", "graph"], extra={"message": msg})
    return {"status": "ok", "convId": cid, "review": review, "thinkTank": conv["thinkTank"], "seq": env["seq"]}


class ReviewDecisionDispatchRequest(BaseModel):
    status: str = Field(pattern="^(sent|failed)$")
    error: Optional[str] = None
    convId: Optional[str] = None


@app.post("/api/governance/review_decision_dispatch")
async def review_decision_dispatch_endpoint(req: ReviewDecisionDispatchRequest) -> dict[str, Any]:
    cid, conv = _ensure_writable_conv(req.convId)
    review = apply_review_decision_dispatch(cid, conv, req.model_dump())
    env = await _commit_event(cid, conv, "GOVERNANCE_REVIEW_DISPATCH", ["review", "thinkTank"])
    return {"status": "ok", "convId": cid, "review": review, "seq": env["seq"]}


# --- Telemetry & Tool Execution Routes ---

@app.get("/api/telemetry")
async def get_telemetry(convId: Optional[str] = Query(None), conv_id: Optional[str] = Query(None)) -> dict[str, Any]:
    raw_cid = (convId or conv_id or "").strip() or session_resolver.active_conv_id
    mapped = session_resolver.ensure_subagent_mapping(raw_cid, conversations_store, is_phantom_child_conv)
    cid = mapped["parentConvId"] if mapped else raw_cid
    existing = conversations_store.get(cid)
    if existing is not None:
        return existing["telemetry"]
    return {"toolCalls": [], "terminalLogs": [], "backgroundTasks": []}


class AntigravityToolEventRequest(BaseModel):
    id: str = Field(min_length=1, max_length=200)
    convId: str = Field(min_length=1, max_length=200)
    tool: str = Field(min_length=1, max_length=120)
    status: str = Field(pattern="^(SUCCESS|ERROR)$")
    stepIdx: int = Field(ge=0)
    args: Optional[dict[str, Any]] = None
    output: Optional[str] = None
    error: Optional[str] = None
    agentId: Optional[str] = None
    agentName: Optional[str] = None
    parentConversationId: Optional[str] = None
    roleId: Optional[str] = None
    roleTitle: Optional[str] = None
    model_config = {"extra": "allow"}


@app.post("/api/telemetry/host_tool")
async def log_antigravity_tool_event(req: AntigravityToolEventRequest) -> dict[str, Any]:
    raw_cid = require_conversation_id(req.convId)
    mapped = session_resolver.ensure_subagent_mapping(
        raw_cid, conversations_store, is_phantom_child_conv,
        parent_cid=req.parentConversationId, role_id=req.roleId, role_title=req.roleTitle,
    )
    cid = mapped["parentConvId"] if mapped else raw_cid
    conv = get_or_create_conversation(cid)
    _assert_project_access(conv, request_project_id.get(), bind_if_empty=True)

    res = apply_telemetry_tool(cid, raw_cid, conv, req.model_dump(), session_resolver, conversations_store, mapped=mapped)
    if res["duplicate"]:
        return {"status": "duplicate", "convId": cid, "entry": res["entry"]}

    entry = res["entry"]
    if res["autoCollabMsg"] is not None:
        await _commit_event(
            cid, conv, "CASE_EVENT",
            ["agents", "messages", "interactions", "graph", "telemetry"],
            extra={"message": res["autoCollabMsg"], "telemetryEntry": entry},
        )
    elif res.get("durableAgentEvent"):
        await _commit_event(
            cid, conv, "AGENTS_UPDATE",
            ["agents", "telemetry"],
            extra={"telemetryEntry": entry},
        )
        await ws_hub.broadcast_pulse(cid, "TELEMETRY", {
            "telemetry": conv["telemetry"],
            "telemetryEntry": entry,
            "toolCall": entry,
            "agentId": res["callerRole"],
            "roleId": res["callerRole"],
            "tool": res["toolName"],
            "status": "WORKING",
        })
    else:
        sync_store.save_snapshot_only(cid, conv)
        await ws_hub.broadcast_pulse(cid, "TELEMETRY", {
            "telemetry": conv["telemetry"],
            "telemetryEntry": entry,
            "toolCall": entry,
            "agentId": res["callerRole"],
            "roleId": res["callerRole"],
            "tool": res["toolName"],
            "status": "WORKING",
        })
    return {"status": "ok", "convId": cid, "entry": entry}


class ToolCallLogRequest(BaseModel):
    id: Optional[str] = None
    agentId: str
    agentName: Optional[str] = None
    tool: str
    args: Optional[dict[str, Any]] = None
    output: str
    status: str = "SUCCESS"
    latencyMs: Optional[int] = None
    convId: Optional[str] = None


@app.post("/api/telemetry/tool_call")
async def log_tool_call(req: ToolCallLogRequest) -> dict[str, Any]:
    cid, conv = _ensure_writable_conv(req.convId)
    call_id = req.id or f"tc-{now_ms()}"
    entry = SyncEventStore.compact_tool_entry({
        "id": call_id, "agentId": req.agentId, "agentName": req.agentName or req.agentId,
        "tool": req.tool, "args": req.args or {}, "output": req.output,
        "status": req.status, "latencyMs": req.latencyMs,
        "timestamp": now_hms(), "createdAtMs": now_ms(),
    })
    telem = conv.setdefault("telemetry", {"toolCalls": [], "terminalLogs": [], "backgroundTasks": []})
    telem.setdefault("toolCalls", []).insert(0, entry)
    telem["toolCalls"] = telem["toolCalls"][:25]

    ag_target = normalize_agent_id(req.agentId or "main_agent")
    if ag_target and ag_target != "user":
        upsert_agent_state(conv, ag_target, name=req.agentName, tool=req.tool.strip(), status="ACTIVE")

    sync_store.save_snapshot_only(cid, conv)
    await ws_hub.broadcast_pulse(cid, "TELEMETRY", {
        "telemetry": telem, "telemetryEntry": entry, "toolCall": entry,
        "agentId": ag_target, "roleId": ag_target, "tool": req.tool.strip(), "status": "ACTIVE",
    })
    return {"status": "ok", "entry": entry}


class TerminalLogRequest(BaseModel):
    id: Optional[str] = None
    agentId: str
    agentName: Optional[str] = None
    command: str
    output: str
    exitCode: int = 0
    convId: Optional[str] = None


@app.post("/api/telemetry/terminal_log")
async def log_terminal(req: TerminalLogRequest) -> dict[str, Any]:
    cid, conv = _ensure_writable_conv(req.convId)
    entry = {
        "id": req.id or f"tl-{now_ms()}",
        "agentId": req.agentId, "agentName": req.agentName or req.agentId,
        "command": req.command, "output": (req.output or "")[:400],
        "exitCode": req.exitCode, "timestamp": now_hms(), "createdAtMs": now_ms(),
    }
    telem = conv.setdefault("telemetry", {"toolCalls": [], "terminalLogs": [], "backgroundTasks": []})
    telem.setdefault("terminalLogs", []).insert(0, entry)
    telem["terminalLogs"] = telem["terminalLogs"][:25]
    sync_store.save_snapshot_only(cid, conv)
    await ws_hub.broadcast_pulse(cid, "TELEMETRY", {"telemetry": telem, "terminalLog": entry})
    return {"status": "ok", "entry": entry}


class TaskLogRequest(BaseModel):
    id: str
    agentId: str
    agentName: Optional[str] = None
    title: str
    command: str
    pid: Optional[int] = None
    status: str = "RUNNING"
    isDaemon: bool = False
    uptime: Optional[str] = "Active"
    convId: Optional[str] = None


@app.post("/api/telemetry/task")
async def log_task(req: TaskLogRequest) -> dict[str, Any]:
    cid, conv = _ensure_writable_conv(req.convId)
    telem = conv.setdefault("telemetry", {"toolCalls": [], "terminalLogs": [], "backgroundTasks": []})
    tasks = telem.setdefault("backgroundTasks", [])
    found = False
    for t in tasks:
        if t.get("id") == req.id:
            t.update({"status": req.status, "command": req.command, "title": req.title})
            if req.pid:
                t["pid"] = req.pid
            if req.uptime:
                t["uptime"] = req.uptime
            found = True
            break
    if not found:
        tasks.insert(0, {
            "id": req.id, "agentId": req.agentId, "agentName": req.agentName or req.agentId,
            "title": req.title, "command": req.command, "pid": req.pid,
            "status": req.status, "isDaemon": req.isDaemon,
            "uptime": req.uptime or "Active", "startedAt": now_hms(),
        })
    sync_store.save_snapshot_only(cid, conv)
    await ws_hub.broadcast_pulse(cid, "TELEMETRY", {"telemetry": telem, "backgroundTask": tasks[0] if tasks else None})
    return {"status": "ok", "tasks": tasks}


class ToolExecuteRequest(BaseModel):
    agentId: str
    command: str
    convId: Optional[str] = None


@app.post("/api/tools/execute")
async def execute_tool(req: ToolExecuteRequest) -> dict[str, Any]:
    cid, conv = _ensure_writable_conv(req.convId)
    started = time.perf_counter()
    result = await asyncio.to_thread(execute_subagent_command, req.agentId, req.command)
    latency_ms = round((time.perf_counter() - started) * 1000)
    entry = SyncEventStore.compact_tool_entry({
        "id": str(uuid.uuid4()),
        "agentId": req.agentId,
        "agentName": next((a.get("name", req.agentId) for a in conv["agents"] if a.get("id") == req.agentId), req.agentId),
        "tool": req.command,
        "args": {},
        "output": result.get("output", ""),
        "status": "SUCCESS" if result.get("success") else "NOT_EXECUTED",
        "latencyMs": latency_ms,
        "timestamp": now_hms(),
        "createdAtMs": now_ms(),
    })
    telem = conv.setdefault("telemetry", {"toolCalls": [], "terminalLogs": [], "backgroundTasks": []})
    calls = telem.setdefault("toolCalls", [])
    calls.insert(0, entry)
    del calls[25:]
    sync_store.save_snapshot_only(cid, conv)
    await ws_hub.broadcast_pulse(cid, "TELEMETRY", {"telemetry": telem, "telemetryEntry": entry, "toolCall": entry})
    return {
        "status": "executed" if result.get("success") else "not_executed",
        "convId": cid, "latencyMs": latency_ms, **result,
    }


# --- WebSocket Synchronization ---

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    conv_id = websocket.query_params.get("convId") or session_resolver.active_conv_id or "default"
    mapped = session_resolver.ensure_subagent_mapping(conv_id, conversations_store, is_phantom_child_conv)
    if mapped:
        conv_id = mapped["parentConvId"]

    project_id = websocket.query_params.get("projectId")
    if project_id and not _valid_project_id(project_id):
        await websocket.close(code=1008, reason="Invalid project ID")
        return

    conv = conversations_store.get(conv_id)
    if conv is not None:
        owner = conv.get("projectId")
        if project_id and not owner:
            conv["projectId"] = project_id
            sync_store.save_snapshot_only(conv_id, conv)

    generation = websocket.query_params.get("generation")
    raw_after = websocket.query_params.get("afterSeq")
    try:
        after_seq = int(raw_after) if raw_after is not None else None
    except ValueError:
        await websocket.close(code=1008, reason="afterSeq must be a non-negative integer")
        return
    if after_seq is not None and after_seq < 0:
        await websocket.close(code=1008, reason="afterSeq must be a non-negative integer")
        return

    await ws_hub.connect(websocket, conv_id, generation, after_seq, _build_status_payload)
    try:
        while True:
            raw_message = await websocket.receive_text()
            await ws_hub.handle_client_message(websocket, raw_message)
    except WebSocketDisconnect:
        pass
    finally:
        ws_hub.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8780, reload=False)
