#!/usr/bin/env python3
"""Minimal Antigravity hook bridge for Think Tank session context and tool metadata."""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
import urllib.error
import urllib.request
from typing import Any


API_URL = "http://127.0.0.1:8780/api/telemetry/host_tool"
ACTIVE_SESSION_API = "http://127.0.0.1:8780/api/host/active-session"
MAX_INPUT_BYTES = 2_000_000
HEAD_SCAN_BYTES = 16 * 1024
TAIL_SCAN_BYTES = 512 * 1024
MAX_CANDIDATE_TRANSCRIPTS = 12
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)

ROLE_ALIASES = {
    "main": "main_agent",
    "main-agent": "main_agent",
    "manager": "team-manager",
    "team_manager": "team-manager",
    "critic": "council-critic",
    "council_critic": "council-critic",
    "reviewer": "code-reviewer",
    "code_reviewer": "code-reviewer",
    "qa": "qa-reviewer",
    "qa_reviewer": "qa-reviewer",
    "designer": "ui-frontend-designer",
    "ui_frontend_designer": "ui-frontend-designer",
    "backend": "backend-auditor",
    "backend_auditor": "backend-auditor",
    "seo": "ecommerce_seo_operator",
    "ecommerce-seo-operator": "ecommerce_seo_operator",
    "wp": "wp_technical_operator",
    "wp-technical-operator": "wp_technical_operator",
}

TOOLS_DIR = str(Path(__file__).resolve().parent)
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

try:
    import bridge_transport
except ImportError:
    bridge_transport = None


def _resolve_session_file() -> Path:
    explicit = os.environ.get("THINKTANK_SESSION_FILE", "").strip()
    if explicit:
        return Path(explicit)
    base = os.environ.get("THINKTANK_HOME", "").strip()
    root = Path(base) if base else (Path.home() / ".gemini" / "config")
    return root / "active_antigravity_session.json"


def _resolve_links_file() -> Path:
    return _resolve_session_file().with_name("subagent_links.json")


def _resolve_brain_dir() -> Path:
    explicit = os.environ.get("THINKTANK_ANTIGRAVITY_BRAIN_DIR", "").strip()
    if explicit:
        return Path(explicit)
    return Path.home() / ".gemini" / "antigravity" / "brain"


