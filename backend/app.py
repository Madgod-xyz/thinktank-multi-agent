import os
import sys
import copy
import json
import asyncio
import hashlib
import re
import threading
import time
import urllib.parse
import uuid
from contextlib import asynccontextmanager, suppress
from contextvars import ContextVar
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from bridge import execute_subagent_command
from bridge_transport import flush_outbox_fast
from sync_store import SyncEventStore
from outbox_recovery import outbox_recovery_loop
from governance import (
    DEFAULT_ROLE_CAPS,
    evaluate_review,
    normalize_role_caps,
    normalize_round_limit,
    role_bucket,
    role_usage,
)

STATE_FILE = os.environ.get(
    "THINKTANK_STATE_FILE",
    os.path.join(os.path.expanduser("~"), ".gemini", "config", "think_tank_live_state.json"),
)
SYNC_DB_FILE = os.environ.get(
    "THINKTANK_SYNC_DB", os.path.join(os.path.dirname(STATE_FILE), "think_tank_sync.sqlite3")
)
sync_store = SyncEventStore(os.environ.get("THINKTANK_SYNC_DB", SYNC_DB_FILE))
request_event_id: ContextVar[Optional[str]] = ContextVar("thinktank_event_id", default=None)
request_project_id: ContextVar[Optional[str]] = ContextVar("thinktank_project_id", default=None)

@asynccontextmanager
async def lifespan(_app):
    recovery_task = asyncio.create_task(outbox_recovery_loop(flush_outbox_fast))
    try:
        yield
    finally:
        recovery_task.cancel()
        with suppress(asyncio.CancelledError):
            await recovery_task
        flush_scheduled_state_save()


app = FastAPI(title="Think Tank Matrix - Interactive Engine", version="3.6.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8780", "http://127.0.0.1:8780"],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def idempotency_event_id(request, call_next):
    supplied = request.headers.get("x-thinktank-event-id", "").strip()
    raw_project_id = request.headers.get("x-thinktank-project-id") or request.query_params.get("projectId")
    project_id = raw_project_id.strip() if isinstance(raw_project_id, str) else None
    if project_id and (len(project_id) > 200 or not re.fullmatch(r"[A-Za-z0-9._:-]+", project_id)):
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
            pass  # Let FastAPI return its usual validation response for malformed JSON.

    query_conv_id = request.query_params.get("convId") or request.query_params.get("conv_id")
    if query_conv_id and body_conv_id and query_conv_id != body_conv_id:
        return JSONResponse({"status": "error", "detail": "Conversation IDs in the URL and request body do not match."}, status_code=400)
    conv_id = query_conv_id or body_conv_id
    conv = conversations_store.get(conv_id) if conv_id else None
    owner = conv.get("projectId") if conv else None

    if project_id and owner and owner != project_id:
        return JSONResponse({"status": "error", "detail": "This session belongs to a different project."}, status_code=403)

    if project_id and conv_id and request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.url.path not in {"/api/status", "/status", "/api/host/active-session"}:
        conv = get_or_create_conversation(conv_id)
        owner = conv.get("projectId")
        if owner and owner != project_id:
            return JSONResponse({"status": "error", "detail": "This session belongs to a different project."}, status_code=403)
        if not owner:
            conv["projectId"] = project_id
            sync_store.save_snapshot_only(conv_id, conv)
            schedule_persisted_state_save()

    event_token = request_event_id.set(supplied[:200] or None)
    project_token = request_project_id.set(project_id)
    try:
        if supplied:
            previous = sync_store.find_event_id(supplied[:200])
            if previous:
                if not conv_id or previous["conversation_id"] != conv_id:
                    return JSONResponse({"status": "error", "detail": "Idempotency key is already assigned to a different conversation."}, status_code=409)
                return JSONResponse({
                    "status": "duplicate",
                    "eventId": supplied[:200],
                    "convId": previous["conversation_id"],
                    "seq": previous["seq"],
                })
        return await call_next(request)
    finally:
        request_event_id.reset(event_token)
        request_project_id.reset(project_token)

# Persistent State Definition
default_think_tank_state = {
    "status": "DISCONNECTED",
    "project": "",
    "phase": "در انتظار دادهٔ زنده",
    "round": 0,
    "maxRounds": 50,
    "roleCaps": dict(DEFAULT_ROLE_CAPS),
    "roundStatus": "UNKNOWN",
    "progress": 0,
    "pipelineStage": 1,
    "stageEpochSeq": 0,
    "isClosed": False,
    "runIndex": 1,
    "directive": "",
    "vpsStatus": "UNKNOWN",
    "triageDecision": None,
    "closureReceipt": None,
}

default_proposal = None
default_review = None

# 10 Full Fleet Subagents
default_agents_state = []
"""Historical sample agent rows were removed from runtime defaults; only bridge updates are live data."""


def get_default_agents() -> List[Dict[str, Any]]:
    return []


default_messages_store = []
default_telemetry_store = {
    "toolCalls": [],
    "terminalLogs": [],
    "backgroundTasks": []
}

default_collaborations_store = []

# Multi-Conversation Store
conversations_store: Dict[str, Dict[str, Any]] = {}
subagent_session_map: Dict[str, Dict[str, Any]] = {}
pending_subagent_invokes: Dict[str, List[Dict[str, Any]]] = {}
sessions_by_workspace: Dict[str, Dict[str, Any]] = {}
active_conv_id = "default"
active_conv_workspace_uri: Optional[str] = None


def _normalize_workspace_key(raw: Any) -> Optional[str]:
    if isinstance(raw, (list, tuple)):
        for item in raw:
            norm = _normalize_workspace_key(item)
            if norm:
                return norm
        return None
    if not isinstance(raw, str):
        return None
    val = raw.strip()
    if not val:
        return None
    if val.lower().startswith("file://"):
        val = urllib.parse.unquote(val)
    elif re.match(r"^[A-Za-z]:[\\/]", val):
        val = "file:///" + val.replace("\\", "/")
    elif val.startswith("/"):
        val = "file://" + val
    val = val.replace("\\", "/").rstrip("/")
    if os.name == "nt" or re.match(r"^file:///[A-Za-z]:", val, re.I):
        val = re.sub(r"^(file:///)([A-Za-z]):", lambda m: m.group(1) + m.group(2).lower() + ":", val)
        if os.name == "nt":
            val = val.lower()
    return val or None

def create_empty_conversation(cid: str) -> Dict[str, Any]:
    conv: Dict[str, Any] = {
        "id": cid,
        "thinkTank": dict(default_think_tank_state),
        "proposal": None,
        "review": None,
        "agents": [],
        "messages": [],
        "interactions": [],
        "telemetry": {"toolCalls": [], "terminalLogs": [], "backgroundTasks": []},
        "collaborations": [],
        "subtasks": [],
        "findings": [],
        "fileLocks": [],
    }
    if "--run-" in cid:
        conv["parentConvId"] = cid.split("--run-")[0]
    return conv


_GENERIC_HOST_AGENTS = {"antigravity", "main_agent"}


def has_thinktank_activity(conv: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(conv, dict):
        return False
    tt = conv.get("thinkTank") or {}
    if tt.get("isClosed"):
        return True
    if str(tt.get("project") or "").strip() or str(tt.get("directive") or "").strip():
        return True
    if int(tt.get("runIndex") or 1) > 1 or int(tt.get("stageEpochSeq") or 0) > 0:
        return True
    prop = conv.get("proposal")
    has_prop = bool(prop) and (not isinstance(prop, dict) or prop.get("status") != "NONE")
    if conv.get("messages") or conv.get("subtasks") or has_prop or conv.get("review") or conv.get("findings") or tt.get("triageDecision"):
        return True
    for ag in conv.get("agents") or []:
        if not isinstance(ag, dict):
            continue
        aid = str(ag.get("id") or "").strip().lower()
        if ag.get("verifiedSubagent") or (aid and aid not in _GENERIC_HOST_AGENTS):
            return True
    status = str(tt.get("status") or "DISCONNECTED").upper().strip()
    if status not in {"", "DISCONNECTED", "IDLE"} and not conv.get("_telemetryOnly"):
        if int(tt.get("round") or 0) > 0 or int(tt.get("progress") or 0) > 0:
            return True
        tel = conv.get("telemetry") or {}
        if not (tel.get("toolCalls") or tel.get("terminalLogs") or tel.get("backgroundTasks")):
            return True
    return False


def get_or_create_conversation(conv_id: Optional[str]) -> Dict[str, Any]:
    global conversations_store
    cid = (conv_id or active_conv_id or "default").strip()
    if cid not in conversations_store:
        conversations_store[cid] = create_empty_conversation(cid)
    return conversations_store[cid]


def project_matches(conv: Dict[str, Any], project_id: Optional[str]) -> bool:
    owner = conv.get("projectId")
    if project_id:
        return owner == project_id
    return True


def _resolve_active_session_file() -> str:
    if os.environ.get("THINKTANK_SESSION_FILE"):
        return os.environ["THINKTANK_SESSION_FILE"]
    base = os.environ.get("THINKTANK_HOME") or os.path.join(os.path.expanduser("~"), ".gemini", "config")
    return os.path.join(base, "active_antigravity_session.json")


def _resolve_subagent_links_file() -> str:
    return os.path.join(os.path.dirname(_resolve_active_session_file()), "subagent_links.json")


def _resolve_brain_dir() -> str:
    explicit = os.environ.get("THINKTANK_ANTIGRAVITY_BRAIN_DIR", "").strip()
    if explicit:
        return explicit
    return os.path.join(os.path.expanduser("~"), ".gemini", "antigravity", "brain")


def _read_json_dict(path: str) -> Dict[str, Any]:
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_json_atomic(path: str, data: Dict[str, Any]) -> None:
    if not path:
        return
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp_path = f"{path}.{os.getpid()}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        pass


def _is_phantom_child_conv(conv: Any) -> bool:
    if not isinstance(conv, dict):
        return True
    tt = conv.get("thinkTank") or {}
    return not bool(
        str(tt.get("project") or "").strip()
        or str(tt.get("directive") or "").strip()
        or tt.get("triageDecision")
        or conv.get("messages")
        or conv.get("subtasks")
        or conv.get("findings")
        or conv.get("proposal")
    )


def _extract_role_from_tail(tail_text: str, child_cid: str) -> tuple[bool, Optional[str], Optional[str]]:
    pending: List[tuple[str, str]] = []
    uuid_re = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
    for raw_line in tail_text.splitlines():
        line = raw_line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        for tc in obj.get("tool_calls") or []:
            if isinstance(tc, dict) and str(tc.get("name") or "").endswith("invoke_subagent"):
                args = tc.get("args") or {}
                tname = str(args.get("TypeName") or args.get("typeName") or "").strip().strip("\"'")
                role = str(args.get("Role") or args.get("role") or "").strip().strip("\"'")
                pending.append((tname, role))
        content = str(obj.get("content") or "")
        if "Created the following subagent" in content:
            conv_ids = re.findall(r'"conversationId"\s*:\s*"([0-9a-f-]{36})"', content, re.I)
            uids = list(dict.fromkeys(conv_ids or uuid_re.findall(content)))
            for uid in uids:
                tname, role = pending.pop(0) if pending else ("", "")
                if uid.lower() == child_cid.lower():
                    return True, normalize_agent_id(tname) or normalize_agent_id(role) or None, role or None

    spawn_match = re.search(
        rf'Created the following subagent[\s\S]{{0,700}}?(?:\\"|"|\b){re.escape(child_cid)}(?:\\"|"|\b)',
        tail_text,
        re.I,
    )
    if not spawn_match:
        return False, None, None
    window = tail_text[max(0, spawn_match.start() - 4000):spawn_match.end() + 200]
    t_matches = re.findall(r'"TypeName"\s*:\s*"(?:\\")?([^"\\]+)', window, re.I)
    r_matches = re.findall(r'"Role"\s*:\s*"(?:\\")?([^"\\]+)', window, re.I)
    tname = t_matches[-1].strip() if t_matches else ""
    role = r_matches[-1].strip() if r_matches else ""
    return True, normalize_agent_id(tname) or normalize_agent_id(role) or None, role or None


def _is_non_child_conv_id(cid: str) -> bool:
    return (
        not cid
        or cid == "default"
        or "--run-" in cid
        or (cid in conversations_store and not _is_phantom_child_conv(conversations_store[cid]))
    )


def _discover_parent_from_brain(child_cid: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    if not child_cid or not isinstance(child_cid, str) or _is_non_child_conv_id(child_cid):
        return None, None, None

    links_file = _resolve_subagent_links_file()
    links = _read_json_dict(links_file)
    cached = links.get(child_cid)
    if isinstance(cached, dict):
        cached_parent = str(cached.get("parentConversationId") or "").strip()
        if cached_parent and cached_parent != child_cid:
            return cached_parent, cached.get("roleId") or None, cached.get("roleTitle") or None

    brain_dir = _resolve_brain_dir()
    if not os.path.isdir(brain_dir):
        return None, None, None

    child_transcript = os.path.join(brain_dir, child_cid, ".system_generated", "logs", "transcript.jsonl")
    if os.path.isfile(child_transcript):
        try:
            with open(child_transcript, "rb") as fp:
                head = fp.read(16 * 1024).decode("utf-8", errors="ignore")
            if '"USER_EXPLICIT"' in head or '"USER_INPUT"' in head:
                return None, None, None
        except Exception:
            pass

    candidates: List[str] = []
    seen_dirs: set[str] = {child_cid}
    sess_data = _read_json_dict(_resolve_active_session_file())
    sess_cid = str(sess_data.get("conversationId") or "").strip()
    if sess_cid and sess_cid not in seen_dirs and sess_cid not in links and sess_cid not in subagent_session_map:
        sess_transcript = os.path.join(brain_dir, sess_cid, ".system_generated", "logs", "transcript.jsonl")
        if os.path.isfile(sess_transcript):
            candidates.append(sess_transcript)
            seen_dirs.add(sess_cid)

    recent_transcripts: List[tuple[float, str]] = []
    try:
        for entry_name in os.listdir(brain_dir):
            if entry_name in seen_dirs:
                continue
            tpath = os.path.join(brain_dir, entry_name, ".system_generated", "logs", "transcript.jsonl")
            if os.path.isfile(tpath):
                try:
                    recent_transcripts.append((os.path.getmtime(tpath), tpath))
                except OSError:
                    continue
    except OSError:
        return None, None, None

    recent_transcripts.sort(key=lambda item: item[0], reverse=True)
    for _, tpath in recent_transcripts[:12]:
        candidates.append(tpath)

    tail_bytes = 512 * 1024
    for cand_path in candidates:
        parent_cid = os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(cand_path))))
        if not parent_cid or parent_cid == child_cid:
            continue
        try:
            size = os.path.getsize(cand_path)
            with open(cand_path, "rb") as fp:
                fp.seek(max(0, size - tail_bytes))
                tail_text = fp.read().decode("utf-8", errors="ignore")
        except Exception:
            continue
        if child_cid not in tail_text:
            continue
        matched_spawn, role_id, role_title = _extract_role_from_tail(tail_text, child_cid)
        if not matched_spawn:
            continue
        links[child_cid] = {
            "parentConversationId": parent_cid,
            "roleId": role_id,
            "roleTitle": role_title,
        }
        _write_json_atomic(links_file, links)
        return parent_cid, role_id, role_title

    return None, None, None


def _save_subagent_link(child_cid: str, parent_cid: str, role_id: Optional[str], role_title: Optional[str]) -> None:
    if not child_cid or not parent_cid or child_cid == parent_cid or "--run-" in child_cid:
        return
    links_file = _resolve_subagent_links_file()
    links = _read_json_dict(links_file)
    links[child_cid] = {
        "parentConversationId": parent_cid,
        "roleId": role_id,
        "roleTitle": role_title,
    }
    _write_json_atomic(links_file, links)