def _valid_conv_id(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or len(value) > 200 or not re.fullmatch(r"[A-Za-z0-9-]+", value):
        return None
    return value


def _normalize_role_id(raw_id: str | None) -> str | None:
    if not raw_id or not isinstance(raw_id, str):
        return None
    clean = re.sub(r"^(?:(?:agent|tt)[_-])+", "", raw_id.strip().lower())
    if not clean:
        return None
    if clean in ROLE_ALIASES:
        return ROLE_ALIASES[clean]
    dashed = clean.replace("_", "-")
    if dashed in ROLE_ALIASES:
        return ROLE_ALIASES[dashed]
    if "_" in clean and clean not in {"main_agent", "ecommerce_seo_operator", "wp_technical_operator"}:
        return dashed
    return clean


def _read_json_dict(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
    except Exception:
        pass


def _extract_role_from_tail(tail_text: str, child_cid: str) -> tuple[bool, str | None, str | None]:
    pending: list[tuple[str, str]] = []
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
            uids = list(dict.fromkeys(conv_ids or UUID_RE.findall(content)))
            for uid in uids:
                tname, role = pending.pop(0) if pending else ("", "")
                if uid.lower() == child_cid.lower():
                    return True, _normalize_role_id(tname) or _normalize_role_id(role), role or None

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
    return True, _normalize_role_id(tname) or _normalize_role_id(role), role or None


def _discover_parent_from_brain(child_cid: str) -> tuple[str | None, str | None, str | None]:
    if not child_cid or "--run-" in child_cid:
        return None, None, None

    links_file = _resolve_links_file()
    links = _read_json_dict(links_file)
    cached = links.get(child_cid)
    if isinstance(cached, dict):
        cached_parent = _valid_conv_id(cached.get("parentConversationId"))
        if cached_parent and cached_parent != child_cid:
            return cached_parent, cached.get("roleId") or None, cached.get("roleTitle") or None

    brain_dir = _resolve_brain_dir()
    if not brain_dir.is_dir():
        return None, None, None

    child_transcript = brain_dir / child_cid / ".system_generated" / "logs" / "transcript.jsonl"
    if child_transcript.is_file():
        try:
            with child_transcript.open("rb") as fp:
                head = fp.read(HEAD_SCAN_BYTES).decode("utf-8", errors="ignore")
            if '"USER_EXPLICIT"' in head or '"USER_INPUT"' in head:
                return None, None, None
        except Exception:
            pass

    candidates: list[Path] = []
    seen_dirs: set[str] = {child_cid}
    sess_data = _read_json_dict(_resolve_session_file())
    sess_cid = _valid_conv_id(sess_data.get("conversationId"))
    if sess_cid and sess_cid not in seen_dirs and sess_cid not in links:
        sess_transcript = brain_dir / sess_cid / ".system_generated" / "logs" / "transcript.jsonl"
        if sess_transcript.is_file():
            candidates.append(sess_transcript)
            seen_dirs.add(sess_cid)

    recent_transcripts: list[tuple[float, Path]] = []
    try:
        for entry in brain_dir.iterdir():
            if not entry.is_dir() or entry.name in seen_dirs:
                continue
            tpath = entry / ".system_generated" / "logs" / "transcript.jsonl"
            if tpath.is_file():
                try:
                    recent_transcripts.append((tpath.stat().st_mtime, tpath))
                except OSError:
                    continue
    except OSError:
        return None, None, None

    recent_transcripts.sort(key=lambda item: item[0], reverse=True)
    for _, tpath in recent_transcripts[:MAX_CANDIDATE_TRANSCRIPTS]:
        candidates.append(tpath)

    for cand_path in candidates:
        parent_cid = _valid_conv_id(cand_path.parent.parent.parent.name)
        if not parent_cid or parent_cid == child_cid:
            continue
        try:
            size = cand_path.stat().st_size
            with cand_path.open("rb") as fp:
                fp.seek(max(0, size - TAIL_SCAN_BYTES))
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


def _conversation_id(payload: dict[str, Any]) -> str | None:
    return _valid_conv_id(payload.get("conversationId"))


def _parent_conversation_id(payload: dict[str, Any]) -> str | None:
    for key in ("parentConversationId", "parentConvId", "rootConversationId"):
        cid = _valid_conv_id(payload.get(key))
        if cid:
            return cid
    return None


def _resolve_parent_context(
    conversation_id: str | None, payload: dict[str, Any]
) -> tuple[str | None, str | None, str | None]:
    if not conversation_id:
        return None, None, None
    explicit_parent = _parent_conversation_id(payload)
    if explicit_parent and explicit_parent != conversation_id:
        role_id = _normalize_role_id(payload.get("roleId"))
        role_title = str(payload.get("roleTitle") or "").strip() or None
        return explicit_parent, role_id, role_title
    return _discover_parent_from_brain(conversation_id)


def _post_active_session(data: dict[str, Any], event_key: str) -> None:
    if bridge_transport is not None:
        try:
            bridge_transport.api_post_fast(
                "host/active-session",
                data,
                event_id=f"active-sess-{event_key}",
                timeout=0.25,
            )
            return
        except Exception:
            pass

    try:
        body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(
            ACTIVE_SESSION_API,
            data=body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=0.25) as resp:
            resp.read(64)
    except Exception:
        pass


def record_active_session(conversation_id: str, payload: dict[str, Any]) -> None:
    """Record the active Antigravity session without letting child subagents overwrite it."""
    if not conversation_id:
        return
    project_id = payload.get("projectId") or payload.get("workspace")
    parent_cid, role_id, role_title = _resolve_parent_context(conversation_id, payload)
    session_file = _resolve_session_file()

    if parent_cid:
        links = _read_json_dict(_resolve_links_file())
        existing = _read_json_dict(session_file)
        existing_cid = _valid_conv_id(existing.get("conversationId"))
        if not existing_cid or existing_cid == conversation_id or existing_cid in links:
            _write_json_atomic(
                session_file,
                {
                    "conversationId": parent_cid,
                    "projectId": project_id or existing.get("projectId"),
                    "timestamp": time.time(),
                },
            )
        _post_active_session(
            {
                "conversationId": conversation_id,
                "parentConversationId": parent_cid,
                "roleId": role_id,
                "roleTitle": role_title,
                "projectId": project_id,
                "timestamp": time.time(),
            },
            f"{conversation_id}-{parent_cid}",
        )
        return

    data = {
        "conversationId": conversation_id,
        "projectId": project_id,
        "timestamp": time.time(),
    }
    _write_json_atomic(session_file, data)
    _post_active_session(data, conversation_id)


def build_tool_event(payload: dict[str, Any]) -> dict[str, Any] | None:
    conversation_id = _conversation_id(payload)
    tool_call = payload.get("toolCall")
    if not conversation_id or not isinstance(tool_call, dict):
        return None
    raw_name = tool_call.get("name")
    if not isinstance(raw_name, str) or not raw_name.strip():
        return None
    name = re.sub(r"[^A-Za-z0-9_.:/ -]", "", raw_name.strip())[:120]
    if not name:
        return None
    step = payload.get("stepIdx")
    if not isinstance(step, int) or isinstance(step, bool) or step < 0:
        return None
    error = payload.get("error")
    tool_args = tool_call.get("args") or payload.get("args")
    tool_output = payload.get("output") or payload.get("result")
    agent_id = payload.get("agentId") or payload.get("senderCode") or "antigravity"
    agent_name = payload.get("agentName") or payload.get("senderName") or "Antigravity"
    event: dict[str, Any] = {
        "convId": conversation_id,
        "id": f"antigravity-tool-{conversation_id}-{step}",
        "tool": name,
        "status": "ERROR" if isinstance(error, str) and error else "SUCCESS",
        "stepIdx": step,
        "args": tool_args if isinstance(tool_args, dict) else {},
        "output": str(tool_output)[:1000] if tool_output else "",
        "error": str(error)[:500] if error else "",
        "agentId": agent_id,
        "agentName": agent_name,
    }
    parent_cid, role_id, role_title = _resolve_parent_context(conversation_id, payload)
    if parent_cid:
        event["parentConversationId"] = parent_cid
        if role_id:
            event["roleId"] = role_id
        if role_title:
            event["roleTitle"] = role_title
    return event


def build_response(event_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    if event_name == "pre-invocation":
        conversation_id = _conversation_id(payload)
        if not conversation_id:
            return {}
        record_active_session(conversation_id, payload)
        parent_cid, _, _ = _resolve_parent_context(conversation_id, payload)
        if parent_cid:
            message = (
                f"Antigravity subagent session ID: {conversation_id} (parent conversation ID: {parent_cid}). "
                f"When using the Think Tank bridge in this session, include --conv-id {parent_cid} "
                f"--origin subagent --subagent-conv-id {conversation_id}."
            )
        else:
            message = (
                f"Antigravity conversation ID for this session: {conversation_id}. "
                "When using the Think Tank bridge in this session, include this exact value with --conv-id on every command."
            )
        return {"injectSteps": [{"ephemeralMessage": message}]}
    return {}


def send_tool_event(event: dict[str, Any]) -> None:
    if bridge_transport is not None:
        try:
            bridge_transport.api_post_fast(
                "telemetry/host_tool",
                event,
                event_id=event["id"],
                timeout=0.35,
            )
            return
        except Exception:
            # Keep the direct path as a last-resort compatibility fallback.
            pass

    body = json.dumps(event, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        API_URL,
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-ThinkTank-Event-Id": event["id"],
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=0.4) as response:
            response.read(256)
    except (OSError, urllib.error.URLError, TimeoutError):
        return


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    event_name = args[0] if args else ""
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            payload: dict[str, Any] = {}
        else:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        payload = {}

    if event_name == "post-tool-use":
        conversation_id = _conversation_id(payload)
        if conversation_id:
            record_active_session(conversation_id, payload)
        event = build_tool_event(payload)
        if event:
            send_tool_event(event)
        response = {}
    else:
        response = build_response(event_name, payload)
    sys.stdout.write(json.dumps(response, ensure_ascii=False))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