def _ensure_subagent_mapping(
    raw_cid: Optional[str],
    parent_cid: Optional[str] = None,
    role_id: Optional[str] = None,
    role_title: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    clean_cid = (raw_cid or "").strip()
    if not clean_cid or clean_cid == "default" or "--run-" in clean_cid:
        return None

    explicit_parent = (parent_cid or "").strip() or None
    if explicit_parent == clean_cid:
        explicit_parent = None
    if not explicit_parent and clean_cid in conversations_store and not _is_phantom_child_conv(conversations_store[clean_cid]):
        subagent_session_map.pop(clean_cid, None)
        return None
    norm_role = normalize_agent_id(role_id) if role_id else ""
    if len(norm_role) > 48 and " " in norm_role:
        norm_role = ""
    clean_title = (role_title or "").strip() or None

    existing = subagent_session_map.get(clean_cid)
    if existing:
        if norm_role and existing.get("roleId") in {"", None, "subagent"}:
            existing["roleId"] = norm_role
        if clean_title and not existing.get("roleTitle"):
            existing["roleTitle"] = clean_title
        if clean_cid in conversations_store and _is_phantom_child_conv(conversations_store[clean_cid]):
            conversations_store.pop(clean_cid, None)
        return existing

    if not explicit_parent:
        disc_parent, disc_role, disc_title = _discover_parent_from_brain(clean_cid)
        if disc_parent and disc_parent != clean_cid:
            explicit_parent = disc_parent
            if not norm_role and disc_role:
                norm_role = normalize_agent_id(disc_role)
            if not clean_title and disc_title:
                clean_title = disc_title

    if not explicit_parent:
        return None

    if explicit_parent in subagent_session_map:
        explicit_parent = subagent_session_map[explicit_parent]["parentConvId"]

    if not norm_role:
        pending_list = pending_subagent_invokes.get(explicit_parent)
        if pending_list:
            now_ts = time.time()
            pending_list[:] = [p for p in pending_list if now_ts - float(p.get("ts") or 0) <= 120.0]
            if pending_list:
                picked = pending_list.pop(0)
                norm_role = normalize_agent_id(picked.get("roleId"))
                if not clean_title:
                    clean_title = picked.get("roleTitle") or None

    entry = {
        "parentConvId": explicit_parent,
        "roleId": norm_role or "subagent",
        "roleTitle": clean_title or "",
    }
    subagent_session_map[clean_cid] = entry
    _save_subagent_link(clean_cid, explicit_parent, entry["roleId"] if entry["roleId"] != "subagent" else None, clean_title)
    if clean_cid in conversations_store and _is_phantom_child_conv(conversations_store[clean_cid]):
        conversations_store.pop(clean_cid, None)
    return entry


ROLE_ALIAS_MAP = {
    "main": "main_agent",
    "root": "main_agent",
    "coordinator": "main_agent",
    "main-agent": "main_agent",
    "antigravity": "main_agent",
    "manager": "team-manager",
    "team_manager": "team-manager",
    "orchestrator": "team-manager",
    "council-architect": "team-manager",
    "council_architect": "team-manager",
    "requirements-auditor": "team-manager",
    "context-memory-curator": "team-manager",
    "data-intelligence-curator": "team-manager",
    "performance-cost-analyst": "team-manager",
    "skill-coach": "team-manager",
    "critic": "council-critic",
    "council_critic": "council-critic",
    "evidence-critical-reviewer": "council-critic",
    "agent-evaluator": "council-critic",
    "reviewer": "code-reviewer",
    "code_reviewer": "code-reviewer",
    "integration-reviewer": "code-reviewer",
    "integration_reviewer": "code-reviewer",
    "security_reviewer": "code-reviewer",
    "qa": "qa-reviewer",
    "qa_reviewer": "qa-reviewer",
    "tester": "qa-reviewer",
    "visual-qa": "qa-reviewer",
    "flutter_a11y_agent": "qa-reviewer",
    "designer": "ui-frontend-designer",
    "designer_solver": "ui-frontend-designer",
    "ui_frontend_designer": "ui-frontend-designer",
    "motion-director": "ui-frontend-designer",
    "backend": "backend-auditor",
    "backend_auditor": "backend-auditor",
    "backend_engineer": "backend-auditor",
    "implementer": "backend-auditor",
    "deep-researcher": "backend-auditor",
    "research-scout": "backend-auditor",
    "seo": "ecommerce_seo_operator",
    "seo_specialist": "ecommerce_seo_operator",
    "ecommerce-seo-operator": "ecommerce_seo_operator",
    "wp": "wp_technical_operator",
    "wordpress": "wp_technical_operator",
    "woocommerce": "wp_technical_operator",
    "wp-technical-operator": "wp_technical_operator",
}


def normalize_agent_id(raw_id: Optional[str]) -> str:
    if not raw_id or not isinstance(raw_id, str):
        return ""
    clean = raw_id.lower().strip()
    clean = re.sub(r"^(?:(?:agent|tt)[_-])+", "", clean)
    if clean in ROLE_ALIAS_MAP:
        return ROLE_ALIAS_MAP[clean]
    dashed = clean.replace("_", "-")
    if dashed in ROLE_ALIAS_MAP:
        return ROLE_ALIAS_MAP[dashed]
    m = re.match(r"^sub(?:agent)?[_-]?(\d+)$", clean)
    if m:
        return f"subagent_{m.group(1)}"
    if "_" in clean and clean not in {"main_agent", "ecommerce_seo_operator", "wp_technical_operator"}:
        return dashed
    return clean


def _extract_mentions_and_citations(text: str) -> tuple[List[str], List[int]]:
    if not isinstance(text, str) or not text:
        return [], []
    mentions: List[str] = []
    for raw in re.findall(r"@([A-Za-z0-9_-]+)", text):
        norm = normalize_agent_id(raw)
        if norm and norm not in mentions:
            mentions.append(norm)
    citations: List[int] = []
    for num in re.findall(r"#(\d+)\b", text):
        try:
            seq_val = int(num)
            if seq_val > 0 and seq_val not in citations:
                citations.append(seq_val)
        except ValueError:
            pass
    return mentions, citations


def _compute_pipeline_state(conv: Dict[str, Any]) -> Dict[str, Any]:
    """Compute the 5-stage closed-loop workflow stage (1..5) and hard-closure flag for the current cycle."""
    tt = conv.get("thinkTank") or {}
    status = str(tt.get("status") or "DISCONNECTED").upper().strip()
    if status in {"COMPLETED", "DONE", "CLOSED"}:
        return {"pipelineStage": 5, "isClosed": True}

    epoch_seq = int(tt.get("stageEpochSeq") or 0)
    interactions = [ev for ev in (conv.get("interactions") or []) if isinstance(ev, dict) and int(ev.get("seq") or 0) > epoch_seq]
    msgs = [m for m in (conv.get("messages") or []) if isinstance(m, dict) and int(m.get("seq") or 0) > epoch_seq]
    events = interactions + msgs
    latest_qa = max(
        (int(e.get("seq") or 0) for e in events if str(e.get("action") or e.get("actionType") or "").upper() in {"QA_DISPATCH", "REVIEW_QUERY", "QA_REPORT"}),
        default=0,
    )
    latest_fix = max(
        (int(e.get("seq") or 0) for e in events if str(e.get("action") or e.get("actionType") or "").upper() == "WORKER_FIX"),
        default=0,
    )
    latest_defect = max(
        (int(e.get("seq") or 0) for e in events if str(e.get("action") or e.get("actionType") or "").upper() in {"RETURN_DEFECT", "INTERROGATE", "CRITIQUE"}),
        default=0,
    )
    has_open_defect = any(
        str(e.get("action") or "").upper() in {"RETURN_DEFECT", "INTERROGATE"} and not e.get("resolved")
        for e in interactions
    )
    if latest_qa > latest_defect and (latest_qa >= latest_fix or not has_open_defect):
        stage = 4
    elif latest_fix > 0 and latest_fix >= latest_defect:
        stage = 3
    elif latest_defect > 0 or has_open_defect:
        stage = 2
    else:
        stage = 1
    return {"pipelineStage": stage, "isClosed": False}


def _sync_pipeline_fields(conv: Dict[str, Any]) -> Dict[str, Any]:
    state = _compute_pipeline_state(conv)
    has_sess = has_thinktank_activity(conv)
    tt = conv.setdefault("thinkTank", dict(default_think_tank_state))
    tt["pipelineStage"] = state["pipelineStage"]
    tt["isClosed"] = state["isClosed"]
    tt["hasSession"] = has_sess
    return {**state, "hasSession": has_sess}


VALID_ORIGINS = {"subagent", "main-proxy", "user"}


def _normalize_origin(msg: Dict[str, Any], conv: Dict[str, Any]) -> str:
    raw = str(msg.get("origin") or "").strip().lower()
    sub_cid = str(msg.get("subagentConvId") or "").strip()
    conv_cid = str(conv.get("id") or msg.get("convId") or "").strip()
    has_child_sub = bool(sub_cid and sub_cid != conv_cid)

    if raw == "user":
        return "user"
    if raw == "subagent":
        return "subagent" if has_child_sub else "main-proxy"
    if raw == "main-proxy":
        return "main-proxy"
    if msg.get("isOperator") or normalize_agent_id(msg.get("senderRole") or msg.get("senderCode")) in {"user", "human", "operator", "owner"}:
        return "user"
    if has_child_sub:
        return "subagent"
    return "main-proxy"


def _require_case_open(conv: Dict[str, Any]) -> None:
    if bool((conv.get("thinkTank") or {}).get("isClosed")):
        raise HTTPException(
            status_code=409,
            detail="Case is closed and read-only. Reopen the case or start a new case first.",
        )


def _enforce_role_cap(
    conv: Dict[str, Any],
    sender_role: Optional[str],
    is_review: bool = False,
    review_id: Optional[str] = None,
) -> None:
    bucket = role_bucket(sender_role)
    if not bucket:
        return
    if is_review and bucket in {"main", "manager"} and isinstance(review_id, str) and bool(review_id.strip()):
        return
    caps = normalize_role_caps((conv.get("thinkTank") or {}).get("roleCaps"))
    usage = role_usage(conv.get("messages") or [])
    if usage.get(bucket, 0) >= caps.get(bucket, 50):
        raise HTTPException(
            status_code=429,
            detail=f"The {bucket} message cap ({caps[bucket]}) has been reached for this session.",
        )


def _compute_origin_counts(conv: Dict[str, Any]) -> Dict[str, int]:
    counts = {"subagent": 0, "main-proxy": 0, "user": 0}
    for m in conv.get("messages") or []:
        if not isinstance(m, dict):
            continue
        origin = _normalize_origin(m, conv)
        counts[origin] = counts.get(origin, 0) + 1
    return counts


def _rebuild_file_locks(conv: Dict[str, Any]) -> List[Dict[str, Any]]:
    locks: List[Dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for st in conv.get("subtasks") or []:
        if not isinstance(st, dict):
            continue
        if str(st.get("status") or "").upper() in {"COMPLETED", "DONE"}:
            continue
        owner = normalize_agent_id(st.get("assignee", "")) or str(st.get("assignee") or "").strip()
        work_item_id = st.get("id")
        for raw_path in st.get("lockedFiles") or []:
            path = str(raw_path or "").strip().replace("\\", "/")
            if not path:
                continue
            key = (path.lower(), owner)
            if key in seen:
                continue
            seen.add(key)
            locks.append({"path": path, "owner": owner, "workItemId": work_item_id})
    conv["fileLocks"] = locks
    return locks


def _find_finding(conv: Dict[str, Any], finding_id: Optional[str]) -> Optional[Dict[str, Any]]:
    target = str(finding_id or "").strip().upper()
    if not target:
        return None
    for f in conv.get("findings") or []:
        if isinstance(f, dict) and str(f.get("id") or "").strip().upper() == target:
            return f
    return None


def _next_finding_id(conv: Dict[str, Any]) -> str:
    max_num = 0
    for f in conv.get("findings") or []:
        if not isinstance(f, dict):
            continue
        m = re.match(r"^F-(\d+)$", str(f.get("id") or "").strip().upper())
        if m:
            max_num = max(max_num, int(m.group(1)))
    return f"F-{max_num + 1:02d}"


VALID_REQUEST_TYPES = {
    "REWRITE",
    "REFERRAL",
    "QUESTION",
    "INTERROGATION",
    "DEFECT_RETURN",
    "CRITIQUE",
    "QA_REPORT",
    "PEER_SYNC",
    "DECISION",
    "MESSAGE",
}

ACTION_REQUEST_TYPE_MAP = {
    "WORKER_FIX": "REWRITE",
    "REVISION_REQUESTED": "REWRITE",
    "REWRITE": "REWRITE",
    "DELEGATE": "REFERRAL",
    "ASSIGN_SUBTASK": "REFERRAL",
    "SUBTASK_UPDATE": "REFERRAL",
    "REFERRAL": "REFERRAL",
    "REVIEW_QUERY": "QUESTION",
    "QUESTION": "QUESTION",
    "INTERROGATE": "INTERROGATION",
    "INTERROGATE_REPLY": "INTERROGATION",
    "INTERROGATION": "INTERROGATION",
    "RETURN_DEFECT": "DEFECT_RETURN",
    "QA_REOPEN": "DEFECT_RETURN",
    "DEFECT_RETURN": "DEFECT_RETURN",
    "CRITIQUE": "CRITIQUE",
    "QA_DISPATCH": "QA_REPORT",
    "QA_REPORT": "QA_REPORT",
    "PEER_SYNC": "PEER_SYNC",
    "DECISION": "DECISION",
    "DECIDE": "DECISION",
    "APPROVE": "DECISION",
    "PROPOSAL": "DECISION",
    "COMPLETE": "DECISION",
    "GOVERNANCE": "DECISION",
    "MESSAGE": "MESSAGE",
}


def _infer_request_type(action_upper: str, explicit: Optional[str] = None) -> str:
    clean = str(explicit or "").strip().upper()
    if clean in VALID_REQUEST_TYPES:
        return clean
    return ACTION_REQUEST_TYPE_MAP.get(str(action_upper or "MESSAGE").upper().strip(), "MESSAGE")


def append_message(
    conv: Dict[str, Any],
    msg: Dict[str, Any],
    *,
    action_type: Optional[str] = None,
    severity: Optional[str] = None,
    label: Optional[str] = None,
) -> Dict[str, Any]:
    """Attach monotonic #seq number, parse @mentions/#citations, track defect resolution, and log graph interactions."""
    msgs = conv.setdefault("messages", [])
    next_seq = max((int(m.get("seq") or 0) for m in msgs if isinstance(m, dict)), default=0) + 1
    msg["seq"] = int(msg.get("seq") or next_seq)
    msg.setdefault("createdAtMs", int(time.time() * 1000))
    if not msg.get("timestamp"):
        msg["timestamp"] = time.strftime("%H:%M:%S")
    msg["origin"] = _normalize_origin(msg, conv)

    content = str(msg.get("content") or "")
    mentions, citations = _extract_mentions_and_citations(content)
    explicit_recip = normalize_agent_id(msg.get("recipientRole") or msg.get("recipientCode") or msg.get("recipient"))
    if explicit_recip and explicit_recip not in {"user", "operator", "council", "all"} and explicit_recip not in mentions:
        mentions.insert(0, explicit_recip)

    msg["mentions"] = mentions
    msg["citations"] = citations
    if action_type:
        msg["actionType"] = action_type
    elif not msg.get("actionType"):
        if msg.get("critique"):
            msg["actionType"] = "CRITIQUE"
        elif msg.get("question"):
            msg["actionType"] = "QUESTION"
        else:
            msg["actionType"] = "MESSAGE"
    if severity:
        msg["severity"] = severity

    action_upper = str(msg.get("actionType") or "MESSAGE").upper()
    msg["requestType"] = _infer_request_type(action_upper, msg.get("requestType"))
    conv_closed = str((conv.get("thinkTank") or {}).get("status") or "").upper() in {"COMPLETED", "DONE", "CLOSED"}
    msg["resolved"] = bool(msg.get("resolved", False) or conv_closed)

    raw_chan = str(msg.get("channel") or "MAIN").upper().strip()
    if raw_chan == "ALL":
        raw_chan = "MAIN"
    msg["channel"] = raw_chan
    msgs.append(msg)

    sender_id = normalize_agent_id(msg.get("senderRole") or msg.get("senderCode"))
    interactions = conv.setdefault("interactions", [])
    msg_finding_id = str(msg.get("findingId") or "").strip().upper() or None

    # Closed-loop resolution: worker fixes close open defects sent to that worker; QA PASS closes QA checks
    if action_upper == "WORKER_FIX" and sender_id:
        for ev in interactions:
            if isinstance(ev, dict) and str(ev.get("action") or "").upper() in {"RETURN_DEFECT", "INTERROGATE", "CRITIQUE"}:
                if msg_finding_id and ev.get("findingId") and str(ev.get("findingId")).upper() != msg_finding_id:
                    continue
                if normalize_agent_id(ev.get("to")) == sender_id:
                    ev["resolved"] = True
        for prev_m in msgs:
            if isinstance(prev_m, dict) and prev_m is not msg:
                if msg_finding_id and prev_m.get("findingId") and str(prev_m.get("findingId")).upper() != msg_finding_id:
                    continue
                prev_act = str(prev_m.get("actionType") or "").upper()
                if prev_act in {"RETURN_DEFECT", "INTERROGATE", "CRITIQUE"}:
                    prev_to = normalize_agent_id(prev_m.get("recipientRole") or prev_m.get("recipientCode") or prev_m.get("recipient"))
                    if prev_to == sender_id or sender_id in (prev_m.get("mentions") or []):
                        prev_m["resolved"] = True
    elif action_upper == "QA_REPORT" and str(msg.get("result") or "").upper() == "PASS":
        qa_clear_actions = {"QA_DISPATCH", "REVIEW_QUERY", "WORKER_FIX", "RETURN_DEFECT", "INTERROGATE", "CRITIQUE"}
        for ev in interactions:
            if isinstance(ev, dict) and str(ev.get("action") or "").upper() in qa_clear_actions:
                if msg_finding_id and ev.get("findingId") and str(ev.get("findingId")).upper() != msg_finding_id:
                    continue
                ev["resolved"] = True
        for prev_m in msgs:
            if isinstance(prev_m, dict) and str(prev_m.get("actionType") or "").upper() in qa_clear_actions:
                if msg_finding_id and prev_m.get("findingId") and str(prev_m.get("findingId")).upper() != msg_finding_id:
                    continue
                prev_m["resolved"] = True
        msg["resolved"] = True

    if sender_id and not msg.get("isOperator") and mentions:
        for target_id in mentions:
            if not target_id or target_id == sender_id or target_id in {"user", "operator"}:
                continue
            ev_row = {
                "seq": msg["seq"],
                "from": sender_id,
                "to": target_id,
                "action": action_upper,
                "requestType": msg["requestType"],
                "channel": msg["channel"],
                "severity": msg.get("severity"),
                "label": label or "",
                "summary": content[:180],
                "timestamp": msg["timestamp"],
                "resolved": bool(msg.get("resolved", False) or conv_closed),
                "origin": msg["origin"],
            }
            if msg_finding_id:
                ev_row["findingId"] = msg_finding_id
            if msg.get("workItemId"):
                ev_row["workItemId"] = msg.get("workItemId")
            if msg.get("result"):
                ev_row["result"] = msg.get("result")
            interactions.append(ev_row)
        if len(interactions) > 500:
            del interactions[:-500]
    _sync_pipeline_fields(conv)
    return msg


def build_interaction_graph(conv: Dict[str, Any]) -> Dict[str, Any]:
    """Aggregate directed edges for the Swarm-style collaboration & interrogation graph."""
    interactions = conv.get("interactions") or []
    edge_map: Dict[tuple, Dict[str, Any]] = {}
    for ev in interactions:
        if not isinstance(ev, dict):
            continue
        src = normalize_agent_id(ev.get("from"))
        dst = normalize_agent_id(ev.get("to"))
        kind = str(ev.get("action") or "MESSAGE").upper()
        if not src or not dst or src == dst:
            continue
        key = (src, dst, kind)
        item = edge_map.setdefault(key, {
            "from": src,
            "to": dst,
            "action": kind,
            "channel": ev.get("channel", "SYNC"),
            "count": 0,
            "openCount": 0,
            "resolved": True,
            "lastSeq": 0,
            "seqs": [],
            "label": ev.get("label") or "",
        })
        item["count"] += 1
        if not ev.get("resolved"):
            item["openCount"] += 1
            item["resolved"] = False
        seq_num = int(ev.get("seq") or 0)
        if seq_num > item["lastSeq"]:
            item["lastSeq"] = seq_num
        if seq_num and seq_num not in item["seqs"]:
            item["seqs"].append(seq_num)
    return {
        "edges": list(edge_map.values()),
        "totalEvents": len(interactions),
        "maxSeq": max((int(m.get("seq") or 0) for m in conv.get("messages", []) if isinstance(m, dict)), default=0),
    }


def normalize_conversation(cid: str, conv: Dict[str, Any]) -> bool:
    """Fill governance defaults, backfill message #seq, and deduplicate agents."""
    changed = False
    tt = conv.setdefault("thinkTank", dict(default_think_tank_state))
    if "roleCaps" not in tt:
        tt["roleCaps"] = dict(DEFAULT_ROLE_CAPS)
        tt["maxRounds"] = 50
        changed = True
    else:
        normalized = normalize_role_caps(tt.get("roleCaps"))
        if tt.get("roleCaps") != normalized:
            tt["roleCaps"] = normalized
            changed = True
        normalized_rounds = normalize_round_limit(tt.get("maxRounds", 50))
        if tt.get("maxRounds") != normalized_rounds:
            tt["maxRounds"] = normalized_rounds
            changed = True
    if "review" not in conv:
        conv["review"] = default_review
        changed = True
    msgs = conv.setdefault("messages", [])
    conv.setdefault("telemetry", {"toolCalls": [], "terminalLogs": [], "backgroundTasks": []})
    conv.setdefault("collaborations", [])
    conv.setdefault("interactions", [])
    conv.setdefault("subtasks", [])
    conv.setdefault("proposal", None)
    if "findings" not in conv or not isinstance(conv.get("findings"), list):
        conv["findings"] = []
        changed = True
    if "fileLocks" not in conv or not isinstance(conv.get("fileLocks"), list):
        conv["fileLocks"] = []
        changed = True
    if "triageDecision" not in tt:
        tt["triageDecision"] = None
        changed = True
    if "closureReceipt" not in tt:
        tt["closureReceipt"] = None
        changed = True
    if not conv.get("parentConvId") and ("--run-" in cid or int(tt.get("runIndex") or 1) > 1):
        conv["parentConvId"] = cid.split("--run-")[0]
        changed = True
    if not tt.get("runIndex"):
        m_run = re.search(r"--run-(\d+)$", cid)
        tt["runIndex"] = int(m_run.group(1)) if m_run else 1
        changed = True
    else:
        tt["runIndex"] = int(tt["runIndex"])
    if not conv["fileLocks"] and conv.get("subtasks"):
        _rebuild_file_locks(conv)

    for idx_m, m in enumerate(msgs, start=1):
        if isinstance(m, dict) and not m.get("seq"):
            m["seq"] = idx_m
            changed = True

    # Deduplicate and canonicalize dynamic subagent fleet
    raw_agents = conv.setdefault("agents", [])
    merged_agents: Dict[str, Dict[str, Any]] = {}
    for ag in raw_agents:
        if not isinstance(ag, dict):
            continue
        canon_id = normalize_agent_id(ag.get("id", "")) or normalize_agent_id(ag.get("code", ""))
        if not canon_id or canon_id in {"operator", "user"}:
            continue
        if canon_id not in merged_agents:
            merged_agents[canon_id] = {**ag, "id": canon_id}
            if "collaboratingWith" in merged_agents[canon_id]:
                merged_agents[canon_id]["collaboratingWith"] = [
                    normalize_agent_id(c) for c in merged_agents[canon_id]["collaboratingWith"] if normalize_agent_id(c) and normalize_agent_id(c) != canon_id
                ]
        else:
            target = merged_agents[canon_id]
            for k, v in ag.items():
                if v is not None:
                    if k == "collaboratingWith" and isinstance(v, list):
                        existing_cw = target.setdefault("collaboratingWith", [])
                        for item in v:
                            clean_item = normalize_agent_id(item)
                            if clean_item and clean_item != canon_id and clean_item not in existing_cw:
                                existing_cw.append(clean_item)
                    elif k in {"tool", "activeTool", "thought", "status", "name", "role", "code", "icon", "task", "currentTask"} and v:
                        if k == "name" and target.get("name") and not target.get("name", "").startswith("sub"):
                            continue
                        target[k] = v
    if len(merged_agents) != len(raw_agents):
        conv["agents"] = list(merged_agents.values())
        changed = True

    prev_stage = tt.get("pipelineStage")
    prev_closed = tt.get("isClosed")
    pstate = _sync_pipeline_fields(conv)
    if pstate["pipelineStage"] != prev_stage or pstate["isClosed"] != prev_closed:
        changed = True

    return changed

def get_conv_sort_ts(c: Dict[str, Any]) -> float:
    last_msg = c.get("messages", [])[-1].get("timestamp") if c.get("messages") else None
    last_tool = c.get("telemetry", {}).get("toolCalls", [])[-1].get("timestamp") if c.get("telemetry", {}).get("toolCalls") else None
    raw = c.get("updatedAt") or c.get("updated_at") or last_msg or last_tool or 0
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        try:
            return float(raw)
        except ValueError:
            return 1000.0
    return 0.0


def load_persisted_state():
    global conversations_store, active_conv_id, subagent_session_map
    subagent_session_map = {}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                sfile_data = json.load(f)
            raw_map = sfile_data.get("subagentSessionMap")
            if isinstance(raw_map, dict):
                subagent_session_map = {
                    str(k): dict(v) for k, v in raw_map.items()
                    if isinstance(v, dict) and v.get("parentConvId") and v.get("roleId")
                }
        except Exception:
            pass
    for child_cid, link_info in _read_json_dict(_resolve_subagent_links_file()).items():
        if child_cid not in subagent_session_map and isinstance(link_info, dict) and link_info.get("parentConversationId"):
            subagent_session_map[child_cid] = {
                "parentConvId": str(link_info["parentConversationId"]).strip(),
                "roleId": normalize_agent_id(link_info.get("roleId")) or "subagent",
                "roleTitle": str(link_info.get("roleTitle") or "").strip(),
            }
    def _prune_loaded_subagent_mappings() -> None:
        links_file = _resolve_subagent_links_file()
        links = _read_json_dict(links_file)
        links_dirty = False
        for child_cid in list(subagent_session_map.keys()):
            if _is_non_child_conv_id(child_cid):
                subagent_session_map.pop(child_cid, None)
            elif child_cid in conversations_store and _is_phantom_child_conv(conversations_store[child_cid]):
                conversations_store.pop(child_cid, None)
        for child_cid in list(links.keys()):
            if _is_non_child_conv_id(child_cid):
                links.pop(child_cid, None)
                links_dirty = True
        if links_dirty:
            _write_json_atomic(links_file, links)

    durable = sync_store.load_conversations()
    if durable:
        conversations_store = {cid: row["snapshot"] for cid, row in durable.items()}
        _prune_loaded_subagent_mappings()
        for cid, snapshot in conversations_store.items():
            if normalize_conversation(cid, snapshot):
                sync_store.commit(
                    conversation_id=cid,
                    event_id=f"thinktank-governance-migration-{uuid.uuid4()}",
                    event_type="GOVERNANCE_DEFAULTS_MIGRATED",
                    payload={"roleCapsDefault": 50, "roundCapDefault": 50},
                    snapshot=snapshot,
                    source="migration",
                )
        if active_conv_id in subagent_session_map:
            active_conv_id = subagent_session_map[active_conv_id]["parentConvId"]
        if active_conv_id not in conversations_store:
            active_conv_id = next(iter(conversations_store), "default")
        for tier in (0, 1, 2):
            # Tier 0: plain non-ThinkTank, Tier 1: closed ThinkTank, Tier 2: unclosed ThinkTank (highest priority)
            for cid, snapshot in sorted(conversations_store.items(), key=lambda kv: get_conv_sort_ts(kv[1])):
                has_tt = has_thinktank_activity(snapshot)
                is_closed = bool((snapshot.get("thinkTank") or {}).get("isClosed"))
                snap_tier = 2 if (has_tt and not is_closed) else (1 if has_tt else 0)
                if snap_tier != tier:
                    continue
                norm_ws = _normalize_workspace_key(snapshot.get("workspaceUri"))
                if norm_ws and cid != "default" and "--run-" not in cid and not snapshot.get("isArchivedRun"):
                    sessions_by_workspace[norm_ws] = {
                        "conversationId": cid,
                        "projectId": snapshot.get("projectId"),
                        "timestamp": get_conv_sort_ts(snapshot),
                    }
        active = get_or_create_conversation(active_conv_id)
        return active["thinkTank"], active["proposal"], active["agents"], active["messages"], active["telemetry"], active["collaborations"]

    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                active_conv_id = data.get("activeConversationId", "default")
                loaded_convs = data.get("conversations", {})
                if loaded_convs:
                    conversations_store = loaded_convs
                _prune_loaded_subagent_mappings()
                if active_conv_id in subagent_session_map:
                    active_conv_id = subagent_session_map[active_conv_id]["parentConvId"]
                
                # Also load root fallback into active conversation
                conv = get_or_create_conversation(active_conv_id)
                if "thinkTank" in data:
                    conv["thinkTank"].update(data["thinkTank"])
                    if "roleCaps" not in data["thinkTank"]:
                        conv["thinkTank"]["roleCaps"] = dict(DEFAULT_ROLE_CAPS)
                        conv["thinkTank"]["maxRounds"] = 50
                if "proposal" in data:
                    conv["proposal"] = data["proposal"]
                if "agents" in data:
                    conv["agents"] = data["agents"]
                if "messages" in data:
                    conv["messages"] = data["messages"]
                if "telemetry" in data:
                    conv["telemetry"] = data["telemetry"]
                if "collaborations" in data:
                    conv["collaborations"] = data["collaborations"]

                for cid, snapshot in conversations_store.items():
                    normalize_conversation(cid, snapshot)
                    sync_store.commit(
                        conversation_id=cid,
                        event_id=f"legacy-import-{cid}",
                        event_type="SNAPSHOT_IMPORTED",
                        payload={"source": "legacy-state"},
                        snapshot=snapshot,
                        source="migration",
                    )
                return (
                    conv["thinkTank"],
                    conv["proposal"],
                    conv["agents"],
                    conv["messages"],
                    conv["telemetry"],
                    conv["collaborations"]
                )
        except Exception as e:
            print(f"[State] Error loading {STATE_FILE}: {e}")
            
    conv = get_or_create_conversation(active_conv_id)
    return conv["thinkTank"], conv["proposal"], conv["agents"], conv["messages"], conv["telemetry"], conv["collaborations"]

_state_save_lock = threading.RLock()
_state_save_timer: Optional[threading.Timer] = None
_state_dirty = False


def save_persisted_state():
    global _state_dirty, _state_save_timer
    needs_retry = False
    with _state_save_lock:
        if _state_save_timer is not None:
            _state_save_timer.cancel()
            _state_save_timer = None
        _state_dirty = False
        target_file = STATE_FILE
        try:
            os.makedirs(os.path.dirname(target_file), exist_ok=True)
            active_conv = conversations_store.get(active_conv_id) or create_empty_conversation(active_conv_id)
            convs_snapshot = copy.deepcopy(dict(conversations_store))
            for c_obj in convs_snapshot.values():
                if isinstance(c_obj, dict) and isinstance(c_obj.get("telemetry"), dict):
                    c_obj["telemetry"] = SyncEventStore.compact_telemetry_store(c_obj["telemetry"], max_calls=25)
            payload_text = json.dumps({
                "activeConversationId": active_conv_id,
                "conversations": convs_snapshot,
                "subagentSessionMap": dict(subagent_session_map),
                "thinkTank": active_conv["thinkTank"],
                "proposal": active_conv["proposal"],
                "agents": active_conv["agents"],
                "messages": active_conv["messages"],
                "telemetry": active_conv["telemetry"],
                "collaborations": active_conv.get("collaborations", default_collaborations_store),
                "updatedAt": time.time(),
            }, ensure_ascii=False, separators=(",", ":"))
            tmp_file = f"{target_file}.{os.getpid()}.{threading.get_ident()}.tmp"
            with open(tmp_file, "w", encoding="utf-8") as f:
                f.write(payload_text)
            os.replace(tmp_file, target_file)
        except RuntimeError:
            if threading.current_thread() is not threading.main_thread():
                needs_retry = True
        except Exception as e:
            print(f"[State] Error saving {target_file}: {e}")
    if needs_retry:
        schedule_persisted_state_save(0.3)


def _flush_timer_callback(expected_file: str) -> None:
    global _state_save_timer
    with _state_save_lock:
        _state_save_timer = None
        if STATE_FILE != expected_file:
            return
    save_persisted_state()


def schedule_persisted_state_save(delay: float = 4.0) -> None:
    """Coalesce high-frequency state dumps off the FastAPI event loop."""
    global _state_dirty, _state_save_timer
    with _state_save_lock:
        _state_dirty = True
        if _state_save_timer is None:
            timer = threading.Timer(delay, _flush_timer_callback, args=(STATE_FILE,))
            timer.daemon = True
            _state_save_timer = timer
            timer.start()


def flush_scheduled_state_save() -> None:
    with _state_save_lock:
        dirty = _state_dirty
        if _state_save_timer is not None:
            _state_save_timer.cancel()
            _state_save_timer = None
    if dirty:
        save_persisted_state()

think_tank_state, current_proposal, agents_state, messages_store, telemetry_store, collaborations_store = load_persisted_state()

def check_and_reload_state(conv_id: Optional[str] = None):
    # SQLite is the event/snapshot source of truth. File mtime polling could
    # replace newer in-memory state with an old external write and has been removed.
    return None


def require_conversation_id(conv_id: Optional[str]) -> str:
    cid = (conv_id or "").strip()
    if not cid or cid == "default":
        raise HTTPException(
            status_code=400,
            detail="An explicit Antigravity conversation ID is required for writes.",
        )
    if not project_matches(conversations_store.get(cid, {}), request_project_id.get()):
        raise HTTPException(status_code=403, detail="This session is not assigned to the active project.")
    return cid


class ConnectionManager:
    SEND_TIMEOUT_SECONDS = 1.0

    def __init__(self):
        self.active_connections: Dict[WebSocket, str] = {}
        self.lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, conv_id: str, generation: Optional[str], after_seq: Optional[int]):
        await websocket.accept()
        async with self.lock:
            self.active_connections[websocket] = conv_id
            conv = get_or_create_conversation(conv_id)
            cursor = sync_store.cursor(conv_id)
            try:
                await self._send(websocket, {"type": "SYNC_READY", "convId": conv_id, **cursor})
                if generation is not None and after_seq is not None:
                    result = sync_store.replay(conv_id, generation, after_seq)
                    if result["status"] == "replay":
                        await self._send(websocket, {
                            "type": "SYNC_REPLAY",
                            "convId": conv_id,
                            "generation": result["generation"],
                            "seq": result["seq"],
                            "events": [self._event_to_wire(event) for event in result["events"]],
                        })
                        return
                snapshot = sync_store.snapshot(conv_id) or conv
                pstate = _sync_pipeline_fields(conv)
                await self._send(websocket, {
                    "type": "SYNC_SNAPSHOT",
                    "convId": conv_id,
                    "parentConvId": conv.get("parentConvId") or conv_id.split("--run-")[0],
                    "hasSession": pstate["hasSession"],
                    "isClosed": pstate["isClosed"],
                    "conversationsList": _build_conversations_list(conv_id, include_target_if_in_store=conv_id in conversations_store),
                    "generation": cursor["generation"],
                    "seq": cursor["seq"],
                    "updatedAt": cursor["updated_at"],
                    "snapshot": snapshot,
                })
            except Exception:
                self.disconnect(websocket)
                try:
                    await websocket.close()
                except Exception:
                    pass
                raise

    async def _send(self, websocket: WebSocket, message: dict) -> None:
        await asyncio.wait_for(websocket.send_json(message), timeout=self.SEND_TIMEOUT_SECONDS)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.pop(websocket, None)

    @staticmethod
    def _event_to_wire(event: dict) -> dict:
        payload = dict(event["payload"])
        payload.update({
            "convId": event["conversation_id"],
            "generation": event["generation"],
            "seq": event["seq"],
            "eventId": event["event_id"],
        })
        return payload

    async def broadcast(self, data: dict):
        conv_id = data.get("convId")
        if not conv_id:
            return
        conv = get_or_create_conversation(conv_id)
        event_id = request_event_id.get() or data.get("eventId") or str(uuid.uuid4())
        event_type = data.get("type", "STATE_UPDATE")
        async with self.lock:
            # Serialize durable commit with subscribe + snapshot/replay setup.
            # Otherwise a commit can land after the cursor is read but before
            # its snapshot is sent, producing a snapshot whose cursor lags it.
            envelope = sync_store.commit(
                conversation_id=conv_id,
                event_id=event_id,
                event_type=event_type,
                payload=data,
                snapshot=conv,
                source="api",
            )
            if envelope["duplicate"]:
                return
            message = self._event_to_wire(envelope)
            for connection, subscribed_conv in list(self.active_connections.items()):
                if subscribed_conv != conv_id:
                    continue
                try:
                    await self._send(connection, message)
                except Exception:
                    self.disconnect(connection)

    async def broadcast_transient(self, data: dict):
        """Deliver ephemeral updates to live WS subscribers without advancing SQLite seq or bloating events."""
        conv_id = data.get("convId")
        if not conv_id:
            return
        message = dict(data)
        message.setdefault("convId", conv_id)
        async with self.lock:
            for connection, subscribed_conv in list(self.active_connections.items()):
                if subscribed_conv != conv_id:
                    continue
                try:
                    await self._send(connection, message)
                except Exception:
                    self.disconnect(connection)

manager = ConnectionManager()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    conv_id = websocket.query_params.get("convId") or active_conv_id or "default"
    mapped = _ensure_subagent_mapping(conv_id)
    if mapped:
        conv_id = mapped["parentConvId"]
    project_id = websocket.query_params.get("projectId")
    if project_id and (len(project_id) > 200 or not re.fullmatch(r"[A-Za-z0-9._:-]+", project_id)):
        await websocket.close(code=1008, reason="Invalid project ID")
        return
    conv = get_or_create_conversation(conv_id)
    owner = conv.get("projectId")
    if project_id and not owner:
        conv["projectId"] = project_id
        sync_store.save_snapshot_only(conv_id, conv)
        schedule_persisted_state_save()
    elif project_id and owner and owner != project_id:
        await websocket.close(code=1008, reason="This session belongs to a different project")
        return
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
    await manager.connect(websocket, conv_id, generation, after_seq)
    try:
        while True:
            raw_message = await websocket.receive_text()
            try:
                message = json.loads(raw_message)
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(message, dict) and message.get("type") == "SYNC_PING":
                await manager._send(websocket, {
                    "type": "SYNC_PONG",
                    "clientTime": message.get("clientTime"),
                    "serverTime": time.time(),
                })
    except WebSocketDisconnect:
        manager.disconnect(websocket)


ROLE_CATALOG_FILE = os.path.join(os.path.dirname(__file__), "role_catalog.json")
_ROLE_CATALOG_CACHE: Optional[tuple[float, List[Dict[str, Any]]]] = None


def load_role_catalog():
    global _ROLE_CATALOG_CACHE
    if os.path.exists(ROLE_CATALOG_FILE):
        try:
            mtime = os.path.getmtime(ROLE_CATALOG_FILE)
            if _ROLE_CATALOG_CACHE and _ROLE_CATALOG_CACHE[0] == mtime:
                return _ROLE_CATALOG_CACHE[1]
            with open(ROLE_CATALOG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                _ROLE_CATALOG_CACHE = (mtime, data)
                return data
        except Exception:
            pass
    return []

@app.get("/roles")
@app.get("/api/roles")
def get_roles():
    return {"roles": load_role_catalog()}


def is_meaningful_conversation(cid: str, conv: Dict[str, Any], current_cid: str) -> bool:
    if cid == current_cid:
        return True
    if cid in subagent_session_map:
        return False
    tt = conv.get("thinkTank", {})
    project = (tt.get("project") or "").strip()
    directive = (tt.get("directive") or "").strip()
    messages = conv.get("messages", [])
    subtasks = conv.get("subtasks", [])
    proposal = conv.get("proposal")
    has_prop = bool(proposal) and (not isinstance(proposal, dict) or proposal.get("status") != "NONE")
    findings = conv.get("findings", [])
    run_index = int(tt.get("runIndex") or 1)
    return bool(
        project
        or directive
        or messages
        or subtasks
        or has_prop
        or findings
        or tt.get("triageDecision")
        or run_index > 1
        or "--run-" in cid
    )


def _build_conv_row(cid: str, c: Dict[str, Any], target_cid: str) -> Dict[str, Any]:
    tt = c.get("thinkTank", {})
    last_msg_ts = c.get("messages", [])[-1].get("timestamp") if c.get("messages") else None
    last_tool_ts = c.get("telemetry", {}).get("toolCalls", [])[-1].get("timestamp") if c.get("telemetry", {}).get("toolCalls") else None
    updated_at = c.get("updatedAt") or c.get("updated_at") or last_msg_ts or last_tool_ts or 0
    is_current = (cid == target_cid)
    p_name = tt.get("project")
    if not p_name:
        p_name = "مکالمه جاری" if is_current else "اتاق فکر بدون عنوان"
    is_closed = bool(tt.get("isClosed")) or str(tt.get("status") or "").upper() in {"COMPLETED", "DONE", "CLOSED"}
    return {
        "id": cid,
        "isCurrent": is_current,
        "projectScope": "bound" if c.get("projectId") else "unassigned",
        "project": p_name,
        "directive": tt.get("directive", "اتاق فکر فعال"),
        "phase": tt.get("phase", "اتاق فکر فعال"),
        "round": tt.get("round", 1 if is_current else 0),
        "maxRounds": tt.get("maxRounds", 50),
        "progress": tt.get("progress", 0),
        "status": tt.get("status", "ACTIVE"),
        "runIndex": int(tt.get("runIndex") or 1),
        "parentConvId": c.get("parentConvId") or cid.split("--run-")[0],
        "isArchivedRun": "--run-" in cid,
        "isClosed": is_closed,
        "messagesCount": len(c.get("messages", [])),
        "subtasksCount": len(c.get("subtasks", [])),
        "updated_at": updated_at,
    }


def _is_unclosed_thinktank(conv: Optional[Dict[str, Any]]) -> bool:
    return bool(conv and has_thinktank_activity(conv) and not (conv.get("thinkTank") or {}).get("isClosed"))


def _refresh_active_conv_id_from_file() -> None:
    global active_conv_id, active_conv_workspace_uri
    active_file = _resolve_active_session_file()
    if active_file and os.path.exists(active_file):
        try:
            with open(active_file, "r", encoding="utf-8") as f:
                sdata = json.load(f)
                raw_ws_map = sdata.get("sessionsByWorkspace")
                if isinstance(raw_ws_map, dict):
                    for ws_k, ws_info in raw_ws_map.items():
                        norm_k = _normalize_workspace_key(ws_k)
                        if not norm_k or not isinstance(ws_info, dict):
                            continue
                        ws_cid = str(ws_info.get("conversationId") or "").strip()
                        if ws_cid:
                            mapped_ws = _ensure_subagent_mapping(ws_cid)
                            resolved_ws_cid = mapped_ws["parentConvId"] if mapped_ws else ws_cid
                            existing_entry = sessions_by_workspace.get(norm_k) or {}
                            existing_cid = str(existing_entry.get("conversationId") or "").strip()
                            existing_unclosed = existing_cid in conversations_store and _is_unclosed_thinktank(conversations_store[existing_cid])
                            cand_has_tt = resolved_ws_cid in conversations_store and has_thinktank_activity(conversations_store[resolved_ws_cid])
                            if existing_unclosed and not cand_has_tt and existing_cid != resolved_ws_cid:
                                continue
                            prev_ts = float(existing_entry.get("timestamp") or 0.0)
                            cand_ts = float(ws_info.get("timestamp") or 0.0)
                            if norm_k not in sessions_by_workspace or cand_ts >= prev_ts:
                                sessions_by_workspace[norm_k] = {
                                    "conversationId": resolved_ws_cid,
                                    "projectId": ws_info.get("projectId"),
                                    "timestamp": cand_ts,
                                }
                raw_cid = str(sdata.get("conversationId") or "").strip()
                if raw_cid:
                    mapped = _ensure_subagent_mapping(raw_cid)
                    if mapped:
                        raw_cid = mapped["parentConvId"]
                    active_conv_id = raw_cid
                    active_conv_workspace_uri = _normalize_workspace_key(sdata.get("workspaceUri"))
        except Exception:
            pass


def _resolve_workspace_conv_id(workspace_uri: Optional[str]) -> Optional[str]:
    norm_ws = _normalize_workspace_key(workspace_uri)
    if not norm_ws:
        return None
    # Prefer the most recently active meaningful ThinkTank session bound to this workspace.
    ws_candidates = [
        (cid, c) for cid, c in conversations_store.items()
        if cid != "default"
        and "--run-" not in cid
        and not c.get("isArchivedRun")
        and _normalize_workspace_key(c.get("workspaceUri")) == norm_ws
        and has_thinktank_activity(c)
    ]
    ws_entry = sessions_by_workspace.get(norm_ws)
    if ws_entry and ws_entry.get("conversationId"):
        mapped_cid = str(ws_entry["conversationId"])
        if "--run-" not in mapped_cid and mapped_cid in conversations_store and _is_unclosed_thinktank(conversations_store[mapped_cid]):
            return mapped_cid
    if ws_candidates:
        ws_candidates.sort(
            key=lambda kv: (0 if not (kv[1].get("thinkTank") or {}).get("isClosed") else 1, -get_conv_sort_ts(kv[1])),
        )
        return ws_candidates[0][0]
    if ws_entry and ws_entry.get("conversationId"):
        mapped_cid = str(ws_entry["conversationId"])
        if "--run-" not in mapped_cid:
            return mapped_cid
    return None


def _valid_project_id_str(raw: Any) -> Optional[str]:
    if not isinstance(raw, str):
        return None
    val = raw.strip()
    if not val or len(val) > 200 or not re.fullmatch(r"[A-Za-z0-9._:-]+", val):
        return None
    return val


def _build_conversations_list(target_cid: str, *, include_target_if_in_store: bool = False) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    sorted_convs = sorted(conversations_store.items(), key=lambda item: get_conv_sort_ts(item[1]), reverse=True)
    for cid, c in sorted_convs:
        if cid == "default" or not is_meaningful_conversation(cid, c, target_cid):
            continue
        rows.append(_build_conv_row(cid, c, target_cid))
    curr_idx = next((i for i, r in enumerate(rows) if r["id"] == target_cid), None)
    if curr_idx is not None and curr_idx > 0:
        c_item = rows.pop(curr_idx)
        c_item["isCurrent"] = True
        rows.insert(0, c_item)
    elif curr_idx is None and target_cid in conversations_store:
        if not include_target_if_in_store or is_meaningful_conversation(target_cid, conversations_store[target_cid], target_cid):
            rows.insert(0, _build_conv_row(target_cid, conversations_store[target_cid], target_cid))
    return rows


@app.post("/api/host/active-session")
async def set_active_session(payload: Dict[str, Any] = Body(...)):
    global active_conv_id, active_conv_workspace_uri
    raw_cid = payload.get("conversationId")
    if raw_cid and isinstance(raw_cid, str):
        raw_cid = raw_cid.strip()
        ev_source = str(payload.get("eventSource") or "").strip().lower()
        mapped = _ensure_subagent_mapping(
            raw_cid,
            parent_cid=payload.get("parentConversationId"),
            role_id=payload.get("roleId"),
            role_title=payload.get("roleTitle"),
        )
        cid = mapped["parentConvId"] if mapped else raw_cid
        req_pid = request_project_id.get()
        existing_conv = conversations_store.get(cid)
        existing_owner = existing_conv.get("projectId") if existing_conv else None
        if req_pid and existing_owner and existing_owner != req_pid:
            raise HTTPException(status_code=403, detail="This session is not assigned to the active project.")
        conv = get_or_create_conversation(cid)
        pid = req_pid or _valid_project_id_str(payload.get("projectId"))
        meta_dirty = False
        if pid and not conv.get("projectId"):
            conv["projectId"] = pid
            meta_dirty = True
        norm_ws = _normalize_workspace_key(payload.get("workspaceUri") or payload.get("workspace"))
        existing_ws_cid = str((sessions_by_workspace.get(norm_ws) or {}).get("conversationId") or "").strip() if norm_ws else ""
        existing_ws_conv = conversations_store.get(existing_ws_cid) if existing_ws_cid else None
        can_claim_workspace = True
        if norm_ws and existing_ws_cid and existing_ws_cid != cid:
            if ev_source == "post-tool-use" and (not has_thinktank_activity(conv) or _is_unclosed_thinktank(existing_ws_conv)):
                can_claim_workspace = False
            elif _is_unclosed_thinktank(existing_ws_conv) and not has_thinktank_activity(conv):
                can_claim_workspace = False
        if can_claim_workspace or not active_conv_id or active_conv_id == "default":
            active_conv_id = cid
            active_conv_workspace_uri = norm_ws or _normalize_workspace_key(conv.get("workspaceUri"))
        if norm_ws:
            if conv.get("workspaceUri") != norm_ws:
                conv["workspaceUri"] = norm_ws
                meta_dirty = True
            if can_claim_workspace:
                sessions_by_workspace[norm_ws] = {
                    "conversationId": cid,
                    "projectId": conv.get("projectId"),
                    "timestamp": time.time(),
                }
        agent_updated = False
        if mapped:
            tt = conv.get("thinkTank") or {}
            is_closed = bool(tt.get("isClosed")) or str(tt.get("status") or "").upper() in {"COMPLETED", "DONE", "CLOSED"}
            role_id = mapped.get("roleId")
            if not is_closed and role_id and role_id not in {"user", "subagent"}:
                agent_updated = upsert_agent_state(
                    conv,
                    role_id,
                    task=mapped.get("roleTitle") or None,
                    status="WORKING",
                    subagent_conv_id=raw_cid,
                    verified_subagent=True,
                )
        if meta_dirty or agent_updated:
            sync_store.save_snapshot_only(cid, conv)
        schedule_persisted_state_save()
        if agent_updated:
            if has_thinktank_activity(conv):
                await manager.broadcast({"type": "AGENTS_UPDATE", "convId": cid, "agents": conv["agents"]})
            else:
                await manager.broadcast_transient({"type": "AGENTS_UPDATE", "convId": cid, "agents": conv["agents"]})
        return {"status": "ok", "activeConversationId": active_conv_id}
    return {"status": "error", "message": "Invalid conversationId"}


def _resolve_session_for_workspace(workspace_uri: Optional[str]) -> tuple[str, bool, Optional[str]]:
    _refresh_active_conv_id_from_file()
    norm_ws = _normalize_workspace_key(workspace_uri)
    ws_cid = _resolve_workspace_conv_id(norm_ws) if norm_ws else None
    if norm_ws:
        if ws_cid:
            return ws_cid, True, norm_ws
        active_ws = _normalize_workspace_key(
            (conversations_store.get(active_conv_id) or {}).get("workspaceUri") or active_conv_workspace_uri
        )
        if active_ws and active_ws != norm_ws:
            return "", False, norm_ws
        if active_conv_id and active_conv_id != "default" and not active_ws:
            return active_conv_id, True, norm_ws
        return "", False, norm_ws
    return active_conv_id, True, None


@app.get("/api/host/active-session")
@app.get("/api/host/context")
def get_active_session(workspaceUri: Optional[str] = Query(None)):
    resolved_cid, ws_matched, norm_ws = _resolve_session_for_workspace(workspaceUri)
    conv = conversations_store.get(resolved_cid, {}) if resolved_cid else {}
    return {
        "conversationId": resolved_cid,
        "workspaceUri": norm_ws or conv.get("workspaceUri"),
        "workspaceMatched": ws_matched,
        "projectId": conv.get("projectId"),
        "project": (conv.get("thinkTank") or {}).get("project"),
        "status": (conv.get("thinkTank") or {}).get("status", "DISCONNECTED" if not resolved_cid else "ACTIVE"),
        "hasSession": has_thinktank_activity(conv),
    }


@app.get("/api/conversations")
def list_conversations():
    """Return selectable session metadata without loading or creating a session."""
    _refresh_active_conv_id_from_file()
    target_cid = active_conv_id or "default"
    return {"conversations": _build_conversations_list(target_cid)}


def _build_status_payload(target_cid: str) -> Dict[str, Any]:
    mapped = _ensure_subagent_mapping(target_cid)
    if mapped:
        target_cid = mapped["parentConvId"]
    project_id = request_project_id.get()
    in_store = target_cid in conversations_store
    if in_store:
        target_conv = conversations_store[target_cid]
        if project_id and not target_conv.get("projectId"):
            target_conv["projectId"] = project_id
        check_and_reload_state(target_cid)
        conv = target_conv
    else:
        # Strict isolation: an uninitialized conversation ID returns a clean empty
        # snapshot without polluting conversations_store or leaking default state.
        conv = create_empty_conversation(target_cid)

    conv_list = _build_conversations_list(target_cid, include_target_if_in_store=in_store)

    cursor = sync_store.cursor(target_cid)
    imported_snapshot = cursor["last_event_type"] in {"SNAPSHOT_IMPORTED"}
    state_age_seconds = max(0.0, time.time() - float(cursor.get("updated_at") or time.time()))
    if imported_snapshot:
        freshness = "imported_snapshot"
    elif cursor["seq"] == 0:
        freshness = "empty"
    else:
        freshness = "updated"
    pstate = _sync_pipeline_fields(conv)
    return {
        "convId": target_cid,
        "parentConvId": conv.get("parentConvId") or target_cid.split("--run-")[0],
        "hasSession": pstate["hasSession"],
        "thinkTank": conv["thinkTank"],
        "pipelineStage": pstate["pipelineStage"],
        "isClosed": pstate["isClosed"],
        "proposal": conv["proposal"],
        "review": conv.get("review"),
        "agents": conv["agents"],
        "messages": conv["messages"],
        "interactions": conv.get("interactions", []),
        "graph": build_interaction_graph(conv),
        "telemetry": conv["telemetry"],
        "collaborations": conv.get("collaborations", []),
        "subtasks": conv.get("subtasks", []),
        "findings": conv.get("findings", []),
        "fileLocks": conv.get("fileLocks", []),
        "originCounts": _compute_origin_counts(conv),
        "closureReceipt": (conv.get("thinkTank") or {}).get("closureReceipt"),
        "roleUsage": role_usage(conv.get("messages", [])),
        "conversationsList": conv_list,
        "serverTime": time.strftime("%H:%M:%S"),
        "sync": cursor,
        "syncMode": "durable-websocket",
        "stateFreshness": freshness,
        "stateAgeSeconds": int(state_age_seconds),
    }


@app.get("/api/health")
@app.get("/health")
def get_health():
    return {
        "ok": True,
        "status": "ok",
        "syncMode": "durable-websocket",
        "conversationsCount": len(conversations_store),
    }


@app.get("/api/status")
@app.get("/status")
def get_status(convId: Optional[str] = Query(None), conv_id: Optional[str] = Query(None), workspaceUri: Optional[str] = Query(None)):
    explicit_cid = (convId or conv_id or "").strip()
    if explicit_cid:
        return _build_status_payload(explicit_cid)

    resolved_cid, ws_matched, _ = _resolve_session_for_workspace(workspaceUri)
    target_cid = resolved_cid if (ws_matched and resolved_cid) else "default"
    return _build_status_payload(target_cid)


@app.post("/api/status")
@app.post("/status")
def post_status(payload: Optional[Dict[str, Any]] = Body(None), convId: Optional[str] = Query(None), conv_id: Optional[str] = Query(None), workspaceUri: Optional[str] = Query(None)):
    body_cid = str((payload or {}).get("convId") or (payload or {}).get("conversationId") or (payload or {}).get("conv_id") or "").strip()
    body_ws = str((payload or {}).get("workspaceUri") or (payload or {}).get("workspace") or "").strip()
    query_cid = (convId or conv_id or "").strip()
    return get_status(convId=query_cid or body_cid or None, workspaceUri=workspaceUri or body_ws or None)


def upsert_agent_state(
    conv: Dict[str, Any],
    agent_id: str,
    *,
    name: Optional[str] = None,
    role: Optional[str] = None,
    code: Optional[str] = None,
    status: str = "ACTIVE",
    tool: Optional[str] = None,
    thought: Optional[str] = None,
    task: Optional[str] = None,
    collaborating_with: Optional[str] = None,
    increment_turn: bool = False,
    subagent_conv_id: Optional[str] = None,
    verified_subagent: bool = False,
) -> bool:
    if not agent_id or not isinstance(agent_id, str):
        return False
    clean_id = normalize_agent_id(agent_id)
    if not clean_id or clean_id in {"operator", "user"}:
        return False

    agents = conv.setdefault("agents", [])
    matched = None
    for ag in agents:
        aid = normalize_agent_id(ag.get("id", ""))
        acode = normalize_agent_id(ag.get("code", ""))
        if aid == clean_id or acode == clean_id or aid.replace("_", "") == clean_id.replace("_", ""):
            matched = ag
            break

    if matched:
        catalog = load_role_catalog()
        cat_entry = next((r for r in catalog if normalize_agent_id(r.get("id", "")) == clean_id or normalize_agent_id(r.get("code", "")) == clean_id), None)
        if cat_entry:
            for meta_key in ("tier", "tierLabel", "reportsTo", "canInterrogate", "canPeerSync"):
                if meta_key in cat_entry:
                    matched[meta_key] = cat_entry[meta_key]
        if name and (not matched.get("name") or matched.get("name") == clean_id):
            matched["name"] = name
        if role and not matched.get("role"):
            matched["role"] = role
        if code and not matched.get("code"):
            matched["code"] = code
        if status:
            matched["status"] = status
        if tool:
            matched["tool"] = tool.strip()
            matched["activeTool"] = tool.strip()
        if thought:
            matched["thought"] = thought.strip()
        if task:
            matched["task"] = task.strip()
            matched["currentTask"] = task.strip()
        if collaborating_with:
            clean_cw = normalize_agent_id(collaborating_with)
            if clean_cw and clean_cw != clean_id:
                cwith = matched.setdefault("collaboratingWith", [])
                if clean_cw not in cwith:
                    cwith.append(clean_cw)
        if increment_turn:
            matched["turnsUsed"] = int(matched.get("turnsUsed") or 0) + 1
        if subagent_conv_id and isinstance(subagent_conv_id, str) and subagent_conv_id.strip():
            matched["subagentConvId"] = subagent_conv_id.strip()
        if verified_subagent:
            matched["verifiedSubagent"] = True
        return True

    catalog = load_role_catalog()
    cat_entry = next((r for r in catalog if normalize_agent_id(r.get("id", "")) == clean_id or normalize_agent_id(r.get("code", "")) == clean_id), None)

    title = name or (cat_entry.get("title") if cat_entry else None) or clean_id.replace("_", " ").title()
    spec = role or (cat_entry.get("specialty") if cat_entry else None) or "ساب‌ایجنت هوشمند"
    icon = (cat_entry.get("icon") if cat_entry else None) or "agent"
    skills = cat_entry.get("skills", ["task-execution", "live-collaboration"]) if cat_entry else ["task-execution", "live-collaboration"]

    cwith_list = []
    if collaborating_with:
        clean_cw = normalize_agent_id(collaborating_with)
        if clean_cw and clean_cw != clean_id:
            cwith_list.append(clean_cw)

    profile = {
        "id": clean_id,
        "name": title,
        "role": spec,
        "icon": icon,
        "status": status,
        "tier": (cat_entry.get("tier") if cat_entry else None) or "worker",
        "tierLabel": (cat_entry.get("tierLabel") if cat_entry else None) or "متخصص اجرایی",
        "reportsTo": cat_entry.get("reportsTo") if cat_entry else None,
        "canInterrogate": bool(cat_entry.get("canInterrogate", False)) if cat_entry else False,
        "canPeerSync": bool(cat_entry.get("canPeerSync", True)) if cat_entry else True,
        "task": task or f"فعالیت در نشست جاری ({title})",
        "currentTask": task or f"فعالیت در نشست جاری ({title})",
        "tool": tool.strip() if tool else None,
        "activeTool": tool.strip() if tool else None,
        "thought": thought.strip() if thought else None,
        "turnsUsed": 1 if increment_turn else None,
        "collaboratingWith": cwith_list,
        "skills": skills,
    }
    if code:
        profile["code"] = code
    if subagent_conv_id and isinstance(subagent_conv_id, str) and subagent_conv_id.strip():
        profile["subagentConvId"] = subagent_conv_id.strip()
    if verified_subagent:
        profile["verifiedSubagent"] = True
    agents.append(profile)
    return True


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
    collaboratingWith: Optional[List[str]] = None
    convId: Optional[str] = None

@app.post("/api/agent/update")
async def update_agent_endpoint(req: AgentUpdateRequest):
    cid = require_conversation_id(req.convId)
    check_and_reload_state(cid)
    conv = get_or_create_conversation(cid)
    _require_case_open(conv)

    updated = False
    for ag in conv["agents"]:
        ag_id = ag.get("id", "")
        if ag_id == req.id or ag_id == f"agent-{req.id}" or ag_id.replace("agent-", "") == req.id:
            if req.name is not None:
                ag["name"] = req.name
            if req.role is not None:
                ag["role"] = req.role
            if req.code is not None:
                ag["code"] = req.code
            if req.icon is not None:
                ag["icon"] = req.icon
            if req.task is not None:
                ag["task"] = req.task
                ag["currentTask"] = req.task
            if req.tool is not None:
                ag["tool"] = req.tool
                ag["activeTool"] = req.tool
            if req.thought is not None:
                ag["thought"] = req.thought
            if req.demo is not None:
                ag["demo"] = req.demo
            if req.status is not None:
                ag["status"] = req.status
            if req.progress is not None:
                ag["progress"] = req.progress
            if req.latency is not None:
                ag["latencyMs"] = req.latency
                ag["latency"] = req.latency
            if req.collaboratingWith is not None:
                ag["collaboratingWith"] = req.collaboratingWith
            updated = True
            break

    if not updated:
        profile = {"id": req.id}
        for key, value in (
            ("name", req.name),
            ("role", req.role),
            ("code", req.code),
            ("icon", req.icon),
            ("task", req.task),
            ("currentTask", req.task),
            ("tool", req.tool),
            ("activeTool", req.tool),
            ("thought", req.thought),
            ("demo", req.demo),
            ("status", req.status),
            ("progress", req.progress),
            ("latencyMs", req.latency),
            ("latency", req.latency),
            ("collaboratingWith", req.collaboratingWith),
        ):
            if value is not None:
                profile[key] = value
        conv["agents"].append(profile)
        updated = True

    if updated:
        save_persisted_state()
        await manager.broadcast({
            "type": "AGENTS_UPDATE",
            "convId": cid,
            "agents": conv["agents"]
        })
    return {"status": "ok", "convId": cid, "agents": conv["agents"]}


class TaskUpdateRequest(BaseModel):
    project: Optional[str] = None
    directive: Optional[str] = None
    status: Optional[str] = None
    phase: Optional[str] = None
    progress: Optional[int] = None
    activeAgentIds: Optional[List[str]] = None
    round: Optional[int] = None
    maxRounds: Optional[int] = None
    roleCaps: Optional[Dict[str, int]] = None
    roundStatus: Optional[str] = None
    triageDecision: Optional[Dict[str, Any]] = None
    forceClose: bool = False
    forceReason: Optional[str] = None
    reopen: bool = False
    resetCase: bool = False
    newRun: bool = False
    summary: Optional[str] = None
    origin: Optional[str] = None
    subagentConvId: Optional[str] = None
    convId: Optional[str] = None


def _build_closure_receipt(conv: Dict[str, Any], force_reason: Optional[str]) -> Dict[str, Any]:
    tt = conv.get("thinkTank") or {}
    subtasks = conv.get("subtasks") or []
    findings = conv.get("findings") or []
    msgs = conv.get("messages") or []

    qa_exit_codes: List[Optional[int]] = []
    seen_qa_seqs: set[int] = set()
    for f in findings:
        if not isinstance(f, dict):
            continue
        for ev in f.get("evidence") or []:
            if not isinstance(ev, dict):
                continue
            seq_val = int(ev.get("seq") or 0)
            if seq_val:
                seen_qa_seqs.add(seq_val)
            qa_exit_codes.append(ev.get("exitCode"))
    for m in msgs:
        if not isinstance(m, dict) or str(m.get("actionType") or "").upper() != "QA_REPORT":
            continue
        seq_val = int(m.get("seq") or 0)
        if seq_val and seq_val in seen_qa_seqs:
            continue
        ev = m.get("evidence")
        if isinstance(ev, dict):
            qa_exit_codes.append(ev.get("exitCode"))
        else:
            res_upper = str(m.get("result") or "").strip().upper()
            content_upper = str(m.get("content") or "").upper()
            is_legacy_pass = not res_upper and "PASS" in content_upper and "FAIL" not in content_upper
            qa_exit_codes.append(0 if (res_upper == "PASS" or is_legacy_pass) else 1)

    return {
        "closedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "project": tt.get("project") or "",
        "totalEvents": len(msgs),
        "subtasksTotal": len(subtasks),
        "subtasksCompleted": sum(1 for s in subtasks if isinstance(s, dict) and str(s.get("status") or "").upper() in {"COMPLETED", "DONE"}),
        "findingsVerified": sum(1 for f in findings if isinstance(f, dict) and str(f.get("state") or "").lower() in {"verified", "closed"}),
        "findingsOpen": sum(1 for f in findings if isinstance(f, dict) and str(f.get("state") or "").lower() in {"open", "fixing", "inreview", "testing"}),
        "findingsWontFix": sum(1 for f in findings if isinstance(f, dict) and str(f.get("state") or "").lower() == "wontfix"),
        "qaRunsCount": len(qa_exit_codes),
        "qaAllExitZero": bool(qa_exit_codes) and all(code == 0 for code in qa_exit_codes),
        "originCounts": _compute_origin_counts(conv),
        "forceCloseReason": (force_reason or "").strip() or None,
    }


def _archive_conversation_run(base_cid: str, conv: Dict[str, Any]) -> Optional[str]:
    base_cid = base_cid.split("--run-")[0]
    tt = conv.setdefault("thinkTank", dict(default_think_tank_state))
    run_idx = int(tt.get("runIndex") or 1)
    while f"{base_cid}--run-{run_idx}" in conversations_store:
        run_idx += 1
    archived_id = f"{base_cid}--run-{run_idx}"
    archived_conv = copy.deepcopy(conv)
    archived_conv["id"] = archived_id
    archived_conv["parentConvId"] = base_cid
    archived_conv["isArchivedRun"] = True
    archived_tt = archived_conv.setdefault("thinkTank", dict(default_think_tank_state))
    archived_tt["runIndex"] = run_idx
    archived_tt["isClosed"] = True
    if str(archived_tt.get("status") or "").upper() not in {"COMPLETED", "DONE", "CLOSED"}:
        archived_tt["status"] = "COMPLETED"
    conversations_store[archived_id] = archived_conv
    sync_store.commit(
        conversation_id=archived_id,
        event_id=f"run-archived-{archived_id}-{uuid.uuid4().hex[:8]}",
        event_type="RUN_ARCHIVED",
        payload={"convId": archived_id, "parentConvId": base_cid, "runIndex": run_idx},
        snapshot=archived_conv,
        source="archive",
    )

    next_run = run_idx + 1
    conv["id"] = base_cid
    conv["parentConvId"] = base_cid
    conv["findings"] = []
    conv["subtasks"] = []
    conv["messages"] = []
    conv["collaborations"] = []
    conv["interactions"] = []
    conv["fileLocks"] = []
    conv["proposal"] = None
    conv["review"] = None
    conv["agents"] = get_default_agents()
    conv["telemetry"] = {k: [] for k in default_telemetry_store}
    tt["isClosed"] = False
    tt["closureReceipt"] = None
    tt["status"] = "ACTIVE"
    tt["round"] = 1
    tt["progress"] = 5
    tt["stageEpochSeq"] = 0
    tt["pipelineStage"] = 1
    tt["roundStatus"] = "ACTIVE"
    tt["triageDecision"] = None
    tt["project"] = ""
    tt["directive"] = ""
    tt["phase"] = "در حال بررسی و اجرای پرونده جدید"
    tt["runIndex"] = next_run
    return archived_id


@app.post("/api/task/update")
async def update_task(req: TaskUpdateRequest):
    cid = require_conversation_id(req.convId)
    if req.newRun and "--run-" in cid:
        cid = require_conversation_id(cid.split("--run-")[0])
    check_and_reload_state(cid)
    conv = get_or_create_conversation(cid)
    if request_project_id.get() and not conv.get("projectId"):
        conv["projectId"] = request_project_id.get()
    tt = conv["thinkTank"]

    is_reopening = bool(req.reopen) and not req.resetCase and not req.newRun
    archived_run_id = None

    if req.resetCase:
        conv["findings"] = []
        conv["subtasks"] = []
        conv["messages"] = []
        conv["collaborations"] = []
        conv["interactions"] = []
        conv["fileLocks"] = []
        conv["proposal"] = None
        conv["review"] = None
        conv["agents"] = get_default_agents()
        conv["telemetry"] = {k: [] for k in default_telemetry_store}
        tt["isClosed"] = False
        tt["closureReceipt"] = None
        tt["status"] = "ACTIVE"
        tt["round"] = 1
        tt["progress"] = 5
        tt["stageEpochSeq"] = 0
        tt["pipelineStage"] = 1
        tt["roundStatus"] = "ACTIVE"
        tt["triageDecision"] = None
        tt["project"] = req.project or ""
        tt["directive"] = req.directive or ""
        tt["phase"] = req.phase or "در حال بررسی و اجرای پرونده جدید"
        tt["runIndex"] = int(tt.get("runIndex") or 1)
        if req.maxRounds is not None:
            tt["maxRounds"] = normalize_round_limit(req.maxRounds)
        if req.roleCaps is not None:
            tt["roleCaps"] = normalize_role_caps(req.roleCaps)
        if req.triageDecision is not None:
            tt["triageDecision"] = req.triageDecision
        _sync_pipeline_fields(conv)
    elif is_reopening:
        tt["isClosed"] = False
        tt["closureReceipt"] = None
        tt["status"] = "ACTIVE"
        if tt.get("roundStatus") == "COMPLETE":
            tt["roundStatus"] = "ACTIVE"
        now_hms = time.strftime("%H:%M:%S")
        for f in conv.get("findings") or []:
            if isinstance(f, dict) and str(f.get("state") or "").strip().lower() == "closed":
                f["state"] = "Verified"
                f["updatedAt"] = now_hms
        for ag in conv.get("agents") or []:
            if isinstance(ag, dict) and str(ag.get("status") or "").upper() == "COMPLETED":
                ag["status"] = "IDLE"
                ag["activeTool"] = None
                ag["tool"] = None
        conv.pop("_telemetryOnly", None)
        if req.project:
            tt["project"] = req.project
        if req.directive:
            tt["directive"] = req.directive
        if req.phase:
            tt["phase"] = req.phase
        if req.progress is not None and int(req.progress) < 100:
            tt["progress"] = req.progress
        elif int(tt.get("progress") or 0) >= 100:
            tt["progress"] = 90
        if req.round is not None:
            tt["round"] = req.round
        if req.maxRounds is not None:
            tt["maxRounds"] = normalize_round_limit(req.maxRounds)
        if req.roleCaps is not None:
            tt["roleCaps"] = normalize_role_caps(req.roleCaps)
        if req.triageDecision is not None:
            tt["triageDecision"] = req.triageDecision
        _sync_pipeline_fields(conv)
    else:
        was_closed = bool(tt.get("isClosed")) or str(tt.get("status") or "").upper() in {"COMPLETED", "DONE", "CLOSED"}
        req_status_upper = str(req.status or "").upper()
        req_should_close = req_status_upper in {"COMPLETED", "DONE", "CLOSED"} or (
            req.progress is not None and int(req.progress) >= 100 and req_status_upper != "HALTED"
        )
        has_existing_work = bool(conv.get("subtasks") or conv.get("findings") or conv.get("messages") or conv.get("proposal"))
        should_start_new_run = has_existing_work and not req_should_close and (
            bool(req.newRun)
            or (was_closed and (req.triageDecision is not None or bool(req.project) or bool(req.directive) or req_status_upper == "ACTIVE"))
        )
        if should_start_new_run:
            archived_run_id = _archive_conversation_run(cid, conv)
            was_closed = False

        if req.status == "COMPLETED":
            review = conv.get("review") or {}
            if review and review.get("status") == "REVIEW_REQUESTED" and (review.get("confidence", 0) < 95 or review.get("decision") != "complete"):
                raise HTTPException(status_code=409, detail="Completion requires a manager and main-agent review with an evidence score of at least 95.")
        if req.round is not None and req.round > normalize_round_limit(tt.get("maxRounds", 50)):
            raise HTTPException(status_code=409, detail="The round limit has been reached. Extend the limit before starting another round.")

        target_status_upper = str(req.status or tt.get("status") or "").upper()
        target_should_close = target_status_upper in {"COMPLETED", "DONE", "CLOSED"} or (
            req.progress is not None and int(req.progress) >= 100 and target_status_upper != "HALTED"
        )
        if target_should_close:
            if req.forceClose and not (req.forceReason or "").strip():
                raise HTTPException(status_code=409, detail="forceClose requires a non-empty forceReason.")
            unresolved = [
                f for f in (conv.get("findings") or [])
                if isinstance(f, dict) and str(f.get("state") or "").lower() in {"open", "fixing", "inreview", "testing"}
            ]
            if unresolved and not req.forceClose:
                ids = ", ".join(str(f.get("id") or "?") for f in unresolved[:5])
                raise HTTPException(
                    status_code=409,
                    detail=f"Cannot close session while {len(unresolved)} unresolved finding(s) remain ({ids}). Resolve them or pass forceClose with forceReason.",
                )

        conv.pop("_telemetryOnly", None)
        if req.project:
            tt["project"] = req.project
        if req.directive:
            tt["directive"] = req.directive
        if req.status:
            tt["status"] = req.status
        if req.phase:
            tt["phase"] = req.phase
        if req.progress is not None:
            tt["progress"] = req.progress
        if req.round is not None:
            tt["round"] = req.round
        if req.maxRounds is not None:
            tt["maxRounds"] = normalize_round_limit(req.maxRounds)
        if req.roleCaps is not None:
            tt["roleCaps"] = normalize_role_caps(req.roleCaps)
        if req.roundStatus:
            tt["roundStatus"] = req.roundStatus
        if req.triageDecision is not None:
            tt["triageDecision"] = req.triageDecision

        # Hard Process Closure when completed/done/100% or explicitly deactivated
        status_upper = str(tt.get("status") or "").upper()
        should_close_hard = status_upper in {"COMPLETED", "DONE", "CLOSED"} or (req.progress is not None and int(req.progress) >= 100 and status_upper != "HALTED")
        if not should_close_hard and (
            was_closed
            or req.round == 1
            or (req.project and req.directive)
            or (req.progress is not None and int(req.progress) < 100 and (req.project or req.directive))
        ):
            epoch = max((int(m.get("seq") or 0) for m in conv.get("messages", []) if isinstance(m, dict)), default=0)
            tt["stageEpochSeq"] = epoch
            tt["isClosed"] = False
            tt["closureReceipt"] = None
            for m in conv.get("messages", []):
                if isinstance(m, dict) and int(m.get("seq") or 0) <= epoch:
                    m["resolved"] = True
            for ev in conv.get("interactions", []):
                if isinstance(ev, dict) and int(ev.get("seq") or 0) <= epoch:
                    ev["resolved"] = True

        if should_close_hard:
            tt["status"] = "COMPLETED"
            tt["progress"] = 100
            tt["pipelineStage"] = 5
            tt["isClosed"] = True
            if not req.phase:
                tt["phase"] = "تکمیل‌شده و بسته — آماده برای تسک جدید"
            for ag in conv.get("agents", []):
                ag["status"] = "COMPLETED"
                ag["activeTool"] = None
                ag["tool"] = None
                ag["currentTask"] = "تکمیل و تحویل نهایی"
                ag["task"] = "تکمیل و تحویل نهایی"
                ag["thought"] = "عملیات با موفقیت به پایان رسید و نشست بسته شد"
                ag["currentThought"] = "عملیات با موفقیت به پایان رسید و نشست بسته شد"
                ag["collaboratingWith"] = []
            for st in conv.get("subtasks", []):
                st["status"] = "COMPLETED"
            _rebuild_file_locks(conv)
            now_hms = time.strftime("%H:%M:%S")
            for f in conv.get("findings") or []:
                if isinstance(f, dict) and str(f.get("state") or "").lower() == "verified":
                    f["state"] = "Closed"
                    f["updatedAt"] = now_hms
            for m in conv.get("messages", []):
                if isinstance(m, dict):
                    m["resolved"] = True
            for ev in conv.get("interactions", []):
                if isinstance(ev, dict):
                    ev["resolved"] = True
            for collab in conv.get("collaborations", []):
                if isinstance(collab, dict):
                    collab["active"] = False
            if conv.get("proposal") and conv["proposal"].get("status") in {"AWAITING_APPROVAL", "PROPOSED", "APPROVED", "EXECUTING"}:
                conv["proposal"]["status"] = "COMPLETED"
            if (req.summary or "").strip():
                append_message(
                    conv,
                    {
                        "id": f"complete-{int(time.time() * 1000)}-{uuid.uuid4().hex[:4]}",
                        "channel": "MAIN",
                        "senderCode": "TEAM-MANAGER",
                        "senderName": "مدیر تیم",
                        "senderRole": "team-manager",
                        "timestamp": now_hms,
                        "content": f"[تکمیل و بسته شدن نشست]: {req.summary.strip()}",
                        "isReview": False,
                        "origin": req.origin,
                        "subagentConvId": req.subagentConvId,
                        "convId": cid,
                    },
                    action_type="COMPLETE",
                )
                tt["isClosed"] = True
            tt["closureReceipt"] = _build_closure_receipt(conv, req.forceReason if req.forceClose else None)
        elif status_upper == "IDLE":
            for ag in conv.get("agents", []):
                ag["status"] = "IDLE"
                ag["activeTool"] = None
                ag["tool"] = None
                ag["collaboratingWith"] = []
            _sync_pipeline_fields(conv)
        else:
            _sync_pipeline_fields(conv)

    save_persisted_state()
    await manager.broadcast({
        "type": "STATE_UPDATE",
        "convId": cid,
        "thinkTank": tt,
        "proposal": conv["proposal"],
        "review": conv.get("review"),
        "agents": conv["agents"],
        "subtasks": conv.get("subtasks", []),
        "findings": conv.get("findings", []),
        "fileLocks": conv.get("fileLocks", []),
        "originCounts": _compute_origin_counts(conv),
        "closureReceipt": tt.get("closureReceipt"),
        "messages": conv.get("messages", []),
        "interactions": conv.get("interactions", []),
        "collaborations": conv.get("collaborations", []),
        "graph": build_interaction_graph(conv),
        "roleUsage": role_usage(conv.get("messages", [])),
        "conversationsList": _build_conversations_list(cid),
        "telemetry": conv["telemetry"],
    })
    return {
        "status": "updated",
        "convId": cid,
        "thinkTank": tt,
        "closureReceipt": tt.get("closureReceipt"),
        "archivedRunId": archived_run_id,
    }


class ReopenCaseRequest(BaseModel):
    convId: Optional[str] = None


@app.post("/api/governance/reopen")
async def reopen_case_endpoint(req: ReopenCaseRequest):
    return await update_task(TaskUpdateRequest(convId=req.convId, reopen=True))


class ProposalUpdateRequest(BaseModel):
    id: str
    project: str
    title: str
    author: str
    summary: str
    decisionOptions: Optional[List[Dict[str, Any]]] = None
    votes: Optional[List[Dict[str, Any]]] = None
    convId: Optional[str] = None

@app.post("/api/proposal/update")
async def update_proposal(req: ProposalUpdateRequest):
    cid = require_conversation_id(req.convId)
    check_and_reload_state(cid)
    conv = get_or_create_conversation(cid)
    _require_case_open(conv)

    conv["proposal"] = {
        "id": req.id,
        "project": req.project,
        "title": req.title,
        "author": req.author,
        "status": "AWAITING_APPROVAL",
        "summary": req.summary,
        "decisionOptions": req.decisionOptions or [],
        "votes": req.votes or [],
        "userDecision": None,
        "lastActionAt": None,
    }
    conv["thinkTank"]["status"] = "ACTIVE"
    conv["thinkTank"]["phase"] = "Awaiting User Approval on Proposal"
    save_persisted_state()

    await manager.broadcast({
        "type": "PROPOSAL_UPDATE",
        "convId": cid,
        "proposal": conv["proposal"],
        "thinkTank": conv["thinkTank"],
        "roleUsage": role_usage(conv.get("messages", [])),
    })
    return {"status": "ok", "convId": cid, "proposal": conv["proposal"]}


class ProposalActionRequest(BaseModel):
    action: str  # approve, request_revision, select_option, halt
    optionId: Optional[str] = None
    comment: Optional[str] = None
    convId: Optional[str] = None

@app.post("/api/proposal/action")
async def handle_proposal_action(req: ProposalActionRequest):
    cid = require_conversation_id(req.convId)
    check_and_reload_state(cid)
    conv = get_or_create_conversation(cid)
    _require_case_open(conv)
    current_prop = conv["proposal"]
    tt = conv["thinkTank"]
    msgs = conv["messages"]
    now_str = time.strftime("%H:%M:%S")

    if req.action == "approve":
        current_prop["status"] = "APPROVED"
        current_prop["userDecision"] = {
            "action": "APPROVED",
            "optionId": req.optionId,
            "comment": req.comment or "طرح توسط کاربر تایید و دستور اجرای قطعی صادر شد.",
            "timestamp": now_str
        }
        tt["status"] = "EXECUTING"
        tt["progress"] = 90
        tt["phase"] = "Applying Changes & Final Production Verification"

        append_message(conv, {
            "id": f"act-{time.time()}",
            "channel": "MAIN",
            "senderCode": "OPERATOR",
            "senderName": "Operator",
            "senderRole": "owner",
            "timestamp": now_str,
            "content": f"[تایید رسمی کاربر]: طرح «{current_prop['title']}» مورد تایید قرار گرفت و دستور اجرا صادر شد."
        }, action_type="DECISION")

    elif req.action == "select_option":
        current_prop["userDecision"] = {
            "action": "OPTION_SELECTED",
            "optionId": req.optionId,
            "comment": req.comment,
            "timestamp": now_str
        }
        selected_text = req.optionId
        for opt in current_prop.get("decisionOptions", []):
            if opt.get("id") == req.optionId:
                selected_text = opt.get("label", req.optionId)
                break
        
        append_message(conv, {
            "id": f"act-{time.time()}",
            "channel": "MAIN",
            "senderCode": "OPERATOR",
            "senderName": "Operator",
            "senderRole": "owner",
            "timestamp": now_str,
            "content": f"[انتخاب گزینه توسط کاربر]: «{selected_text}»\nپروسه با گزینه انتخابی ادامه می‌یابد."
        }, action_type="DECISION")

    elif req.action == "request_revision":
        current_prop["status"] = "REVISION_REQUESTED"
        current_prop["userDecision"] = {
            "action": "REVISION_REQUESTED",
            "comment": req.comment or "درخواست اصلاح و بازنگری توسط کاربر ثبت شد.",
            "timestamp": now_str
        }
        tt["status"] = "ACTIVE"
        tt["phase"] = "Council Revising Plan According to Feedback"

        append_message(conv, {
            "id": f"act-{time.time()}",
            "channel": "SUBAGENTS",
            "senderCode": "OPERATOR",
            "senderName": "Operator",
            "senderRole": "owner",
            "timestamp": now_str,
            "content": f"[درخواست اصلاح از سوی کاربر]: لطفا طرح بازنگری و مجددا چکش‌کاری شود.\nتوضیحات: {req.comment or 'عدم تایید نسخه فعلی'}"
        }, action_type="DECISION")

    elif req.action == "halt":
        current_prop["status"] = "HALTED"
        tt["status"] = "HALTED"
        tt["phase"] = "Session Halted by Operator"

        append_message(conv, {
            "id": f"act-{time.time()}",
            "channel": "MAIN",
            "senderCode": "OPERATOR",
            "senderName": "Operator",
            "senderRole": "owner",
            "timestamp": now_str,
            "content": "[دستور توقف توسط کاربر]: نشست اتاق فکر به درخواست صریح کاربر متوقف گردید."
        }, action_type="DECISION")

    current_prop["lastActionAt"] = now_str
    save_persisted_state()

    await manager.broadcast({
        "type": "PROPOSAL_UPDATE",
        "convId": cid,
        "proposal": current_prop,
        "thinkTank": tt,
        "messages": msgs,
        "interactions": conv.get("interactions", []),
        "graph": build_interaction_graph(conv),
        "roleUsage": role_usage(msgs),
    })
    return {"status": "ok", "convId": cid, "proposal": current_prop, "thinkTank": tt}


class ProposalVoteRequest(BaseModel):
    voter: str
    voterName: Optional[str] = None
    voterRole: Optional[str] = None
    stance: str = "APPROVE"  # APPROVE, CONDITIONAL, CRITIQUE, REJECT
    confidence: int = 90
    comment: str
    counterArgument: Optional[str] = None
    origin: Optional[str] = None
    subagentConvId: Optional[str] = None
    convId: Optional[str] = None


@app.post("/api/proposal/vote")
async def vote_proposal(req: ProposalVoteRequest):
    cid = require_conversation_id(req.convId)
    check_and_reload_state(cid)
    conv = get_or_create_conversation(cid)
    _require_case_open(conv)
    tt = conv["thinkTank"]
    msgs = conv["messages"]
    now_str = time.strftime("%H:%M:%S")

    if not conv.get("proposal") or (isinstance(conv.get("proposal"), dict) and conv["proposal"].get("status") == "NONE"):
        conv["proposal"] = {
            "id": f"prop-{int(time.time())}",
            "project": tt.get("project") or "پروژه جاری",
            "title": tt.get("directive") or "طرح راهبردی اتاق فکر",
            "author": "Council",
            "status": "AWAITING_APPROVAL",
            "summary": tt.get("directive") or "بررسی و هم‌افزایی شورای اتاق فکر",
            "decisionOptions": [
                {"id": "opt-1", "label": "تأیید و اجرای کامل طرح"},
                {"id": "opt-2", "label": "بازنگری بر اساس نقدها"},
            ],
            "votes": [],
            "userDecision": None,
            "lastActionAt": None,
        }

    prop = conv["proposal"]
    votes = prop.setdefault("votes", [])
    canon_voter = normalize_agent_id(req.voter) or req.voter.strip()
    stance_upper = (req.stance or "APPROVE").upper().strip()

    # Resolve voter display name from role_catalog if not given
    voter_name = req.voterName or req.voter
    try:
        catalog_path = os.path.join(os.path.dirname(__file__), "role_catalog.json")
        if os.path.exists(catalog_path):
            with open(catalog_path, "r", encoding="utf-8") as cf:
                cdata = json.load(cf)
                croles = cdata if isinstance(cdata, list) else cdata.get("roles", [])
                for cr in croles:
                    if normalize_agent_id(cr.get("id", "")) == canon_voter or normalize_agent_id(cr.get("agent_name", "")) == canon_voter:
                        voter_name = req.voterName or cr.get("title") or cr.get("title_fa") or voter_name
                        break
    except Exception:
        pass

    vote_entry = {
        "voter": canon_voter,
        "voterName": voter_name,
        "voterRole": req.voterRole or canon_voter,
        "stance": stance_upper,
        "confidence": max(0, min(100, int(req.confidence))),
        "comment": req.comment.strip(),
        "counterArgument": (req.counterArgument or "").strip() or None,
        "timestamp": now_str,
    }

    replaced = False
    for idx_v, existing in enumerate(votes):
        if normalize_agent_id(existing.get("voter", "")) == canon_voter:
            votes[idx_v] = vote_entry
            replaced = True
            break
    if not replaced:
        votes.append(vote_entry)

    stance_labels = {
        "APPROVE": "موافق (تأیید طرح)",
        "CONDITIONAL": "موافق مشروط",
        "CRITIQUE": "نقد و چالش راهبردی",
        "REJECT": "مخالف (رد طرح)",
    }
    stance_badge = stance_labels.get(stance_upper, stance_upper)

    msg_entry = {
        "id": f"vote-{int(time.time() * 1000)}-{uuid.uuid4().hex[:4]}",
        "channel": "COUNCIL",
        "senderCode": canon_voter.upper(),
        "senderName": voter_name,
        "senderRole": req.voterRole or canon_voter,
        "recipientCode": "COUNCIL",
        "recipientName": "شورای تصمیم‌گیری اتاق فکر",
        "timestamp": now_str,
        "content": f"{stance_badge} (اطمینان: {vote_entry['confidence']}٪)\n{req.comment.strip()}",
        "thoughts": req.comment.strip() if stance_upper in {"APPROVE", "CONDITIONAL"} else None,
        "critique": (req.counterArgument or req.comment).strip() if stance_upper in {"CRITIQUE", "REJECT"} else None,
        "origin": req.origin,
        "subagentConvId": req.subagentConvId,
        "convId": cid,
    }
    append_message(conv, msg_entry, action_type="CRITIQUE" if stance_upper in {"CRITIQUE", "REJECT"} else "MESSAGE")

    upsert_agent_state(
        conv,
        canon_voter,
        name=voter_name,
        role=req.voterRole or canon_voter,
        status="ACTIVE",
        thought=f"{stance_badge}: {req.comment.strip()[:80]}",
    )

    save_persisted_state()
    await manager.broadcast({
        "type": "PROPOSAL_UPDATE",
        "convId": cid,
        "proposal": prop,
        "thinkTank": tt,
        "agents": conv["agents"],
        "messages": msgs,
        "interactions": conv.get("interactions", []),
        "graph": build_interaction_graph(conv),
        "roleUsage": role_usage(msgs),
    })
    return {"status": "ok", "convId": cid, "vote": vote_entry, "proposal": prop}


class SubtaskUpsertRequest(BaseModel):
    id: Optional[str] = None
    title: str
    assignee: str
    assigneeName: Optional[str] = None
    delegatedBy: Optional[str] = "team_manager"
    delegatedByName: Optional[str] = "مدیر تیم"
    status: str = "ASSIGNED"  # ASSIGNED, IN_PROGRESS, IN_REVIEW, COMPLETED, BLOCKED
    priority: str = "HIGH"  # HIGH, MEDIUM, LOW
    deliverable: Optional[str] = ""
    thoughts: Optional[str] = None
    report: Optional[str] = None
    dependencies: Optional[List[str]] = None
    lockedFiles: Optional[List[str]] = None
    acceptanceCriteria: Optional[str] = None
    origin: Optional[str] = None
    subagentConvId: Optional[str] = None
    convId: Optional[str] = None


@app.post("/api/subtasks/upsert")
async def upsert_subtask(req: SubtaskUpsertRequest):
    cid = require_conversation_id(req.convId)
    check_and_reload_state(cid)
    conv = get_or_create_conversation(cid)
    _require_case_open(conv)
    tt = conv["thinkTank"]
    msgs = conv["messages"]
    subtasks = conv.setdefault("subtasks", [])
    now_str = time.strftime("%H:%M:%S")

    canon_assignee = normalize_agent_id(req.assignee) or req.assignee.strip()
    canon_delegator = normalize_agent_id(req.delegatedBy or "team_manager") or "team_manager"
    status_upper = (req.status or "ASSIGNED").upper().strip()
    priority_upper = (req.priority or "HIGH").upper().strip()

    assignee_name = req.assigneeName or req.assignee
    for cr in load_role_catalog():
        if normalize_agent_id(cr.get("id", "")) == canon_assignee or normalize_agent_id(cr.get("agent_name", "")) == canon_assignee:
            assignee_name = req.assigneeName or cr.get("title") or cr.get("title_fa") or assignee_name
            break

    subtask_id = (req.id or "").strip()
    existing_idx = -1
    for i, st in enumerate(subtasks):
        if (subtask_id and st.get("id") == subtask_id) or (
            not subtask_id
            and st.get("title", "").strip() == req.title.strip()
            and normalize_agent_id(st.get("assignee", "")) == canon_assignee
        ):
            existing_idx = i
            subtask_id = st.get("id") or f"task-{i + 1}"
            break

    if not subtask_id:
        subtask_id = f"task-{len(subtasks) + 1}-{int(time.time()) % 10000}"

    existing_entry = subtasks[existing_idx] if existing_idx >= 0 else {}
    if req.lockedFiles is not None:
        locked_files: List[str] = []
        seen_paths: set[str] = set()
        for raw_f in req.lockedFiles:
            clean_f = str(raw_f or "").strip().replace("\\", "/")
            if clean_f and clean_f.lower() not in seen_paths:
                seen_paths.add(clean_f.lower())
                locked_files.append(clean_f)
    else:
        locked_files = list(existing_entry.get("lockedFiles") or [])

    if req.acceptanceCriteria is not None:
        acceptance_criteria = req.acceptanceCriteria.strip()
    else:
        acceptance_criteria = str(existing_entry.get("acceptanceCriteria") or "")
    if existing_idx < 0 and status_upper not in {"COMPLETED", "DONE"} and not acceptance_criteria:
        raise HTTPException(
            status_code=409,
            detail="New active subtask requires a non-empty acceptanceCriteria.",
        )

    # Reject cross-assignee file lock conflicts on active subtasks
    if status_upper not in {"COMPLETED", "DONE"} and locked_files:
        req_lock_set = {p.lower(): p for p in locked_files}
        for st in subtasks:
            if not isinstance(st, dict) or st.get("id") == subtask_id:
                continue
            if str(st.get("status") or "").upper() in {"COMPLETED", "DONE"}:
                continue
            other_owner = normalize_agent_id(st.get("assignee", ""))
            if other_owner == canon_assignee:
                continue
            for other_path in st.get("lockedFiles") or []:
                norm_other = str(other_path or "").strip().replace("\\", "/").lower()
                if norm_other in req_lock_set:
                    raise HTTPException(
                        status_code=409,
                        detail=f"File lock conflict on {req_lock_set[norm_other]} (already locked by {other_owner} in {st.get('id')}).",
                    )

    entry = {
        "id": subtask_id,
        "title": req.title.strip(),
        "assignee": canon_assignee,
        "assigneeName": assignee_name,
        "delegatedBy": canon_delegator,
        "delegatedByName": req.delegatedByName or "مدیر تیم",
        "status": status_upper,
        "priority": priority_upper,
        "deliverable": (req.deliverable or "").strip(),
        "thoughts": (req.thoughts or "").strip() or existing_entry.get("thoughts", ""),
        "report": (req.report or "").strip() or existing_entry.get("report", ""),
        "dependencies": req.dependencies if req.dependencies is not None else list(existing_entry.get("dependencies") or []),
        "lockedFiles": locked_files,
        "acceptanceCriteria": acceptance_criteria,
        "updatedAt": now_str,
    }

    if existing_idx >= 0:
        subtasks[existing_idx] = entry
    else:
        subtasks.insert(0, entry)
    _rebuild_file_locks(conv)

    # Update Think Tank progress automatically from subtasks completion ratio
    if subtasks:
        done_count = sum(1 for s in subtasks if s.get("status") == "COMPLETED")
        in_prog_count = sum(1 for s in subtasks if s.get("status") in {"IN_PROGRESS", "IN_REVIEW"})
        calc_progress = int(((done_count + 0.5 * in_prog_count) / len(subtasks)) * 100)
        tt["progress"] = max(10, min(100, calc_progress))
        if done_count < len(subtasks) and tt.get("status") in {"DISCONNECTED", "IDLE", "COMPLETED"}:
            tt["status"] = "ACTIVE"

    # Update assignee subagent state
    sub_origin = _normalize_origin(
        {
            "origin": req.origin,
            "subagentConvId": req.subagentConvId,
            "senderRole": canon_delegator if status_upper == "ASSIGNED" else canon_assignee,
        },
        conv,
    )
    verified_sub = sub_origin == "subagent"
    sub_cid = req.subagentConvId if verified_sub else None

    if status_upper == "ASSIGNED":
        if verified_sub and canon_delegator:
            upsert_agent_state(
                conv,
                canon_delegator,
                name=req.delegatedByName or None,
                status="ACTIVE",
                subagent_conv_id=sub_cid,
                verified_subagent=True,
            )
        upsert_agent_state(
            conv,
            canon_assignee,
            name=assignee_name,
            role=canon_assignee,
            status="ACTIVE",
            task=req.title.strip(),
            thought=f"در حال اجرای تسک ({status_upper}): {req.title.strip()}",
            collaborating_with=canon_delegator,
            subagent_conv_id=sub_cid if canon_assignee == canon_delegator else None,
            verified_subagent=verified_sub and canon_assignee == canon_delegator,
        )
    elif status_upper == "COMPLETED":
        other_active = any(
            s.get("id") != subtask_id
            and normalize_agent_id(s.get("assignee", "")) == canon_assignee
            and s.get("status") in {"ASSIGNED", "IN_PROGRESS", "IN_REVIEW"}
            for s in subtasks
        )
        upsert_agent_state(
            conv,
            canon_assignee,
            name=assignee_name,
            role=canon_assignee,
            status="ACTIVE" if other_active else "COMPLETED",
            task="تمام تسک‌های این عضو تکمیل شد" if not other_active else req.title.strip(),
            thought=f"تکمیل تسک: {req.deliverable or req.title.strip()}",
            subagent_conv_id=sub_cid,
            verified_subagent=verified_sub,
        )
        if not other_active:
            for ag in conv.get("agents", []):
                if normalize_agent_id(ag.get("id", "")) == canon_assignee:
                    ag["tool"] = None
                    ag["activeTool"] = None
                    ag["collaboratingWith"] = []
                    break
    else:
        upsert_agent_state(
            conv,
            canon_assignee,
            name=assignee_name,
            role=canon_assignee,
            status="ACTIVE",
            task=req.title.strip(),
            thought=f"در حال اجرای تسک ({status_upper}): {req.title.strip()}",
            collaborating_with=canon_delegator,
            subagent_conv_id=sub_cid,
            verified_subagent=verified_sub,
        )

    status_fa = {
        "ASSIGNED": "واگذاری تسک جدید",
        "IN_PROGRESS": "شروع اجرای تسک",
        "IN_REVIEW": "ارسال تسک برای بازبینی کیفیت",
        "COMPLETED": "تکمیل و تحویل تسک",
        "BLOCKED": "گزارش مانع در تسک",
    }.get(status_upper, status_upper)

    msg_content = f"{status_fa}: «{req.title.strip()}»\nمسئول اجرا: {assignee_name} ({canon_assignee})"
    if req.deliverable:
        msg_content += f"\nخروجی و شواهد: {req.deliverable.strip()}"

    default_thought = (
        f"تحلیل، بررسی پیش‌نیازها و اجرای گام‌به‌گام تسک «{req.title.strip()}» توسط {assignee_name}. "
        f"(اولویت: {priority_upper} | وضعیت فعلی: {status_upper})"
        + (f" — شواهد و فایل‌های هدف: {req.deliverable.strip()}" if req.deliverable else "")
    )
    msg_thoughts = (req.thoughts or "").strip() or entry.get("thoughts") or default_thought
    msg_report = (req.report or "").strip() or entry.get("report") or None

    append_message(conv, {
        "id": f"subtask-msg-{int(time.time() * 1000)}-{uuid.uuid4().hex[:4]}",
        "channel": "SUBAGENTS",
        "senderCode": canon_delegator.upper() if status_upper == "ASSIGNED" else canon_assignee.upper(),
        "senderName": (req.delegatedByName or "مدیر تیم") if status_upper == "ASSIGNED" else assignee_name,
        "senderRole": canon_delegator if status_upper == "ASSIGNED" else canon_assignee,
        "recipientCode": canon_assignee.upper() if status_upper == "ASSIGNED" else canon_delegator.upper(),
        "recipientName": assignee_name if status_upper == "ASSIGNED" else (req.delegatedByName or "مدیر تیم"),
        "recipientRole": canon_assignee if status_upper == "ASSIGNED" else canon_delegator,
        "timestamp": now_str,
        "content": msg_content,
        "thoughts": msg_thoughts,
        "report": msg_report,
        "origin": req.origin,
        "subagentConvId": req.subagentConvId,
        "convId": cid,
    }, action_type="DELEGATE" if status_upper == "ASSIGNED" else ("QA_DISPATCH" if status_upper == "IN_REVIEW" else "SUBTASK_UPDATE"))

    save_persisted_state()
    await manager.broadcast({
        "type": "SUBTASKS_UPDATE",
        "convId": cid,
        "subtasks": subtasks,
        "fileLocks": conv.get("fileLocks", []),
        "agents": conv["agents"],
        "thinkTank": tt,
        "messages": msgs,
        "interactions": conv.get("interactions", []),
        "graph": build_interaction_graph(conv),
        "roleUsage": role_usage(msgs),
    })
    return {"status": "ok", "convId": cid, "subtask": entry, "subtasks": subtasks, "fileLocks": conv.get("fileLocks", [])}


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
    questions: Optional[List[str]] = None
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
    evidenceCommand: Optional[str] = None
    exitCode: Optional[int] = None
    evidenceExcerpt: Optional[str] = None
    runner: Optional[str] = None
    runnerReason: Optional[str] = None
    convId: Optional[str] = None
    model_config = {"extra": "allow"}

def generate_subagent_btw_reply(content: str, agents: List[Dict[str, Any]], conv_id: str) -> Optional[Dict[str, Any]]:
    # Replies must come from an actual subagent event through the bridge.
    # The previous canned replies reported checks that had never run.
    return None

@app.post("/api/chat/send")
async def send_chat(req: ChatMessageRequest):
    cid = require_conversation_id(req.convId)
    check_and_reload_state(cid)
    conv = get_or_create_conversation(cid)
    _require_case_open(conv)

    msg_dict = req.model_dump()
    if not msg_dict.get("id"):
        msg_dict["id"] = f"msg-{int(time.time() * 1000)}-{uuid.uuid4().hex[:6]}"
    if not msg_dict.get("timestamp"):
        msg_dict["timestamp"] = time.strftime("%H:%M:%S")

    # Auto-detect recipient from @mention in content if not explicitly passed
    if not (msg_dict.get("recipient") or msg_dict.get("recipientName") or msg_dict.get("recipientCode")):
        mention_match = re.search(r"@([A-Za-z0-9_\u0600-\u06FF-]+)", msg_dict.get("content", ""))
        if mention_match:
            recip = mention_match.group(1).strip()
            msg_dict["recipient"] = recip
            msg_dict["recipientName"] = recip
            msg_dict["recipientCode"] = recip.upper()

    if any(existing.get("id") == msg_dict.get("id") for existing in conv["messages"] if isinstance(existing, dict)):
        return {"status": "duplicate", "convId": cid, "message": msg_dict}
    bucket = role_bucket(msg_dict.get("senderRole"))
    if msg_dict.get("isReview"):
        review = conv.get("review") or {}
        if bucket not in {"main", "manager"}:
            raise HTTPException(status_code=409, detail="Only the main agent and team manager can post review messages.")
        if (
            review.get("status") not in {"DISPATCH_PENDING", "DISPATCH_FAILED", "AWAITING_TEAM_REVIEW"}
            or not msg_dict.get("reviewId")
            or msg_dict.get("reviewId") != review.get("id")
        ):
            raise HTTPException(status_code=409, detail="Review messages must reference the current pending review request.")
    elif not msg_dict.get("isOperator"):
        _enforce_role_cap(conv, msg_dict.get("senderRole"), is_review=False, review_id=msg_dict.get("reviewId"))
    is_btw_inquiry = msg_dict.get("isBtw") or msg_dict.get("content", "").startswith("/btw") or "/btw" in msg_dict.get("senderCode", "")
    if is_btw_inquiry:
        msg_dict["isBtw"] = True
        msg_dict["channel"] = "SUBAGENTS"
    elif msg_dict.get("channel") == "ALL":
        msg_dict["channel"] = "MAIN"

    # Track subagent-to-subagent peer activity unless conversation is already closed
    agents_modified = False
    is_session_closed = str((conv.get("thinkTank") or {}).get("status") or "").upper() in {"COMPLETED", "DONE", "CLOSED"}
    sender_clean = normalize_agent_id(msg_dict.get("senderCode") or msg_dict.get("senderRole"))
    recipient_clean = normalize_agent_id(msg_dict.get("recipient") or msg_dict.get("recipientCode") or msg_dict.get("recipientRole"))

    if sender_clean and not msg_dict.get("isOperator") and sender_clean != "user" and not is_session_closed:
        resolved_origin = _normalize_origin(msg_dict, conv)
        verified_sub = resolved_origin == "subagent"
        agents_modified |= upsert_agent_state(
            conv,
            sender_clean,
            name=msg_dict.get("senderName"),
            role=msg_dict.get("senderRole"),
            code=msg_dict.get("senderCode"),
            status="ACTIVE",
            thought=msg_dict.get("thoughts") or msg_dict.get("thought"),
            collaborating_with=recipient_clean if (recipient_clean and recipient_clean != sender_clean) else None,
            increment_turn=True,
            subagent_conv_id=msg_dict.get("subagentConvId") if verified_sub else None,
            verified_subagent=verified_sub,
        )
    if recipient_clean and recipient_clean != sender_clean and recipient_clean != "user" and not is_session_closed:
        agents_modified |= upsert_agent_state(
            conv,
            recipient_clean,
            name=msg_dict.get("recipientName") or msg_dict.get("recipient"),
            role=msg_dict.get("recipientRole"),
            code=msg_dict.get("recipientCode"),
            status="ACTIVE",
            collaborating_with=sender_clean,
        )

    append_message(conv, msg_dict)
    save_persisted_state()
    await manager.broadcast({
        "type": "NEW_MESSAGE",
        "convId": cid,
        "message": msg_dict,
        "thinkTank": conv["thinkTank"],
        "originCounts": _compute_origin_counts(conv),
        "interactions": conv.get("interactions", []),
        "graph": build_interaction_graph(conv),
        "roleUsage": role_usage(conv.get("messages", [])),
    })
    if agents_modified:
        await manager.broadcast({
            "type": "AGENTS_UPDATE",
            "convId": cid,
            "agents": conv["agents"]
        })

    if is_btw_inquiry and msg_dict.get("isOperator"):
        reply = generate_subagent_btw_reply(msg_dict.get("content", ""), conv["agents"], cid)
        if reply:
            append_message(conv, reply)
            save_persisted_state()
            await manager.broadcast({
                "type": "NEW_MESSAGE",
                "convId": cid,
                "message": reply,
                "interactions": conv.get("interactions", []),
                "graph": build_interaction_graph(conv),
                "roleUsage": role_usage(conv.get("messages", [])),
            })

    return {"status": "sent", "convId": cid, "message": msg_dict}


# --- Deliberation Round Governance Endpoints ---

class ExtendRoundsRequest(BaseModel):
    additionalRounds: int = Field(default=3, ge=1, le=50)
    convId: Optional[str] = None


@app.post("/api/governance/extend_rounds")
async def extend_rounds_endpoint(req: ExtendRoundsRequest):
    cid = require_conversation_id(req.convId)
    conv = get_or_create_conversation(cid)
    _require_case_open(conv)
    tt = conv["thinkTank"]
    tt["maxRounds"] = normalize_round_limit(tt.get("maxRounds", 50))
    tt["maxRounds"] = min(500, tt["maxRounds"] + req.additionalRounds)
    tt["roundStatus"] = "ACTIVE"

    msg = {
        "id": f"gov-{uuid.uuid4()}",
        "channel": "MAIN",
        "senderCode": "OWNER",
        "senderName": "کاربر",
        "senderRole": "owner",
        "isOperator": True,
        "timestamp": time.strftime("%H:%M:%S"),
        "content": f"سقف دورهای گفتگو با درخواست کاربر به {tt['maxRounds']} افزایش یافت.",
    }
    append_message(conv, msg, action_type="GOVERNANCE")
    save_persisted_state()
    await manager.broadcast({
        "type": "GOVERNANCE_UPDATE",
        "convId": cid,
        "thinkTank": tt,
        "review": conv.get("review"),
        "message": msg,
        "interactions": conv.get("interactions", []),
        "graph": build_interaction_graph(conv),
        "roleUsage": role_usage(conv.get("messages", [])),
    })
    return {"status": "extended", "convId": cid, "maxRounds": tt["maxRounds"], "roundStatus": "ACTIVE"}


class CompressFinalRequest(BaseModel):
    convId: Optional[str] = None


@app.post("/api/governance/compress_final")
async def compress_final_endpoint(req: CompressFinalRequest):
    """Request a real manager review; never synthesize an agent proposal or vote."""
    cid = require_conversation_id(req.convId)
    conv = get_or_create_conversation(cid)
    _require_case_open(conv)
    tt = conv["thinkTank"]
    tt["roundStatus"] = "REVIEW_REQUESTED"
    tt["phase"] = "درخواست بازبینی مدیر تیم"
    review_id = f"review-{uuid.uuid4()}"
    conv["review"] = {
        "id": review_id,
        "status": "DISPATCH_PENDING",
        "dispatchStatus": "pending",
        "requestedAt": time.time(),
        "confidence": None,
        "confidenceLabel": "evidence_score",
        "humanRequired": False,
        "managerSummary": "",
        "mainSummary": "",
        "continueReasons": [],
        "completionReasons": [],
        "evidence": [],
        "decision": None,
    }
    save_persisted_state()
    await manager.broadcast({
        "type": "GOVERNANCE_REVIEW_REQUEST",
        "convId": cid,
        "thinkTank": tt,
        "review": conv["review"],
        "roleUsage": role_usage(conv.get("messages", [])),
    })
    return {"status": "review_requested", "convId": cid, "review": conv["review"]}


class ReviewDispatchRequest(BaseModel):
    status: str = Field(pattern="^(sent|failed)$")
    error: Optional[str] = None
    convId: Optional[str] = None


@app.post("/api/governance/review_dispatch")
async def review_dispatch_endpoint(req: ReviewDispatchRequest):
    cid = require_conversation_id(req.convId)
    conv = get_or_create_conversation(cid)
    _require_case_open(conv)
    review = conv.get("review")
    if not review or review.get("status") not in {"DISPATCH_PENDING", "DISPATCH_FAILED", "AWAITING_TEAM_REVIEW"}:
        raise HTTPException(status_code=409, detail="There is no pending team review request.")
    review["dispatchStatus"] = req.status
    review["dispatchError"] = (req.error or "")[:800] if req.status == "failed" else ""
    review["status"] = "AWAITING_TEAM_REVIEW" if req.status == "sent" else "DISPATCH_FAILED"
    save_persisted_state()
    await manager.broadcast({
        "type": "GOVERNANCE_REVIEW_DISPATCH",
        "convId": cid,
        "review": review,
        "thinkTank": conv["thinkTank"],
        "roleUsage": role_usage(conv.get("messages", [])),
    })
    return {"status": "ok", "convId": cid, "review": review}


class ReviewSubmissionRequest(BaseModel):
    reviewId: str = Field(min_length=1, max_length=200)
    managerSummary: str = Field(min_length=1, max_length=4000)
    mainSummary: str = Field(min_length=1, max_length=4000)
    confidence: int = Field(ge=0, le=100)
    recommendation: str = Field(pattern="^(continue|complete)$")
    continueReasons: List[str] = Field(min_length=1, max_length=8)
    completionReasons: List[str] = Field(min_length=1, max_length=8)
    evidence: List[str] = Field(min_length=1, max_length=12)
    convId: Optional[str] = None


@app.post("/api/governance/submit_review")
async def submit_review_endpoint(req: ReviewSubmissionRequest):
    cid = require_conversation_id(req.convId)
    conv = get_or_create_conversation(cid)
    _require_case_open(conv)
    existing = conv.get("review")
    if not existing or existing.get("status") not in {"AWAITING_TEAM_REVIEW", "DISPATCH_PENDING"}:
        raise HTTPException(status_code=409, detail="A team review was not requested for this session.")
    if req.reviewId != existing.get("id"):
        raise HTTPException(status_code=409, detail="The review submission does not match the current review request.")

    review_messages = {
        role_bucket(message.get("senderRole")): message
        for message in conv.get("messages", [])
        if isinstance(message, dict)
        and message.get("isReview") is True
        and message.get("reviewId") == existing.get("id")
        and role_bucket(message.get("senderRole")) in {"manager", "main"}
    }
    if "manager" not in review_messages or "main" not in review_messages:
        raise HTTPException(status_code=409, detail="The team manager and main agent must first post their real review messages.")
    if (
        req.managerSummary.strip() != str(review_messages["manager"].get("content", "")).strip()
        or req.mainSummary.strip() != str(review_messages["main"].get("content", "")).strip()
    ):
        raise HTTPException(status_code=422, detail="Review summaries must match the current messages visible in the Think Tank room.")
    if not all(str(reason).strip() for reason in req.continueReasons + req.completionReasons + req.evidence):
        raise HTTPException(status_code=422, detail="Review reasons and evidence cannot be blank.")

    try:
        decision = evaluate_review(req.confidence, req.managerSummary, req.mainSummary, req.recommendation)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    review = {
        **existing,
        **decision,
        "continueReasons": [str(item).strip() for item in req.continueReasons],
        "completionReasons": [str(item).strip() for item in req.completionReasons],
        "evidence": [str(item).strip() for item in req.evidence],
        "submittedAt": time.time(),
    }
    conv["review"] = review
    tt = conv["thinkTank"]
    if review["humanRequired"]:
        tt["roundStatus"] = "WAITING_FOR_HUMAN"
        tt["phase"] = "در انتظار تصمیم شما"
    elif review["decision"] == "complete":
        tt["roundStatus"] = "COMPLETE"
        tt["status"] = "COMPLETED"
        tt["phase"] = "بازبینی مدیر و ایجنت اصلی کامل شد"
    else:
        tt["roundStatus"] = "ACTIVE"
        tt["status"] = "ACTIVE"
        tt["phase"] = "ادامه کار بر اساس بازبینی تیم"
    save_persisted_state()
    await manager.broadcast({
        "type": "GOVERNANCE_REVIEW_SUBMITTED",
        "convId": cid,
        "review": review,
        "thinkTank": tt,
        "roleUsage": role_usage(conv.get("messages", [])),
    })
    return {"status": "ok", "convId": cid, "review": review, "thinkTank": tt}


class ReviewDecisionRequest(BaseModel):
    decision: str = Field(pattern="^(continue|stop)$")
    note: Optional[str] = Field(default=None, max_length=1200)
    convId: Optional[str] = None


@app.post("/api/governance/review_decision")
async def review_decision_endpoint(req: ReviewDecisionRequest):
    cid = require_conversation_id(req.convId)
    conv = get_or_create_conversation(cid)
    _require_case_open(conv)
    review = conv.get("review")
    if not review or review.get("status") != "WAITING_FOR_HUMAN" or not review.get("humanRequired"):
        raise HTTPException(status_code=409, detail="No human decision is currently required.")

    decided_at = time.time()
    review["decision"] = req.decision
    review["humanDecision"] = {"decision": req.decision, "note": req.note or "", "decidedAt": decided_at, "dispatchStatus": "pending"}
    review["status"] = "HUMAN_CONTINUE" if req.decision == "continue" else "HUMAN_STOP"
    tt = conv["thinkTank"]
    tt["roundStatus"] = "ACTIVE" if req.decision == "continue" else "HALTED"
    tt["status"] = "ACTIVE" if req.decision == "continue" else "HALTED"
    tt["phase"] = "ادامه با تصمیم کاربر" if req.decision == "continue" else "توقف با تصمیم کاربر"
    msg = {
        "id": f"review-decision-{uuid.uuid4()}",
        "channel": "MAIN",
        "senderCode": "OWNER",
        "senderName": "کاربر",
        "senderRole": "owner",
        "isOperator": True,
        "timestamp": time.strftime("%H:%M:%S"),
        "content": ("ادامهٔ کار" if req.decision == "continue" else "توقف کار") + (f" — {req.note.strip()}" if req.note and req.note.strip() else ""),
    }
    append_message(conv, msg, action_type="DECISION")
    save_persisted_state()
    await manager.broadcast({
        "type": "GOVERNANCE_REVIEW_DECISION",
        "convId": cid,
        "review": review,
        "thinkTank": tt,
        "message": msg,
        "interactions": conv.get("interactions", []),
        "graph": build_interaction_graph(conv),
        "roleUsage": role_usage(conv.get("messages", [])),
    })
    return {"status": "ok", "convId": cid, "review": review, "thinkTank": tt}


class ReviewDecisionDispatchRequest(BaseModel):
    status: str = Field(pattern="^(sent|failed)$")
    error: Optional[str] = None
    convId: Optional[str] = None


@app.post("/api/governance/review_decision_dispatch")
async def review_decision_dispatch_endpoint(req: ReviewDecisionDispatchRequest):
    cid = require_conversation_id(req.convId)
    conv = get_or_create_conversation(cid)
    review = conv.get("review")
    human_decision = (review or {}).get("humanDecision")
    if not human_decision:
        raise HTTPException(status_code=409, detail="There is no human review decision to deliver.")
    human_decision["dispatchStatus"] = req.status
    human_decision["dispatchError"] = (req.error or "")[:800] if req.status == "failed" else ""
    save_persisted_state()
    await manager.broadcast({
        "type": "GOVERNANCE_REVIEW_DISPATCH",
        "convId": cid,
        "review": review,
        "thinkTank": conv["thinkTank"],
        "roleUsage": role_usage(conv.get("messages", [])),
    })
    return {"status": "ok", "convId": cid, "review": review}


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


class FindingActionRequest(BaseModel):
    convId: Optional[str] = None
    findingId: str
    action: str  # "ack" | "wontfix" | "mark_important"
    reason: Optional[str] = None


def _derive_collab_channel(action_upper: str, explicit_channel: Optional[str]) -> str:
    if explicit_channel and explicit_channel.strip():
        return explicit_channel.strip().upper()
    if action_upper in {"RETURN_DEFECT", "INTERROGATE", "INTERROGATE_REPLY", "CRITIQUE"}:
        return "INTERROGATION"
    if action_upper in {"WORKER_FIX", "REVIEW_QUERY", "QA_DISPATCH", "QA_REPORT"}:
        return "QA"
    if action_upper == "PEER_SYNC":
        return "SYNC"
    return "SUBAGENTS"


@app.post("/api/findings/action")
async def finding_action_endpoint(req: FindingActionRequest):
    cid = require_conversation_id(req.convId)
    check_and_reload_state(cid)
    conv = get_or_create_conversation(cid)
    _require_case_open(conv)
    finding = _find_finding(conv, req.findingId)
    if not finding:
        raise HTTPException(status_code=404, detail=f"Finding {req.findingId} not found.")

    action_lower = (req.action or "").strip().lower()
    now_hms = time.strftime("%H:%M:%S")
    if action_lower == "ack":
        finding["state"] = "Fixing"
        finding["updatedAt"] = now_hms
    elif action_lower == "wontfix":
        reason_clean = (req.reason or "").strip()
        if not reason_clean:
            raise HTTPException(status_code=409, detail="A non-empty reason is required for wontfix.")
        finding["state"] = "WontFix"
        finding["wontFixReason"] = reason_clean
        finding["updatedAt"] = now_hms
    elif action_lower == "mark_important":
        finding["markedImportant"] = not bool(finding.get("markedImportant"))
        finding["updatedAt"] = now_hms
    else:
        raise HTTPException(status_code=400, detail="Invalid finding action; expected ack, wontfix, or mark_important.")

    save_persisted_state()
    await manager.broadcast({
        "type": "FINDINGS_UPDATE",
        "convId": cid,
        "findings": conv.get("findings", []),
        "thinkTank": conv["thinkTank"],
        "roleUsage": role_usage(conv.get("messages", [])),
    })
    return {"status": "ok", "convId": cid, "finding": finding, "findings": conv.get("findings", [])}


CANONICAL_FINDING_STATES = {
    "open": "Open",
    "fixing": "Fixing",
    "inreview": "InReview",
    "in_review": "InReview",
    "testing": "Testing",
    "verified": "Verified",
    "closed": "Closed",
    "wontfix": "WontFix",
    "wont_fix": "WontFix",
}


@app.post("/api/agent/collaborate")
async def collaborate_endpoint(req: CollaborateRequest):
    cid = require_conversation_id(req.convId)
    check_and_reload_state(cid)
    conv = get_or_create_conversation(cid)
    _require_case_open(conv)

    from_id = normalize_agent_id(req.fromAgent)
    to_id = normalize_agent_id(req.toAgent)
    _enforce_role_cap(conv, from_id or req.fromAgent)
    action_upper = (req.action or "PEER_SYNC").strip().upper()
    target_channel = _derive_collab_channel(action_upper, req.channel)
    severity_clean = req.severity.strip().lower() if req.severity and req.severity.strip() else None
    result_upper = str(req.result or "").strip().upper()

    # Validate Finding lifecycle, critic limits, & QA Evidence gates before mutating state
    findings_list = conv.setdefault("findings", [])
    req_fid = (req.findingId or "").strip().upper() or None
    if action_upper in {"WORKER_FIX", "QA_DISPATCH", "QA_REPORT"} and not req_fid:
        raise HTTPException(status_code=409, detail=f"{action_upper} requires a non-empty findingId.")
    finding = _find_finding(conv, req_fid) if req_fid else None
    if action_upper in {"WORKER_FIX", "REVIEW_QUERY", "QA_DISPATCH", "QA_REPORT"} and req_fid and finding is None:
        raise HTTPException(status_code=404, detail=f"Finding {req_fid} not found.")
    if finding is not None:
        raw_state = str(finding.get("state") or "Open").strip()
        cur_state = CANONICAL_FINDING_STATES.get(raw_state.lower(), raw_state)
        if cur_state in {"Closed", "WontFix"} and action_upper in {"WORKER_FIX", "QA_DISPATCH", "QA_REPORT", "RETURN_DEFECT"}:
            raise HTTPException(
                status_code=409,
                detail=f"Finding {finding.get('id')} is {cur_state} and cannot accept {action_upper}.",
            )
        if action_upper == "REVIEW_QUERY" and cur_state not in {"Open", "Fixing", "InReview", "Testing"}:
            raise HTTPException(
                status_code=409,
                detail=f"REVIEW_QUERY cannot run on finding {finding.get('id')} in state {cur_state}.",
            )
        if action_upper == "WORKER_FIX" and cur_state not in {"Open", "Fixing", "InReview"}:
            raise HTTPException(
                status_code=409,
                detail=f"WORKER_FIX requires finding state in Open, Fixing, or InReview (got {cur_state}).",
            )
        if action_upper == "QA_DISPATCH" and cur_state not in {"InReview", "Testing"}:
            raise HTTPException(
                status_code=409,
                detail=f"QA_DISPATCH requires finding state in InReview or Testing (got {cur_state}).",
            )
        if action_upper == "QA_REPORT" and cur_state != "Testing":
            raise HTTPException(
                status_code=409,
                detail=f"QA_REPORT requires finding state to be Testing (got {cur_state}).",
            )
    cur_round = int((conv.get("thinkTank") or {}).get("round") or 1)
    repro_clean = (req.reproSteps or req.question or "").strip()
    if action_upper == "RETURN_DEFECT":
        sev_upper = (req.severity or "HIGH").strip().upper()
        if sev_upper not in {"CRITICAL", "HIGH", "MEDIUM"}:
            raise HTTPException(status_code=400, detail="Severity must be CRITICAL, HIGH, or MEDIUM.")
        if not repro_clean:
            raise HTTPException(status_code=409, detail="RETURN_DEFECT requires non-empty reproSteps.")
        if finding is None:
            round_count = sum(
                1 for f in findings_list
                if isinstance(f, dict) and int(f.get("round") or 1) == cur_round
            )
            if round_count >= 7:
                raise HTTPException(status_code=409, detail="Maximum 7 findings per round reached.")
    if action_upper == "QA_REPORT":
        if (req.runner or "substrate").strip().lower() == "host-fallback" and not (req.runnerReason or "").strip():
            raise HTTPException(status_code=409, detail="runner='host-fallback' requires a non-empty runnerReason.")
        if result_upper == "PASS":
            if not (req.evidenceCommand or "").strip() or req.exitCode is None or int(req.exitCode) != 0:
                raise HTTPException(
                    status_code=409,
                    detail="QA_REPORT PASS requires a non-empty evidenceCommand and exitCode == 0.",
                )

    now_hms = time.strftime("%H:%M:%S")
    effective_fid = finding["id"] if finding else req_fid
    if action_upper == "RETURN_DEFECT" and finding is None:
        effective_fid = req_fid or _next_finding_id(conv)

    collabs = conv.setdefault("collaborations", [])
    existing = next(
        (
            c
            for c in collabs
            if (c.get("from") == from_id and c.get("to") == to_id)
            or (c.get("from") == to_id and c.get("to") == from_id)
        ),
        None,
    )
    is_collab_active = not (action_upper == "QA_REPORT" and result_upper == "PASS")
    if existing:
        existing["active"] = is_collab_active
        existing["action"] = action_upper
        existing["channel"] = target_channel
        if severity_clean:
            existing["severity"] = severity_clean
        existing["label"] = req.label or existing.get("label", "همکاری و مباحثه فعال")
    else:
        existing = {
            "from": from_id,
            "to": to_id,
            "action": action_upper,
            "channel": target_channel,
            "label": req.label or "همکاری و مباحثه فعال",
            "active": is_collab_active,
        }
        if severity_clean:
            existing["severity"] = severity_clean
        collabs.append(existing)

    if action_upper == "QA_REPORT" and result_upper == "PASS":
        has_other_open = any(
            isinstance(f, dict) and f.get("id") != effective_fid and str(f.get("state") or "").lower() in {"open", "fixing", "inreview", "testing"}
            for f in findings_list
        )
        if not has_other_open:
            for c in collabs:
                if isinstance(c, dict) and c.get("channel") in {"QA", "INTERROGATION"}:
                    c["active"] = False

    catalog = load_role_catalog()
    from_name = next((a.get("name") for a in conv["agents"] if normalize_agent_id(a.get("id")) == from_id), None)
    if not from_name:
        from_name = next((r.get("title") for r in catalog if normalize_agent_id(r.get("id")) == from_id), from_id.upper())
    to_name = next((a.get("name") for a in conv["agents"] if normalize_agent_id(a.get("id")) == to_id), None)
    if not to_name:
        to_name = next((r.get("title") for r in catalog if normalize_agent_id(r.get("id")) == to_id), to_id.upper())

    target_task_hint = None
    if action_upper == "RETURN_DEFECT":
        target_task_hint = f"در حال رفع ایراد برگشتی از {from_name}"
    elif action_upper == "WORKER_FIX":
        target_task_hint = f"بازبینی اصلاحیه ارسال‌شده از {from_name}"
    elif action_upper == "REVIEW_QUERY":
        target_task_hint = f"پاسخ به پرسش بررسی از {from_name}"
    elif action_upper == "INTERROGATE":
        target_task_hint = f"در حال پاسخ‌گویی به بازخواست از {from_name}"
    elif action_upper == "QA_DISPATCH":
        target_task_hint = f"اجرای تست QA به دستور {from_name}"
    elif action_upper == "QA_REPORT" and req.result:
        target_task_hint = f"گزارش QA ثبت شد ({req.result.upper()})"

    collab_origin = _normalize_origin({"origin": req.origin, "subagentConvId": req.subagentConvId, "senderRole": from_id}, conv)
    verified_sub = collab_origin == "subagent"
    upsert_agent_state(
        conv,
        from_id,
        name=from_name,
        status="ACTIVE",
        thought=req.thoughts or req.thought or req.question or req.critique,
        collaborating_with=to_id,
        increment_turn=True,
        subagent_conv_id=req.subagentConvId if verified_sub else None,
        verified_subagent=verified_sub,
    )
    upsert_agent_state(
        conv,
        to_id,
        name=to_name,
        status="ACTIVE",
        task=target_task_hint,
        collaborating_with=from_id,
    )

    msg_text = req.content or req.crosstalkMessage or req.question or req.critique or req.report or req.fullReport
    if not msg_text and (effective_fid or action_upper in {"RETURN_DEFECT", "WORKER_FIX", "REVIEW_QUERY", "QA_DISPATCH", "QA_REPORT"}):
        msg_text = req.label or action_upper

    collab_msg = None
    if msg_text:
        collab_msg = {
            "id": f"collab-{int(time.time() * 1000)}-{uuid.uuid4().hex[:6]}",
            "channel": target_channel,
            "action": action_upper,
            "requestType": req.requestType,
            "severity": severity_clean,
            "parentSeq": req.parentSeq,
            "result": result_upper or None,
            "senderCode": from_id.upper(),
            "senderName": from_name,
            "senderRole": from_id,
            "recipientCode": to_id.upper(),
            "recipientName": to_name,
            "recipientRole": to_id,
            "recipient": to_id,
            "timestamp": now_hms,
            "content": msg_text,
            "thoughts": req.thoughts or req.thought,
            "critique": req.critique,
            "question": req.question,
            "report": req.report or req.fullReport,
            "origin": req.origin,
            "subagentConvId": req.subagentConvId,
            "findingId": effective_fid,
            "workItemId": req.workItemId,
            "reproSteps": req.reproSteps,
            "convId": cid,
        }
        append_message(conv, collab_msg, action_type=action_upper, severity=severity_clean, label=req.label)
        existing["lastSeq"] = collab_msg.get("seq")
    else:
        _sync_pipeline_fields(conv)

    ev_seq = collab_msg.get("seq") if collab_msg else None
    if action_upper == "RETURN_DEFECT":
        if finding is not None:
            finding["state"] = "Fixing"
            finding["returnCount"] = int(finding.get("returnCount") or 0) + 1
            finding["reproSteps"] = repro_clean
            if req.workItemId:
                finding["workItemId"] = req.workItemId
            finding["updatedAt"] = now_hms
            if ev_seq and ev_seq not in finding.setdefault("events", []):
                finding["events"].append(ev_seq)
        else:
            title_src = req.critique or req.question or req.content or req.crosstalkMessage or req.label or "Defect"
            finding = {
                "id": effective_fid,
                "title": str(title_src).strip().splitlines()[0][:160],
                "severity": (req.severity or "HIGH").strip().upper(),
                "owner": to_id,
                "raisedBy": from_id,
                "workItemId": req.workItemId,
                "round": cur_round,
                "state": "Open",
                "reproSteps": (req.reproSteps or req.question or "").strip(),
                "returnCount": 0,
                "wontFixReason": None,
                "markedImportant": False,
                "events": [ev_seq] if ev_seq else [],
                "evidence": [],
                "createdAt": now_hms,
                "updatedAt": now_hms,
            }
            findings_list.append(finding)
    elif action_upper == "WORKER_FIX" and finding is not None:
        finding["state"] = "InReview"
        finding["updatedAt"] = now_hms
        if ev_seq and ev_seq not in finding.setdefault("events", []):
            finding["events"].append(ev_seq)
    elif action_upper == "REVIEW_QUERY" and finding is not None:
        sev_upper = str(req.severity or "").strip().upper()
        if result_upper == "REJECT" or sev_upper in {"HIGH", "CRITICAL"}:
            finding["state"] = "Fixing"
            finding["returnCount"] = int(finding.get("returnCount") or 0) + 1
        finding["updatedAt"] = now_hms
        if ev_seq and ev_seq not in finding.setdefault("events", []):
            finding["events"].append(ev_seq)
    elif action_upper == "QA_DISPATCH" and finding is not None:
        finding["state"] = "Testing"
        finding["updatedAt"] = now_hms
        if ev_seq and ev_seq not in finding.setdefault("events", []):
            finding["events"].append(ev_seq)
    elif action_upper == "QA_REPORT":
        has_ev_input = bool(finding is not None or (req.evidenceCommand or "").strip() or req.exitCode is not None or req.evidenceExcerpt is not None)
        if has_ev_input:
            raw_excerpt = req.evidenceExcerpt if req.evidenceExcerpt is not None else (req.report or req.fullReport or msg_text or "")
            excerpt_lines = str(raw_excerpt).splitlines()
            excerpt_text = "\n".join(excerpt_lines[:20]) if len(excerpt_lines) > 20 else str(raw_excerpt)
            ev_record = {
                "seq": ev_seq,
                "command": (req.evidenceCommand or "").strip(),
                "exitCode": req.exitCode,
                "stdoutHash": hashlib.sha256(excerpt_text.encode("utf-8")).hexdigest(),
                "excerpt": excerpt_text,
                "runner": (req.runner or "substrate").strip(),
                "runnerReason": (req.runnerReason or "").strip() or None,
                "timestamp": now_hms,
            }
            if collab_msg is not None:
                collab_msg["evidence"] = ev_record
            if finding is not None:
                finding.setdefault("evidence", []).append(ev_record)
        if finding is not None:
            if ev_seq and ev_seq not in finding.setdefault("events", []):
                finding["events"].append(ev_seq)
            if result_upper == "PASS":
                finding["state"] = "Verified"
            else:
                finding["state"] = "Fixing"
                finding["returnCount"] = int(finding.get("returnCount") or 0) + 1
            finding["updatedAt"] = now_hms

    graph_data = build_interaction_graph(conv)
    origin_counts = _compute_origin_counts(conv)
    save_persisted_state()
    if collab_msg:
        await manager.broadcast({
            "type": "NEW_MESSAGE",
            "convId": cid,
            "message": collab_msg,
            "thinkTank": conv["thinkTank"],
            "findings": findings_list,
            "originCounts": origin_counts,
            "interactions": conv.get("interactions", []),
            "graph": graph_data,
            "roleUsage": role_usage(conv.get("messages", [])),
        })
    await manager.broadcast({
        "type": "COLLABORATION_UPDATE",
        "convId": cid,
        "thinkTank": conv["thinkTank"],
        "collaborations": collabs,
        "findings": findings_list,
        "originCounts": origin_counts,
        "interactions": conv.get("interactions", []),
        "graph": graph_data,
        "agents": conv["agents"],
        "messages": conv["messages"],
        "roleUsage": role_usage(conv.get("messages", [])),
    })
    await manager.broadcast({
        "type": "AGENTS_UPDATE",
        "convId": cid,
        "agents": conv["agents"],
    })
    return {
        "status": "ok",
        "convId": cid,
        "thinkTank": conv["thinkTank"],
        "collaborations": collabs,
        "findings": findings_list,
        "finding": finding,
        "originCounts": origin_counts,
        "interactions": conv.get("interactions", []),
        "graph": graph_data,
        "message": collab_msg,
    }


# --- Telemetry & Process Inspection Endpoints ---

@app.get("/api/telemetry")
def get_telemetry(convId: Optional[str] = Query(None), conv_id: Optional[str] = Query(None)):
    cid = (convId or conv_id or "").strip() or active_conv_id
    if not project_matches(conversations_store.get(cid, {}), request_project_id.get()):
        raise HTTPException(status_code=403, detail="This session is not assigned to the active project.")
    check_and_reload_state(cid)
    conv = get_or_create_conversation(cid)
    return conv["telemetry"]


class AntigravityToolEventRequest(BaseModel):
    id: str = Field(min_length=1, max_length=200)
    convId: str = Field(min_length=1, max_length=200)
    tool: str = Field(min_length=1, max_length=120)
    status: str = Field(pattern="^(SUCCESS|ERROR)$")
    stepIdx: int = Field(ge=0)
    args: Optional[Dict[str, Any]] = None
    output: Optional[str] = None
    error: Optional[str] = None
    agentId: Optional[str] = None
    agentName: Optional[str] = None
    parentConversationId: Optional[str] = None
    roleId: Optional[str] = None
    roleTitle: Optional[str] = None
    model_config = {"extra": "allow"}


@app.post("/api/telemetry/host_tool")
async def log_antigravity_tool_event(req: AntigravityToolEventRequest):
    raw_cid = require_conversation_id(req.convId)
    mapped = _ensure_subagent_mapping(
        raw_cid,
        parent_cid=req.parentConversationId,
        role_id=req.roleId,
        role_title=req.roleTitle,
    )
    cid = mapped["parentConvId"] if mapped else raw_cid
    if cid != raw_cid and not project_matches(conversations_store.get(cid, {}), request_project_id.get()):
        raise HTTPException(status_code=403, detail="This session is not assigned to the active project.")
    conv = get_or_create_conversation(cid)
    tt = conv.setdefault("thinkTank", {})
    had_tt_before = has_thinktank_activity(conv)
    is_closed = bool(tt.get("isClosed")) or str(tt.get("status") or "").upper() in {"COMPLETED", "DONE", "CLOSED"}
    if not is_closed and tt.get("status") in {"DISCONNECTED", "UNKNOWN", "IDLE"}:
        tt["status"] = "ACTIVE"
        if not had_tt_before:
            conv["_telemetryOnly"] = True

    telemetry = conv.setdefault("telemetry", {"toolCalls": [], "terminalLogs": [], "backgroundTasks": []})
    calls = telemetry.setdefault("toolCalls", [])
    previous = next((call for call in calls if call.get("id") == req.id), None)
    if previous:
        return {"status": "duplicate", "convId": cid, "entry": previous}

    mapped_role = mapped.get("roleId") if mapped else None
    entry_agent_id = mapped_role or req.agentId or "antigravity"
    entry_agent_name = (
        req.agentName
        if (req.agentName and req.agentName != "Antigravity")
        else (mapped.get("roleTitle") or mapped_role if mapped else (req.agentName or "Antigravity"))
    )
    tool_name = req.tool.strip()
    entry = SyncEventStore.compact_tool_entry({
        "id": req.id,
        "agentId": entry_agent_id,
        "agentName": entry_agent_name,
        "tool": tool_name,
        "args": req.args or {},
        "output": req.output or "",
        "error": req.error or "",
        "status": req.status,
        "latencyMs": None,
        "timestamp": time.strftime("%H:%M:%S"),
        "source": "antigravity-hook",
        "stepIdx": req.stepIdx,
    })
    if mapped:
        entry["subagentConvId"] = raw_cid
    calls.insert(0, entry)
    telemetry["toolCalls"] = calls[:25]

    # Do not re-activate an already closed session when host tool telemetry arrives
    agent_updated = False
    durable_agent_event = False
    if not is_closed:
        if mapped_role and mapped_role not in {"user", "subagent"}:
            was_known = any(normalize_agent_id(a.get("id", "")) == mapped_role and a.get("verifiedSubagent") for a in conv.get("agents") or [])
            changed = upsert_agent_state(
                conv,
                mapped_role,
                name=req.agentName if (req.agentName and req.agentName != "Antigravity") else None,
                tool=tool_name,
                status="WORKING",
                subagent_conv_id=raw_cid,
                verified_subagent=True,
                increment_turn=True,
            )
            agent_updated |= changed
            if changed and not was_known:
                durable_agent_event = True
        else:
            ag_target = normalize_agent_id(req.agentId or "main_agent")
            if ag_target and ag_target != "user":
                agent_updated |= upsert_agent_state(
                    conv,
                    ag_target,
                    name=req.agentName,
                    tool=tool_name,
                    status="ACTIVE",
                )

        if tool_name.endswith("invoke_subagent"):
            durable_agent_event = True
            args = req.args or {}
            type_name = str(args.get("TypeName") or args.get("typeName") or args.get("type_name") or "").strip()
            role_desc = str(args.get("Role") or args.get("role") or args.get("Description") or "").strip()
            role_id = normalize_agent_id(type_name) or normalize_agent_id(role_desc)
            if len(role_id) > 48 and " " in role_id:
                role_id = ""
            uuid_matches = re.findall(
                r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
                req.output or "",
                re.IGNORECASE,
            )
            spawned_cid = next((u for u in uuid_matches if u.lower() not in {cid.lower(), raw_cid.lower()}), None)
            if spawned_cid and role_id and role_id != "user":
                subagent_session_map[spawned_cid] = {
                    "parentConvId": cid,
                    "roleId": role_id,
                    "roleTitle": role_desc,
                }
                _save_subagent_link(spawned_cid, cid, role_id, role_desc or None)
                if spawned_cid in conversations_store and _is_phantom_child_conv(conversations_store[spawned_cid]):
                    conversations_store.pop(spawned_cid, None)
                agent_updated |= upsert_agent_state(
                    conv,
                    role_id,
                    task=role_desc or None,
                    tool="invoke_subagent",
                    status="WORKING",
                    subagent_conv_id=spawned_cid,
                    verified_subagent=True,
                    increment_turn=True,
                )
            elif role_id and role_id != "user":
                pending_subagent_invokes.setdefault(cid, []).append({
                    "roleId": role_id,
                    "roleTitle": role_desc,
                    "ts": time.time(),
                })
                agent_updated |= upsert_agent_state(
                    conv,
                    role_id,
                    task=role_desc or None,
                    tool="invoke_subagent",
                    status="WORKING",
                    increment_turn=True,
                )
        elif tool_name.endswith("send_message"):
            args = req.args or {}
            recip_cid = str(args.get("Recipient") or args.get("recipient") or "").strip()
            if recip_cid:
                recip_info = _ensure_subagent_mapping(recip_cid)
                recip_role = recip_info.get("roleId") if recip_info else None
                if recip_role and recip_role not in {"user", "subagent"}:
                    durable_agent_event = True
                    agent_updated |= upsert_agent_state(
                        conv,
                        recip_role,
                        tool="send_message",
                        status="WORKING",
                        subagent_conv_id=recip_cid,
                        verified_subagent=True,
                        increment_turn=True,
                    )

    sync_store.save_snapshot_only(cid, conv)
    schedule_persisted_state_save()
    await manager.broadcast_transient({"type": "TELEMETRY_UPDATE", "convId": cid, "telemetryEntry": entry})
    if agent_updated:
        if durable_agent_event and has_thinktank_activity(conv):
            await manager.broadcast({"type": "AGENTS_UPDATE", "convId": cid, "agents": conv["agents"]})
        else:
            await manager.broadcast_transient({"type": "AGENTS_UPDATE", "convId": cid, "agents": conv["agents"]})
    return {"status": "ok", "convId": cid, "entry": entry}


class ToolCallLogRequest(BaseModel):
    id: Optional[str] = None
    agentId: str
    agentName: Optional[str] = None
    tool: str
    args: Optional[Dict[str, Any]] = None
    output: str
    status: str = "SUCCESS"
    latencyMs: Optional[int] = None
    convId: Optional[str] = None


@app.post("/api/telemetry/tool_call")
async def log_tool_call(req: ToolCallLogRequest):
    cid = require_conversation_id(req.convId)
    check_and_reload_state(cid)
    conv = get_or_create_conversation(cid)
    
    call_id = req.id or f"tc-{int(time.time()*1000)}"
    entry = SyncEventStore.compact_tool_entry({
        "id": call_id,
        "agentId": req.agentId,
        "agentName": req.agentName or req.agentId,
        "tool": req.tool,
        "args": req.args or {},
        "output": req.output,
        "status": req.status,
        "latencyMs": req.latencyMs,
        "timestamp": time.strftime("%H:%M:%S")
    })
    telem = conv["telemetry"]
    telem.setdefault("toolCalls", []).insert(0, entry)
    if len(telem["toolCalls"]) > 25:
        telem["toolCalls"] = telem["toolCalls"][:25]

    ag_target = normalize_agent_id(req.agentId or "main_agent")
    agent_updated = False
    if ag_target and ag_target != "user":
        agent_updated = upsert_agent_state(
            conv,
            ag_target,
            name=req.agentName,
            tool=req.tool.strip(),
            status="ACTIVE",
        )

    sync_store.save_snapshot_only(cid, conv)
    schedule_persisted_state_save()
    await manager.broadcast_transient({
        "type": "TELEMETRY_UPDATE",
        "convId": cid,
        "telemetryEntry": entry,
    })
    if agent_updated:
        await manager.broadcast_transient({
            "type": "AGENTS_UPDATE",
            "convId": cid,
            "agents": conv["agents"]
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
async def log_terminal(req: TerminalLogRequest):
    cid = require_conversation_id(req.convId)
    check_and_reload_state(cid)
    conv = get_or_create_conversation(cid)
    
    log_id = req.id or f"tl-{int(time.time()*1000)}"
    entry = {
        "id": log_id,
        "agentId": req.agentId,
        "agentName": req.agentName or req.agentId,
        "command": req.command,
        "output": (req.output or "")[:400],
        "exitCode": req.exitCode,
        "timestamp": time.strftime("%H:%M:%S")
    }
    telem = conv["telemetry"]
    telem.setdefault("terminalLogs", []).insert(0, entry)
    if len(telem["terminalLogs"]) > 25:
        telem["terminalLogs"] = telem["terminalLogs"][:25]
    sync_store.save_snapshot_only(cid, conv)
    schedule_persisted_state_save()
    await manager.broadcast_transient({
        "type": "TELEMETRY_UPDATE",
        "convId": cid,
        "terminalLog": entry,
    })
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
async def log_task(req: TaskLogRequest):
    cid = require_conversation_id(req.convId)
    check_and_reload_state(cid)
    conv = get_or_create_conversation(cid)
    
    tasks = conv["telemetry"].setdefault("backgroundTasks", [])
    found = False
    for t in tasks:
        if t.get("id") == req.id:
            t["status"] = req.status
            t["command"] = req.command
            t["title"] = req.title
            if req.pid: t["pid"] = req.pid
            if req.uptime: t["uptime"] = req.uptime
            found = True
            break
    if not found:
        entry = {
            "id": req.id,
            "agentId": req.agentId,
            "agentName": req.agentName or req.agentId,
            "title": req.title,
            "command": req.command,
            "pid": req.pid,
            "status": req.status,
            "isDaemon": req.isDaemon,
            "uptime": req.uptime or "Active",
            "startedAt": time.strftime("%H:%M:%S")
        }
        tasks.insert(0, entry)
    sync_store.save_snapshot_only(cid, conv)
    schedule_persisted_state_save()
    await manager.broadcast_transient({
        "type": "TELEMETRY_UPDATE",
        "convId": cid,
        "backgroundTask": tasks[0] if tasks else None,
    })
    return {"status": "ok", "tasks": tasks}


class ToolExecuteRequest(BaseModel):
    agentId: str
    command: str
    convId: Optional[str] = None


@app.post("/api/tools/execute")
async def execute_tool(req: ToolExecuteRequest):
    cid = require_conversation_id(req.convId)
    conv = get_or_create_conversation(cid)
    started = time.perf_counter()
    result = await asyncio.to_thread(execute_subagent_command, req.agentId, req.command)
    latency_ms = round((time.perf_counter() - started) * 1000)
    entry = {
        "id": str(uuid.uuid4()),
        "agentId": req.agentId,
        "agentName": next((a.get("name", req.agentId) for a in conv["agents"] if a.get("id") == req.agentId), req.agentId),
        "tool": req.command,
        "args": {},
        "output": result.get("output", ""),
        "status": "SUCCESS" if result.get("success") else "NOT_EXECUTED",
        "latencyMs": latency_ms,
        "timestamp": time.strftime("%H:%M:%S"),
    }
    calls = conv["telemetry"].setdefault("toolCalls", [])
    calls.insert(0, SyncEventStore.compact_tool_entry(entry))
    del calls[25:]
    sync_store.save_snapshot_only(cid, conv)
    await manager.broadcast_transient({"type": "TELEMETRY_UPDATE", "convId": cid, "telemetryEntry": calls[0]})
    return {
        "status": "executed" if result.get("success") else "not_executed",
        "convId": cid,
        "latencyMs": latency_ms,
        **result,
    }


# Mount Static Files (Frontend SPA Build & Fonts)
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8780, reload=False)
