"""Pure Case Ledger domain logic, 5-stage gates, WBS file locks, and interaction graph."""

from __future__ import annotations

import copy
import hashlib
import re
import time
import uuid
from typing import Any, Optional

try:
    from .catalog import (
        CANONICAL_ROLES,
        OPERATOR_ALIASES,
        extract_mentions_and_citations,
        find_role_entry,
        infer_request_type,
        load_role_catalog,
        normalize_agent_id,
        resolve_role_title,
    )
    from .governance import (
        DEFAULT_ROLE_CAPS,
        evaluate_review,
        normalize_role_caps,
        normalize_round_limit,
        role_bucket,
        role_usage,
    )
    from .session_resolver import save_subagent_link
    from .store import SyncEventStore
except ImportError:
    from catalog import (
        CANONICAL_ROLES,
        OPERATOR_ALIASES,
        extract_mentions_and_citations,
        find_role_entry,
        infer_request_type,
        load_role_catalog,
        normalize_agent_id,
        resolve_role_title,
    )
    from governance import (
        DEFAULT_ROLE_CAPS,
        evaluate_review,
        normalize_role_caps,
        normalize_round_limit,
        role_bucket,
        role_usage,
    )
    from session_resolver import save_subagent_link
    from store import SyncEventStore


class CaseGateError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = int(status_code)
        self.detail = str(detail)


CANONICAL_FINDING_STATES: dict[str, str] = {
    "open": "Open", "fixing": "Fixing", "inreview": "InReview", "in_review": "InReview",
    "testing": "Testing", "verified": "Verified", "closed": "Closed",
    "wontfix": "WontFix", "wont_fix": "WontFix",
}

DEFAULT_THINK_TANK_STATE: dict[str, Any] = {
    "status": "DISCONNECTED", "project": "", "phase": "در انتظار داده زنده",
    "round": 0, "maxRounds": 50, "roleCaps": dict(DEFAULT_ROLE_CAPS),
    "roundStatus": "UNKNOWN", "progress": 0, "pipelineStage": 1,
    "stageEpochSeq": 0, "isClosed": False, "hasSession": False,
    "runIndex": 1, "directive": "", "triageDecision": None, "closureReceipt": None,
}


def now_ms() -> int:
    return int(time.time() * 1000)


def now_hms() -> str:
    return time.strftime("%H:%M:%S")


def create_empty_conversation(cid: str) -> dict[str, Any]:
    ts_ms = now_ms()
    conv: dict[str, Any] = {
        "id": cid,
        "createdAtMs": ts_ms,
        "updatedAtMs": ts_ms,
        "updated_at": ts_ms / 1000.0,
        "thinkTank": dict(DEFAULT_THINK_TANK_STATE),
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
    conv["thinkTank"]["roleCaps"] = dict(DEFAULT_ROLE_CAPS)
    if "--run-" in cid:
        conv["parentConvId"] = cid.split("--run-")[0]
    return conv


def get_conv_sort_ts(c: dict[str, Any]) -> float:
    if not isinstance(c, dict):
        return 0.0
    for key in ("updatedAtMs", "updated_at", "updatedAt", "createdAtMs"):
        val = c.get(key)
        if isinstance(val, (int, float)) and not isinstance(val, bool) and val > 0:
            return float(val) / 1000.0 if float(val) > 1e11 else float(val)
        if isinstance(val, str) and re.fullmatch(r"\d+(?:\.\d+)?", val.strip()):
            fval = float(val.strip())
            return fval / 1000.0 if fval > 1e11 else fval
    best_ms = 0.0
    for col in ("messages", "interactions", "subtasks", "findings"):
        items = c.get(col)
        if isinstance(items, list) and items:
            for item in reversed(items[-5:]):
                if isinstance(item, dict):
                    ms = item.get("updatedAtMs") or item.get("createdAtMs")
                    if isinstance(ms, (int, float)) and ms > best_ms:
                        best_ms = float(ms)
    return best_ms / 1000.0 if best_ms > 1e11 else best_ms


_GENERIC_HOST_AGENTS = frozenset({"antigravity", "main_agent"})


def has_thinktank_activity(conv: Optional[dict[str, Any]]) -> bool:
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
        if isinstance(ag, dict):
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


def is_unclosed_thinktank(conv: Optional[dict[str, Any]]) -> bool:
    return bool(conv and has_thinktank_activity(conv) and not (conv.get("thinkTank") or {}).get("isClosed"))


def is_phantom_child_conv(conv: Any) -> bool:
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


def is_meaningful_conversation(cid: str, conv: dict[str, Any], current_cid: str, subagent_map: Optional[dict[str, Any]] = None) -> bool:
    if cid == current_cid:
        return True
    if subagent_map and cid in subagent_map:
        return False
    tt = conv.get("thinkTank") or {}
    prop = conv.get("proposal")
    has_prop = bool(prop) and (not isinstance(prop, dict) or prop.get("status") != "NONE")
    return bool(
        (tt.get("project") or "").strip()
        or (tt.get("directive") or "").strip()
        or conv.get("messages")
        or conv.get("subtasks")
        or has_prop
        or conv.get("findings")
        or tt.get("triageDecision")
        or int(tt.get("runIndex") or 1) > 1
        or "--run-" in cid
    )


def compute_pipeline_state(conv: dict[str, Any]) -> dict[str, Any]:
    tt = conv.get("thinkTank") or {}
    status = str(tt.get("status") or "DISCONNECTED").upper().strip()
    if status in {"COMPLETED", "DONE", "CLOSED"} or bool(tt.get("isClosed")):
        return {"pipelineStage": 5, "isClosed": True}
    epoch_seq = int(tt.get("stageEpochSeq") or 0)
    interactions = [ev for ev in (conv.get("interactions") or []) if isinstance(ev, dict) and int(ev.get("seq") or 0) > epoch_seq]
    msgs = [m for m in (conv.get("messages") or []) if isinstance(m, dict) and int(m.get("seq") or 0) > epoch_seq]
    events = interactions + msgs
    latest_qa = max((int(e.get("seq") or 0) for e in events if str(e.get("action") or e.get("actionType") or "").upper() in {"QA_DISPATCH", "REVIEW_QUERY", "QA_REPORT"}), default=0)
    latest_fix = max((int(e.get("seq") or 0) for e in events if str(e.get("action") or e.get("actionType") or "").upper() == "WORKER_FIX"), default=0)
    latest_defect = max((int(e.get("seq") or 0) for e in events if str(e.get("action") or e.get("actionType") or "").upper() in {"RETURN_DEFECT", "INTERROGATE", "CRITIQUE"}), default=0)
    has_open_defect = any(str(e.get("action") or "").upper() in {"RETURN_DEFECT", "INTERROGATE"} and not e.get("resolved") for e in interactions)
    if latest_qa > latest_defect and (latest_qa >= latest_fix or not has_open_defect):
        stage = 4
    elif latest_fix > 0 and latest_fix >= latest_defect:
        stage = 3
    elif latest_defect > 0 or has_open_defect:
        stage = 2
    else:
        stage = 1
    return {"pipelineStage": stage, "isClosed": False}


def sync_pipeline_fields(conv: dict[str, Any]) -> dict[str, Any]:
    state = compute_pipeline_state(conv)
    has_sess = has_thinktank_activity(conv)
    tt = conv.setdefault("thinkTank", dict(DEFAULT_THINK_TANK_STATE))
    tt["pipelineStage"] = state["pipelineStage"]
    tt["isClosed"] = state["isClosed"]
    tt["hasSession"] = has_sess
    conv["hasSession"] = has_sess
    conv["isClosed"] = state["isClosed"]
    conv["pipelineStage"] = state["pipelineStage"]
    return {**state, "hasSession": has_sess}


def normalize_origin(msg: dict[str, Any], conv: dict[str, Any]) -> str:
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
    sender_norm = normalize_agent_id(msg.get("senderRole") or msg.get("senderCode"))
    if msg.get("isOperator") or sender_norm in OPERATOR_ALIASES:
        return "user"
    if has_child_sub:
        return "subagent"
    return "main-proxy"


def require_case_open(conv: dict[str, Any]) -> None:
    if bool((conv.get("thinkTank") or {}).get("isClosed")):
        raise CaseGateError(409, "Case is closed and read-only. Reopen the case or start a new case first.")


def enforce_role_cap(conv: dict[str, Any], sender_role: Optional[str], is_review: bool = False, review_id: Optional[str] = None) -> None:
    bucket = role_bucket(sender_role)
    if not bucket:
        return
    if is_review and bucket in {"main", "manager"} and isinstance(review_id, str) and bool(review_id.strip()):
        return
    caps = normalize_role_caps((conv.get("thinkTank") or {}).get("roleCaps"))
    usage = role_usage(conv.get("messages") or [])
    if usage.get(bucket, 0) >= caps.get(bucket, 50):
        raise CaseGateError(429, f"The {bucket} message cap ({caps[bucket]}) has been reached for this session.")


def compute_origin_counts(conv: dict[str, Any]) -> dict[str, int]:
    counts = {"subagent": 0, "main-proxy": 0, "user": 0}
    for m in conv.get("messages") or []:
        if isinstance(m, dict):
            origin = normalize_origin(m, conv)
            counts[origin] = counts.get(origin, 0) + 1
    return counts


def rebuild_file_locks(conv: dict[str, Any]) -> list[dict[str, Any]]:
    locks: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for st in conv.get("subtasks") or []:
        if not isinstance(st, dict) or str(st.get("status") or "").upper() in {"COMPLETED", "DONE"}:
            continue
        owner = normalize_agent_id(st.get("assignee", "")) or str(st.get("assignee") or "").strip()
        work_item_id = st.get("id")
        for raw_path in st.get("lockedFiles") or []:
            path = str(raw_path or "").strip().replace("\\", "/")
            if path and (path.lower(), owner) not in seen:
                seen.add((path.lower(), owner))
                locks.append({"path": path, "owner": owner, "workItemId": work_item_id})
    conv["fileLocks"] = locks
    return locks


def find_finding(conv: dict[str, Any], finding_id: Optional[str]) -> Optional[dict[str, Any]]:
    target = str(finding_id or "").strip().upper()
    if not target:
        return None
    for f in conv.get("findings") or []:
        if isinstance(f, dict) and str(f.get("id") or "").strip().upper() == target:
            return f
    return None


def next_finding_id(conv: dict[str, Any]) -> str:
    max_num = 0
    for f in conv.get("findings") or []:
        if isinstance(f, dict):
            m = re.match(r"^F-(\d+)$", str(f.get("id") or "").strip().upper())
            if m:
                max_num = max(max_num, int(m.group(1)))
    return f"F-{max_num + 1:02d}"


def upsert_agent_state(
    conv: dict[str, Any],
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
    if not clean_id or clean_id in OPERATOR_ALIASES:
        return False

    ts_ms = now_ms()
    agents = conv.setdefault("agents", [])
    cat_entry = find_role_entry(clean_id)
    matched = next(
        (ag for ag in agents if normalize_agent_id(ag.get("id", "")) == clean_id or normalize_agent_id(ag.get("code", "")) == clean_id),
        None,
    )
    if matched:
        if cat_entry:
            for meta_key in ("tier", "tierLabel", "monogram", "frameShape", "reportsTo", "canInterrogate", "canPeerSync"):
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
            if clean_cw and clean_cw != clean_id and clean_cw not in OPERATOR_ALIASES:
                cwith = matched.setdefault("collaboratingWith", [])
                if clean_cw not in cwith:
                    cwith.append(clean_cw)
        if increment_turn:
            matched["turnsUsed"] = int(matched.get("turnsUsed") or 0) + 1
        if subagent_conv_id and isinstance(subagent_conv_id, str) and subagent_conv_id.strip():
            matched["subagentConvId"] = subagent_conv_id.strip()
        if verified_subagent:
            matched["verifiedSubagent"] = True
        matched["updatedAtMs"] = ts_ms
        return True

    title = resolve_role_title(clean_id, name)
    spec = role or (cat_entry.get("specialty") if cat_entry else None) or "ساب ایجنت هوشمند"
    cwith_list = []
    if collaborating_with:
        clean_cw = normalize_agent_id(collaborating_with)
        if clean_cw and clean_cw != clean_id and clean_cw not in OPERATOR_ALIASES:
            cwith_list.append(clean_cw)
    profile: dict[str, Any] = {
        "id": clean_id, "name": title, "role": spec,
        "icon": (cat_entry.get("icon") if cat_entry else None) or "agent",
        "monogram": (cat_entry.get("monogram") if cat_entry else None) or clean_id[:2].upper(),
        "frameShape": (cat_entry.get("frameShape") if cat_entry else None) or "circle",
        "status": status,
        "tier": (cat_entry.get("tier") if cat_entry else None) or "worker",
        "tierLabel": (cat_entry.get("tierLabel") if cat_entry else None) or "متخصص اجرایی",
        "reportsTo": cat_entry.get("reportsTo") if cat_entry else None,
        "canInterrogate": bool(cat_entry.get("canInterrogate", False)) if cat_entry else False,
        "canPeerSync": bool(cat_entry.get("canPeerSync", True)) if cat_entry else True,
        "task": task or f"فعالیت در نشست جاری ({title})",
        "currentTask": task or f"فعالیت در نشست جاری ({title})",
        "tool": tool.strip() if tool else None, "activeTool": tool.strip() if tool else None,
        "thought": thought.strip() if thought else None,
        "turnsUsed": 1 if increment_turn else None,
        "collaboratingWith": cwith_list,
        "skills": cat_entry.get("skills", ["task-execution", "live-collaboration"]) if cat_entry else ["task-execution", "live-collaboration"],
        "updatedAtMs": ts_ms,
    }
    if code:
        profile["code"] = code
    if subagent_conv_id and isinstance(subagent_conv_id, str) and subagent_conv_id.strip():
        profile["subagentConvId"] = subagent_conv_id.strip()
    if verified_subagent:
        profile["verifiedSubagent"] = True
    agents.append(profile)
    return True


def normalize_conversation(cid: str, conv: dict[str, Any]) -> bool:
    changed = False
    tt = conv.setdefault("thinkTank", dict(DEFAULT_THINK_TANK_STATE))
    norm_caps = normalize_role_caps(tt.get("roleCaps"))
    if tt.get("roleCaps") != norm_caps:
        tt["roleCaps"] = norm_caps
        changed = True
    norm_rounds = normalize_round_limit(tt.get("maxRounds", 50))
    if tt.get("maxRounds") != norm_rounds:
        tt["maxRounds"] = norm_rounds
        changed = True
    for k, default_v in (("review", None), ("proposal", None), ("messages", []), ("interactions", []), ("collaborations", []), ("subtasks", []), ("findings", []), ("fileLocks", [])):
        if k not in conv or (isinstance(default_v, list) and not isinstance(conv.get(k), list)):
            conv[k] = list(default_v) if isinstance(default_v, list) else default_v
            changed = True
    conv.setdefault("telemetry", {"toolCalls": [], "terminalLogs": [], "backgroundTasks": []})
    for tk in ("triageDecision", "closureReceipt"):
        if tk not in tt:
            tt[tk] = None
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
        rebuild_file_locks(conv)
    for idx_m, m in enumerate(conv["messages"], start=1):
        if isinstance(m, dict) and not m.get("seq"):
            m["seq"] = idx_m
            changed = True
    prev_stage, prev_closed = tt.get("pipelineStage"), tt.get("isClosed")
    pstate = sync_pipeline_fields(conv)
    if pstate["pipelineStage"] != prev_stage or pstate["isClosed"] != prev_closed:
        changed = True
    return changed


def append_message(
    conv: dict[str, Any],
    msg: dict[str, Any],
    *,
    action_type: Optional[str] = None,
    severity: Optional[str] = None,
    label: Optional[str] = None,
) -> dict[str, Any]:
    msgs = conv.setdefault("messages", [])
    next_seq = max((int(m.get("seq") or 0) for m in msgs if isinstance(m, dict)), default=0) + 1
    msg["seq"] = int(msg.get("seq") or next_seq)
    ts_ms = int(msg.get("createdAtMs") or now_ms())
    msg["createdAtMs"] = ts_ms
    if not msg.get("timestamp"):
        msg["timestamp"] = now_hms()
    msg["origin"] = normalize_origin(msg, conv)

    content = str(msg.get("content") or "")
    mentions, citations = extract_mentions_and_citations(content)
    explicit_recip = normalize_agent_id(msg.get("recipientRole") or msg.get("recipientCode") or msg.get("recipient"))
    if explicit_recip and explicit_recip not in OPERATOR_ALIASES and explicit_recip not in {"council", "all"} and explicit_recip not in mentions:
        mentions.insert(0, explicit_recip)
    msg["mentions"] = mentions
    msg["citations"] = citations

    if action_type:
        msg["actionType"] = action_type
    elif not msg.get("actionType"):
        msg["actionType"] = "CRITIQUE" if msg.get("critique") else ("QUESTION" if msg.get("question") else "MESSAGE")
    if severity:
        msg["severity"] = severity

    action_upper = str(msg.get("actionType") or "MESSAGE").upper()
    msg["requestType"] = infer_request_type(action_upper, msg.get("requestType"))
    conv_closed = str((conv.get("thinkTank") or {}).get("status") or "").upper() in {"COMPLETED", "DONE", "CLOSED"} or bool((conv.get("thinkTank") or {}).get("isClosed"))
    msg["resolved"] = bool(msg.get("resolved", False) or conv_closed)

    raw_chan = str(msg.get("channel") or "MAIN").upper().strip()
    msg["channel"] = "MAIN" if raw_chan == "ALL" else raw_chan
    msgs.append(msg)

    raw_sender = str(msg.get("senderRole") or msg.get("senderCode") or "").strip()
    sender_norm = normalize_agent_id(raw_sender)
    is_operator = bool(msg.get("isOperator") or raw_sender.lower() in OPERATOR_ALIASES or sender_norm in OPERATOR_ALIASES)
    sender_id = "user" if is_operator else (sender_norm or "main_agent")
    interactions = conv.setdefault("interactions", [])
    msg_finding_id = str(msg.get("findingId") or "").strip().upper() or None

    if action_upper == "WORKER_FIX" and sender_id and not is_operator:
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
                if str(prev_m.get("actionType") or "").upper() in {"RETURN_DEFECT", "INTERROGATE", "CRITIQUE"}:
                    prev_to = normalize_agent_id(prev_m.get("recipientRole") or prev_m.get("recipientCode") or prev_m.get("recipient"))
                    if prev_to == sender_id or sender_id in (prev_m.get("mentions") or []):
                        prev_m["resolved"] = True
    elif action_upper == "QA_REPORT" and str(msg.get("result") or "").upper() == "PASS":
        qa_clear = {"QA_DISPATCH", "REVIEW_QUERY", "WORKER_FIX", "RETURN_DEFECT", "INTERROGATE", "CRITIQUE"}
        for ev in interactions:
            if isinstance(ev, dict) and str(ev.get("action") or "").upper() in qa_clear:
                if msg_finding_id and ev.get("findingId") and str(ev.get("findingId")).upper() != msg_finding_id:
                    continue
                ev["resolved"] = True
        for prev_m in msgs:
            if isinstance(prev_m, dict) and str(prev_m.get("actionType") or "").upper() in qa_clear:
                if msg_finding_id and prev_m.get("findingId") and str(prev_m.get("findingId")).upper() != msg_finding_id:
                    continue
                prev_m["resolved"] = True
        msg["resolved"] = True

    targets = [t for t in mentions if t and t != sender_id and t not in OPERATOR_ALIASES and t not in {"council", "all"}]
    if not targets:
        if is_operator:
            targets = ["main_agent"]
        elif msg["channel"] == "COUNCIL":
            targets = ["team-manager" if sender_id != "team-manager" else "main_agent"]
        elif msg["channel"] == "QA":
            targets = ["code-reviewer" if sender_id != "code-reviewer" else "team-manager"]
        elif msg["channel"] in {"SYNC", "SUBAGENTS", "INTERROGATION"}:
            targets = ["team-manager" if sender_id != "team-manager" else "main_agent"]
        else:
            targets = ["team-manager" if sender_id != "team-manager" else "main_agent"]
    if not msg.get("recipientRole") and targets:
        msg["recipientRole"] = targets[0]
        msg.setdefault("recipientCode", targets[0].upper())
        msg.setdefault("recipientName", resolve_role_title(targets[0]))
    for target_id in targets:
        if not target_id or target_id == sender_id:
            continue
        ev_row: dict[str, Any] = {
            "seq": msg["seq"], "from": sender_id, "to": target_id,
            "action": action_upper, "requestType": msg["requestType"],
            "channel": msg["channel"], "severity": msg.get("severity"),
            "label": label or "", "summary": content[:180],
            "timestamp": msg["timestamp"], "createdAtMs": ts_ms,
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
    sync_pipeline_fields(conv)
    return msg


def build_interaction_graph(conv: dict[str, Any]) -> dict[str, Any]:
    interactions = conv.get("interactions") or []
    edge_map: dict[str, dict[str, Any]] = {}
    total_events = 0
    for ev in interactions:
        if not isinstance(ev, dict):
            continue
        raw_from = str(ev.get("from") or "").strip()
        src = "user" if raw_from.lower() in OPERATOR_ALIASES else normalize_agent_id(raw_from)
        dst = normalize_agent_id(ev.get("to"))
        kind = str(ev.get("action") or "MESSAGE").upper()
        if not src or not dst or src == dst or src in {"user", "all"} or dst in {"user", "all"}:
            continue
        total_events += 1
        key = f"{src}->{dst}"
        req_type = ev.get("requestType") or infer_request_type(kind)
        item = edge_map.setdefault(key, {
            "key": key, "from": src, "to": dst, "action": kind, "requestType": req_type,
            "channel": ev.get("channel", "SYNC"), "count": 0, "openCount": 0,
            "resolved": True, "lastSeq": 0, "seqs": [], "label": ev.get("label") or "",
        })
        item["count"] += 1
        if not ev.get("resolved"):
            item["openCount"] += 1
            item["resolved"] = False
        seq_num = int(ev.get("seq") or 0)
        if seq_num >= item["lastSeq"]:
            item["lastSeq"] = seq_num
            item["action"] = kind
            item["requestType"] = req_type
            item["channel"] = ev.get("channel") or item["channel"]
            if ev.get("label"):
                item["label"] = ev["label"]
        if seq_num and seq_num not in item["seqs"]:
            item["seqs"].append(seq_num)
    return {
        "edges": list(edge_map.values()),
        "totalEvents": total_events,
        "maxSeq": max((int(m.get("seq") or 0) for m in conv.get("messages", []) if isinstance(m, dict)), default=0),
    }


def build_closure_receipt(conv: dict[str, Any], force_reason: Optional[str]) -> dict[str, Any]:
    tt = conv.get("thinkTank") or {}
    subtasks = conv.get("subtasks") or []
    findings = conv.get("findings") or []
    msgs = conv.get("messages") or []
    qa_exit_codes: list[Optional[int]] = []
    seen_qa_seqs: set[int] = set()
    for f in findings:
        if isinstance(f, dict):
            for ev in f.get("evidence") or []:
                if isinstance(ev, dict):
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
            cu = str(m.get("content") or "").upper()
            qa_exit_codes.append(0 if (res_upper == "PASS" or (not res_upper and "PASS" in cu and "FAIL" not in cu)) else 1)

    return {
        "closedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "closedAtMs": now_ms(),
        "project": tt.get("project") or "",
        "totalEvents": len(msgs),
        "subtasksTotal": len(subtasks),
        "subtasksCompleted": sum(1 for s in subtasks if isinstance(s, dict) and str(s.get("status") or "").upper() in {"COMPLETED", "DONE"}),
        "findingsVerified": sum(1 for f in findings if isinstance(f, dict) and str(f.get("state") or "").lower() in {"verified", "closed"}),
        "findingsOpen": sum(1 for f in findings if isinstance(f, dict) and str(f.get("state") or "").lower() in {"open", "fixing", "inreview", "testing"}),
        "findingsWontFix": sum(1 for f in findings if isinstance(f, dict) and str(f.get("state") or "").lower() == "wontfix"),
        "qaRunsCount": len(qa_exit_codes),
        "qaAllExitZero": bool(qa_exit_codes) and all(code == 0 for code in qa_exit_codes),
        "originCounts": compute_origin_counts(conv),
        "forceCloseReason": (force_reason or "").strip() or None,
    }


def archive_conversation_run(
    base_cid: str,
    conv: dict[str, Any],
    conversations_store: dict[str, dict[str, Any]],
    store: Any = None,
) -> str:
    base_cid = base_cid.split("--run-")[0]
    tt = conv.setdefault("thinkTank", dict(DEFAULT_THINK_TANK_STATE))
    run_idx = int(tt.get("runIndex") or 1)
    while f"{base_cid}--run-{run_idx}" in conversations_store:
        run_idx += 1
    archived_id = f"{base_cid}--run-{run_idx}"
    archived_conv = copy.deepcopy(conv)
    archived_conv["id"] = archived_id
    archived_conv["parentConvId"] = base_cid
    archived_conv["isArchivedRun"] = True
    archived_conv["isClosed"] = True
    archived_tt = archived_conv.setdefault("thinkTank", dict(DEFAULT_THINK_TANK_STATE))
    archived_tt["runIndex"] = run_idx
    archived_tt["isClosed"] = True
    if str(archived_tt.get("status") or "").upper() not in {"COMPLETED", "DONE", "CLOSED"}:
        archived_tt["status"] = "COMPLETED"
    conversations_store[archived_id] = archived_conv
    if store is not None:
        store.commit(
            conversation_id=archived_id,
            event_id=f"run-archived-{archived_id}-{uuid.uuid4().hex[:8]}",
            event_type="RUN_ARCHIVED",
            payload={"convId": archived_id, "parentConvId": base_cid, "runIndex": run_idx},
            snapshot=archived_conv,
            source="archive",
        )
    ts_ms = now_ms()
    conv["id"] = base_cid
    conv["parentConvId"] = base_cid
    conv["updatedAtMs"] = ts_ms
    conv["updated_at"] = ts_ms / 1000.0
    for k in ("findings", "subtasks", "messages", "collaborations", "interactions", "fileLocks", "agents"):
        conv[k] = []
    conv["proposal"] = None
    conv["review"] = None
    conv["telemetry"] = {"toolCalls": [], "terminalLogs": [], "backgroundTasks": []}
    tt.update({
        "isClosed": False, "closureReceipt": None, "status": "ACTIVE",
        "round": 1, "progress": 5, "stageEpochSeq": 0, "pipelineStage": 1,
        "roundStatus": "ACTIVE", "triageDecision": None, "project": "",
        "directive": "", "phase": "در حال بررسی و اجرای پرونده جدید", "runIndex": run_idx + 1,
    })
    sync_pipeline_fields(conv)
    if store is not None and hasattr(store, "reset_conversation_events"):
        store.reset_conversation_events(base_cid, conv)
    return archived_id


def apply_task_update(
    cid: str,
    conv: dict[str, Any],
    req: dict[str, Any],
    conversations_store: dict[str, dict[str, Any]],
    store: Any = None,
) -> tuple[Optional[str], list[str]]:
    tt = conv.setdefault("thinkTank", dict(DEFAULT_THINK_TANK_STATE))
    is_reopening = bool(req.get("reopen")) and not req.get("resetCase") and not req.get("newRun")
    archived_run_id: Optional[str] = None
    ts_ms = now_ms()
    hms = now_hms()

    def _norm_triage(td: Any) -> Optional[dict[str, Any]]:
        if not isinstance(td, dict):
            return None
        out = dict(td)
        out.setdefault("timestamp", hms)
        out.setdefault("createdAtMs", ts_ms)
        return out

    if req.get("resetCase"):
        for k in ("findings", "subtasks", "messages", "collaborations", "interactions", "fileLocks", "agents"):
            conv[k] = []
        conv["proposal"] = None
        conv["review"] = None
        conv["telemetry"] = {"toolCalls": [], "terminalLogs": [], "backgroundTasks": []}
        tt.update({
            "isClosed": False, "closureReceipt": None, "status": "ACTIVE",
            "round": 1, "progress": 5, "stageEpochSeq": 0, "pipelineStage": 1,
            "roundStatus": "ACTIVE", "triageDecision": _norm_triage(req.get("triageDecision")),
            "project": req.get("project") or "", "directive": req.get("directive") or "",
            "phase": req.get("phase") or "در حال بررسی و اجرای پرونده جدید",
            "runIndex": int(tt.get("runIndex") or 1),
        })
        if req.get("maxRounds") is not None:
            tt["maxRounds"] = normalize_round_limit(req["maxRounds"])
        if req.get("roleCaps") is not None:
            tt["roleCaps"] = normalize_role_caps(req["roleCaps"])
        sync_pipeline_fields(conv)
        return None, ["thinkTank", "agents", "subtasks", "fileLocks", "findings", "messages", "interactions", "graph", "proposal", "review", "telemetry", "conversationsList"]

    if is_reopening:
        tt["isClosed"] = False
        tt["closureReceipt"] = None
        tt["status"] = "ACTIVE"
        if tt.get("roundStatus") == "COMPLETE":
            tt["roundStatus"] = "ACTIVE"
        for f in conv.get("findings") or []:
            if isinstance(f, dict) and str(f.get("state") or "").strip().lower() == "closed":
                f["state"] = "Verified"
                f["updatedAt"] = hms
                f["updatedAtMs"] = ts_ms
        for ag in conv.get("agents") or []:
            if isinstance(ag, dict) and str(ag.get("status") or "").upper() == "COMPLETED":
                ag["status"] = "IDLE"
                ag["activeTool"] = None
                ag["tool"] = None
                ag["updatedAtMs"] = ts_ms
        conv.pop("_telemetryOnly", None)
        for fk in ("project", "directive", "phase"):
            if req.get(fk):
                tt[fk] = req[fk]
        if req.get("progress") is not None and int(req["progress"]) < 100:
            tt["progress"] = int(req["progress"])
        elif int(tt.get("progress") or 0) >= 100:
            tt["progress"] = 90
        if req.get("round") is not None:
            tt["round"] = int(req["round"])
        if req.get("maxRounds") is not None:
            tt["maxRounds"] = normalize_round_limit(req["maxRounds"])
        if req.get("roleCaps") is not None:
            tt["roleCaps"] = normalize_role_caps(req["roleCaps"])
        if req.get("triageDecision") is not None:
            tt["triageDecision"] = _norm_triage(req["triageDecision"])
        sync_pipeline_fields(conv)
        return None, ["thinkTank", "findings", "agents", "conversationsList"]

    was_closed = bool(tt.get("isClosed")) or str(tt.get("status") or "").upper() in {"COMPLETED", "DONE", "CLOSED"}
    req_status_upper = str(req.get("status") or "").upper()
    req_prog = req.get("progress")
    req_should_close = req_status_upper in {"COMPLETED", "DONE", "CLOSED"} or (req_prog is not None and int(req_prog) >= 100 and req_status_upper != "HALTED")
    has_existing_work = bool(conv.get("subtasks") or conv.get("findings") or conv.get("messages") or conv.get("proposal"))
    should_start_new_run = has_existing_work and not req_should_close and (
        bool(req.get("newRun"))
        or (was_closed and (req.get("triageDecision") is not None or bool(req.get("project")) or bool(req.get("directive")) or req_status_upper == "ACTIVE"))
    )
    if should_start_new_run:
        archived_run_id = archive_conversation_run(cid, conv, conversations_store, store=store)
        was_closed = False

    if req.get("status") == "COMPLETED":
        review = conv.get("review") or {}
        if review and review.get("status") == "REVIEW_REQUESTED" and (review.get("confidence", 0) < 95 or review.get("decision") != "complete"):
            raise CaseGateError(409, "Completion requires a manager and main-agent review with an evidence score of at least 95.")
    if req.get("round") is not None and int(req["round"]) > normalize_round_limit(tt.get("maxRounds", 50)):
        raise CaseGateError(409, "The round limit has been reached. Extend the limit before starting another round.")

    target_status_upper = str(req.get("status") or tt.get("status") or "").upper()
    target_should_close = target_status_upper in {"COMPLETED", "DONE", "CLOSED"} or (req_prog is not None and int(req_prog) >= 100 and target_status_upper != "HALTED")
    if target_should_close:
        if req.get("forceClose") and not str(req.get("forceReason") or "").strip():
            raise CaseGateError(409, "forceClose requires a non-empty forceReason.")
        unresolved = [f for f in (conv.get("findings") or []) if isinstance(f, dict) and str(f.get("state") or "").lower() in {"open", "fixing", "inreview", "testing"}]
        if unresolved and not req.get("forceClose"):
            ids = ", ".join(str(f.get("id") or "?") for f in unresolved[:5])
            raise CaseGateError(409, f"Cannot close session while {len(unresolved)} unresolved finding(s) remain ({ids}). Resolve them or pass forceClose with forceReason.")

    conv.pop("_telemetryOnly", None)
    for fk in ("project", "directive", "status", "phase", "roundStatus"):
        if req.get(fk):
            tt[fk] = req[fk]
    if req_prog is not None:
        tt["progress"] = int(req_prog)
    if req.get("round") is not None:
        tt["round"] = int(req["round"])
    if req.get("maxRounds") is not None:
        tt["maxRounds"] = normalize_round_limit(req["maxRounds"])
    if req.get("roleCaps") is not None:
        tt["roleCaps"] = normalize_role_caps(req["roleCaps"])
    if req.get("triageDecision") is not None:
        tt["triageDecision"] = _norm_triage(req["triageDecision"])

    status_upper = str(tt.get("status") or "").upper()
    should_close_hard = status_upper in {"COMPLETED", "DONE", "CLOSED"} or (req_prog is not None and int(req_prog) >= 100 and status_upper != "HALTED")
    if not should_close_hard and (
        was_closed
        or req.get("round") == 1
        or (req.get("project") and req.get("directive"))
        or (req_prog is not None and int(req_prog) < 100 and (req.get("project") or req.get("directive")))
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
        tt.update({"status": "COMPLETED", "progress": 100, "pipelineStage": 5, "isClosed": True})
        if not req.get("phase"):
            tt["phase"] = "تکمیل‌شده و بسته — آماده برای تسک جدید"
        for ag in conv.get("agents", []):
            ag.update({
                "status": "COMPLETED", "activeTool": None, "tool": None,
                "currentTask": "تکمیل و تحویل نهایی", "task": "تکمیل و تحویل نهایی",
                "thought": "عملیات با موفقیت به پایان رسید و نشست بسته شد",
                "collaboratingWith": [], "updatedAtMs": ts_ms,
            })
        for st in conv.get("subtasks", []):
            st.update({"status": "COMPLETED", "updatedAt": hms, "updatedAtMs": ts_ms})
        rebuild_file_locks(conv)

        for f in conv.get("findings") or []:
            if isinstance(f, dict) and str(f.get("state") or "").lower() == "verified":
                f.update({"state": "Closed", "updatedAt": hms, "updatedAtMs": ts_ms})
        for col_name in ("messages", "interactions"):
            for item in conv.get(col_name, []):
                if isinstance(item, dict):
                    item["resolved"] = True
        for collab in conv.get("collaborations", []):
            if isinstance(collab, dict):
                collab["active"] = False
        if conv.get("proposal") and conv["proposal"].get("status") in {"AWAITING_APPROVAL", "PROPOSED", "APPROVED", "EXECUTING"}:
            conv["proposal"]["status"] = "COMPLETED"
        if str(req.get("summary") or "").strip():
            append_message(conv, {
                "id": f"complete-{ts_ms}-{uuid.uuid4().hex[:4]}",
                "channel": "MAIN", "senderCode": "TEAM-MANAGER", "senderName": "مدیر تیم",
                "senderRole": "team-manager", "timestamp": hms, "createdAtMs": ts_ms,
                "content": f"[تکمیل و بسته شدن نشست]: {str(req['summary']).strip()}",
                "isReview": False, "origin": req.get("origin"),
                "subagentConvId": req.get("subagentConvId"), "convId": cid,
            }, action_type="COMPLETE")
            tt["isClosed"] = True
        tt["closureReceipt"] = build_closure_receipt(conv, req.get("forceReason") if req.get("forceClose") else None)
        sync_pipeline_fields(conv)
        return archived_run_id, ["thinkTank", "agents", "subtasks", "fileLocks", "findings", "messages", "interactions", "graph", "proposal", "closureReceipt", "conversationsList"]
    if status_upper == "IDLE":
        for ag in conv.get("agents", []):
            ag.update({"status": "IDLE", "activeTool": None, "tool": None, "collaboratingWith": [], "updatedAtMs": ts_ms})
    sync_pipeline_fields(conv)
    if archived_run_id:
        return archived_run_id, [
            "thinkTank", "agents", "subtasks", "fileLocks", "findings",
            "messages", "interactions", "graph", "proposal", "review",
            "telemetry", "closureReceipt", "conversationsList",
        ]
    return archived_run_id, ["thinkTank", "agents", "conversationsList"]


def apply_subtask_upsert(cid: str, conv: dict[str, Any], req: dict[str, Any]) -> dict[str, Any]:
    require_case_open(conv)
    tt = conv["thinkTank"]
    subtasks = conv.setdefault("subtasks", [])
    ts_ms, hms = now_ms(), now_hms()

    canon_assignee = normalize_agent_id(req.get("assignee")) or str(req.get("assignee") or "").strip()
    canon_delegator = normalize_agent_id(req.get("delegatedBy") or "team-manager") or "team-manager"
    raw_status = str(req.get("status") or "ASSIGNED").upper().strip()
    status_upper = "COMPLETED" if raw_status == "DONE" else ("IN_REVIEW" if raw_status == "REVIEW" else raw_status)
    priority_upper = str(req.get("priority") or "HIGH").upper().strip()
    assignee_name = resolve_role_title(canon_assignee, req.get("assigneeName"))
    title_clean = str(req.get("title") or "").strip()

    subtask_id = str(req.get("id") or "").strip()
    existing_idx = -1
    for i, st in enumerate(subtasks):
        if (subtask_id and st.get("id") == subtask_id) or (
            not subtask_id and str(st.get("title") or "").strip() == title_clean and normalize_agent_id(st.get("assignee", "")) == canon_assignee
        ):
            existing_idx = i
            subtask_id = st.get("id") or f"task-{i + 1}"
            break
    if not subtask_id:
        subtask_id = f"task-{len(subtasks) + 1}-{int(time.time()) % 10000}"

    existing_entry = subtasks[existing_idx] if existing_idx >= 0 else {}
    if req.get("lockedFiles") is not None:
        locked_files: list[str] = []
        seen_paths: set[str] = set()
        for raw_f in req["lockedFiles"]:
            clean_f = str(raw_f or "").strip().replace("\\", "/")
            if clean_f and clean_f.lower() not in seen_paths:
                seen_paths.add(clean_f.lower())
                locked_files.append(clean_f)
    else:
        locked_files = list(existing_entry.get("lockedFiles") or [])

    acceptance = str(req["acceptanceCriteria"]).strip() if req.get("acceptanceCriteria") is not None else str(existing_entry.get("acceptanceCriteria") or "")
    if existing_idx < 0 and status_upper not in {"COMPLETED", "DONE"} and not acceptance:
        raise CaseGateError(409, "New active subtask requires a non-empty acceptanceCriteria.")

    if status_upper not in {"COMPLETED", "DONE"} and locked_files:
        req_lock_set = {p.lower(): p for p in locked_files}
        for st in subtasks:
            if not isinstance(st, dict) or st.get("id") == subtask_id or str(st.get("status") or "").upper() in {"COMPLETED", "DONE"}:
                continue
            other_owner = normalize_agent_id(st.get("assignee", ""))
            if other_owner == canon_assignee:
                continue
            for other_path in st.get("lockedFiles") or []:
                norm_other = str(other_path or "").strip().replace("\\", "/").lower()
                if norm_other in req_lock_set:
                    raise CaseGateError(409, f"File lock conflict on {req_lock_set[norm_other]} (already locked by {other_owner} in {st.get('id')}).")

    entry: dict[str, Any] = {
        "id": subtask_id, "title": title_clean, "assignee": canon_assignee,
        "assigneeName": assignee_name, "delegatedBy": canon_delegator,
        "delegatedByName": req.get("delegatedByName") or "مدیر تیم",
        "status": status_upper, "priority": priority_upper,
        "deliverable": str(req.get("deliverable") or "").strip(),
        "thoughts": str(req.get("thoughts") or "").strip() or existing_entry.get("thoughts", ""),
        "report": str(req.get("report") or "").strip() or existing_entry.get("report", ""),
        "dependencies": req["dependencies"] if req.get("dependencies") is not None else list(existing_entry.get("dependencies") or []),
        "lockedFiles": locked_files, "acceptanceCriteria": acceptance,
        "createdAtMs": int(existing_entry.get("createdAtMs") or ts_ms),
        "updatedAtMs": ts_ms, "updatedAt": hms,
    }
    if existing_idx >= 0:
        subtasks[existing_idx] = entry
    else:
        subtasks.insert(0, entry)
    rebuild_file_locks(conv)

    if subtasks:
        done_c = sum(1 for s in subtasks if s.get("status") == "COMPLETED")
        prog_c = sum(1 for s in subtasks if s.get("status") in {"IN_PROGRESS", "IN_REVIEW"})
        tt["progress"] = max(10, min(100, int(((done_c + 0.5 * prog_c) / len(subtasks)) * 100)))
        if done_c < len(subtasks) and tt.get("status") in {"DISCONNECTED", "IDLE", "COMPLETED"}:
            tt["status"] = "ACTIVE"

    sub_origin = normalize_origin({"origin": req.get("origin"), "subagentConvId": req.get("subagentConvId"), "senderRole": canon_delegator if status_upper == "ASSIGNED" else canon_assignee}, conv)
    verified_sub = sub_origin == "subagent"
    sub_cid = req.get("subagentConvId") if verified_sub else None

    if status_upper == "ASSIGNED":
        if verified_sub and canon_delegator:
            upsert_agent_state(conv, canon_delegator, name=req.get("delegatedByName"), status="ACTIVE", subagent_conv_id=sub_cid, verified_subagent=True)
        upsert_agent_state(conv, canon_assignee, name=assignee_name, role=canon_assignee, status="ACTIVE", task=title_clean, collaborating_with=canon_delegator, subagent_conv_id=sub_cid if canon_assignee == canon_delegator else None, verified_subagent=verified_sub and canon_assignee == canon_delegator)
    elif status_upper == "COMPLETED":
        other_active = any(s.get("id") != subtask_id and normalize_agent_id(s.get("assignee", "")) == canon_assignee and s.get("status") in {"ASSIGNED", "IN_PROGRESS", "IN_REVIEW"} for s in subtasks)
        upsert_agent_state(conv, canon_assignee, name=assignee_name, role=canon_assignee, status="ACTIVE" if other_active else "COMPLETED", task="تمام تسک‌های این عضو تکمیل شد" if not other_active else title_clean, subagent_conv_id=sub_cid, verified_subagent=verified_sub)
        if not other_active:
            for ag in conv.get("agents", []):
                if normalize_agent_id(ag.get("id", "")) == canon_assignee:
                    ag.update({"tool": None, "activeTool": None, "collaboratingWith": []})
    else:
        upsert_agent_state(conv, canon_assignee, name=assignee_name, role=canon_assignee, status="ACTIVE", task=title_clean, collaborating_with=canon_delegator, subagent_conv_id=sub_cid, verified_subagent=verified_sub)

    status_fa = {"ASSIGNED": "واگذاری تسک جدید", "IN_PROGRESS": "شروع اجرای تسک", "IN_REVIEW": "ارسال تسک برای بازبینی کیفیت", "COMPLETED": "تکمیل و تحویل تسک", "BLOCKED": "گزارش مانع در تسک"}.get(status_upper, status_upper)
    deliv = str(req.get("deliverable") or "").strip()
    msg_content = f"{status_fa}: «{title_clean}»\nمسئول اجرا: {assignee_name} ({canon_assignee})" + (f"\nخروجی و شواهد: {deliv}" if deliv else "")
    append_message(conv, {
        "id": f"subtask-msg-{ts_ms}-{uuid.uuid4().hex[:4]}", "channel": "SUBAGENTS",
        "senderCode": (canon_delegator if status_upper == "ASSIGNED" else canon_assignee).upper(),
        "senderName": (req.get("delegatedByName") or "مدیر تیم") if status_upper == "ASSIGNED" else assignee_name,
        "senderRole": canon_delegator if status_upper == "ASSIGNED" else canon_assignee,
        "recipientCode": (canon_assignee if status_upper == "ASSIGNED" else canon_delegator).upper(),
        "recipientName": assignee_name if status_upper == "ASSIGNED" else (req.get("delegatedByName") or "مدیر تیم"),
        "recipientRole": canon_assignee if status_upper == "ASSIGNED" else canon_delegator,
        "timestamp": hms, "createdAtMs": ts_ms, "content": msg_content,
        "thoughts": entry.get("thoughts") or None, "report": entry.get("report") or None,
        "workItemId": subtask_id, "origin": req.get("origin"),
        "subagentConvId": req.get("subagentConvId"), "convId": cid,
    }, action_type="DELEGATE" if status_upper == "ASSIGNED" else ("QA_DISPATCH" if status_upper == "IN_REVIEW" else "SUBTASK_UPDATE"), label=title_clean[:48])
    sync_pipeline_fields(conv)
    return entry


def apply_agent_update(conv: dict[str, Any], req: dict[str, Any]) -> None:
    require_case_open(conv)
    ts_ms = now_ms()
    target_id = normalize_agent_id(req.get("id")) or str(req.get("id") or "").strip()
    matched = next(
        (ag for ag in conv.setdefault("agents", []) if normalize_agent_id(ag.get("id")) == target_id or ag.get("id") == req.get("id")),
        None,
    )
    if matched is None:
        upsert_agent_state(conv, target_id, name=req.get("name"), role=req.get("role"), code=req.get("code"), status=req.get("status") or "ACTIVE", tool=req.get("tool"), thought=req.get("thought"), task=req.get("task"))
        matched = next((ag for ag in conv["agents"] if normalize_agent_id(ag.get("id")) == target_id), None)
    if matched is not None:
        for k in ("name", "role", "code", "icon", "thought", "demo", "status", "progress", "collaboratingWith"):
            if req.get(k) is not None:
                matched[k] = req[k]
        if req.get("task") is not None:
            matched["task"] = req["task"]
            matched["currentTask"] = req["task"]
        if req.get("tool") is not None:
            matched["tool"] = req["tool"]
            matched["activeTool"] = req["tool"]
        if req.get("latency") is not None:
            matched["latency"] = req["latency"]
            matched["latencyMs"] = req["latency"]
        matched["updatedAtMs"] = ts_ms


def apply_finding_action(conv: dict[str, Any], req: dict[str, Any]) -> dict[str, Any]:
    require_case_open(conv)
    finding = find_finding(conv, req.get("findingId"))
    if not finding:
        raise CaseGateError(404, f"Finding {req.get('findingId')} not found.")
    action_lower = str(req.get("action") or "").strip().lower()
    ts_ms, hms = now_ms(), now_hms()
    cur_state = CANONICAL_FINDING_STATES.get(str(finding.get("state") or "Open").strip().lower(), str(finding.get("state") or "Open"))
    if action_lower == "ack":
        if cur_state in {"Closed", "WontFix"}:
            raise CaseGateError(409, f"Finding {finding.get('id')} is {cur_state} and cannot accept ack.")
        finding.update({"state": "Fixing", "updatedAt": hms, "updatedAtMs": ts_ms})
    elif action_lower == "wontfix":
        reason_clean = str(req.get("reason") or "").strip()
        if not reason_clean:
            raise CaseGateError(409, "A non-empty reason is required for wontfix.")
        finding.update({"state": "WontFix", "wontFixReason": reason_clean, "updatedAt": hms, "updatedAtMs": ts_ms})
    elif action_lower == "mark_important":
        finding.update({"markedImportant": not bool(finding.get("markedImportant")), "updatedAt": hms, "updatedAtMs": ts_ms})
    else:
        raise CaseGateError(400, "Invalid finding action; expected ack, wontfix, or mark_important.")
    sync_pipeline_fields(conv)
    return finding


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


def apply_collaborate(cid: str, conv: dict[str, Any], req: dict[str, Any]) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]]]:
    require_case_open(conv)
    from_id = normalize_agent_id(req.get("fromAgent")) or str(req.get("fromAgent") or "").strip()
    to_id = normalize_agent_id(req.get("toAgent")) or str(req.get("toAgent") or "").strip()
    enforce_role_cap(conv, from_id or req.get("fromAgent"))

    action_upper = str(req.get("action") or "PEER_SYNC").strip().upper()
    target_channel = _derive_collab_channel(action_upper, req.get("channel"))
    raw_sev = req.get("severity")
    severity_clean = raw_sev.strip().lower() if isinstance(raw_sev, str) and raw_sev.strip() else None
    result_upper = str(req.get("result") or "").strip().upper()

    findings_list = conv.setdefault("findings", [])
    req_fid = str(req.get("findingId") or "").strip().upper() or None
    if action_upper in {"WORKER_FIX", "QA_DISPATCH", "QA_REPORT"} and not req_fid:
        raise CaseGateError(409, f"{action_upper} requires a non-empty findingId.")
    finding = find_finding(conv, req_fid) if req_fid else None
    if action_upper in {"WORKER_FIX", "REVIEW_QUERY", "QA_DISPATCH", "QA_REPORT"} and req_fid and finding is None:
        raise CaseGateError(404, f"Finding {req_fid} not found.")
    if finding is not None:
        raw_state = str(finding.get("state") or "Open").strip()
        cur_state = CANONICAL_FINDING_STATES.get(raw_state.lower(), raw_state)
        if cur_state in {"Closed", "WontFix"} and action_upper in {"WORKER_FIX", "QA_DISPATCH", "QA_REPORT", "RETURN_DEFECT"}:
            raise CaseGateError(409, f"Finding {finding.get('id')} is {cur_state} and cannot accept {action_upper}.")
        if action_upper == "REVIEW_QUERY" and cur_state not in {"Open", "Fixing", "InReview", "Testing"}:
            raise CaseGateError(409, f"REVIEW_QUERY cannot run on finding {finding.get('id')} in state {cur_state}.")
        if action_upper == "WORKER_FIX" and cur_state not in {"Open", "Fixing", "InReview"}:
            raise CaseGateError(409, f"WORKER_FIX requires finding state in Open, Fixing, or InReview (got {cur_state}).")
        if action_upper == "QA_DISPATCH" and cur_state not in {"InReview", "Testing"}:
            raise CaseGateError(409, f"QA_DISPATCH requires finding state in InReview or Testing (got {cur_state}).")
        if action_upper == "QA_REPORT" and cur_state != "Testing":
            raise CaseGateError(409, f"QA_REPORT requires finding state to be Testing (got {cur_state}).")

    cur_round = int((conv.get("thinkTank") or {}).get("round") or 1)
    repro_clean = str(req.get("reproSteps") or req.get("question") or "").strip()
    if action_upper == "RETURN_DEFECT":
        sev_upper = str(req.get("severity") or "HIGH").strip().upper()
        if sev_upper not in {"CRITICAL", "HIGH", "MEDIUM"}:
            raise CaseGateError(400, "Severity must be CRITICAL, HIGH, or MEDIUM.")
        if not repro_clean:
            raise CaseGateError(409, "RETURN_DEFECT requires non-empty reproSteps.")
        if finding is None:
            round_count = sum(1 for f in findings_list if isinstance(f, dict) and int(f.get("round") or 1) == cur_round)
            if round_count >= 7:
                raise CaseGateError(409, "Maximum 7 findings per round reached.")
    if action_upper == "QA_REPORT":
        if str(req.get("runner") or "substrate").strip().lower() == "host-fallback" and not str(req.get("runnerReason") or "").strip():
            raise CaseGateError(409, "runner='host-fallback' requires a non-empty runnerReason.")
        if result_upper == "PASS":
            raw_exit = req.get("exitCode")
            if not str(req.get("evidenceCommand") or "").strip() or raw_exit is None or isinstance(raw_exit, bool) or int(raw_exit) != 0:
                raise CaseGateError(409, "QA_REPORT PASS requires a non-empty evidenceCommand and exitCode == 0.")

    ts_ms, hms = now_ms(), now_hms()
    effective_fid = finding["id"] if finding else req_fid
    if action_upper == "RETURN_DEFECT" and finding is None:
        effective_fid = req_fid or next_finding_id(conv)

    collabs = conv.setdefault("collaborations", [])
    existing = next(
        (c for c in collabs if (c.get("from") == from_id and c.get("to") == to_id) or (c.get("from") == to_id and c.get("to") == from_id)),
        None,
    )
    is_collab_active = not (action_upper == "QA_REPORT" and result_upper == "PASS")
    label_clean = str(req.get("label") or "").strip() or (existing.get("label") if existing else "همکاری و مباحثه فعال")
    if existing:
        existing["active"] = is_collab_active
        existing["action"] = action_upper
        existing["channel"] = target_channel
        if severity_clean:
            existing["severity"] = severity_clean
        existing["label"] = label_clean
    else:
        existing = {
            "from": from_id, "to": to_id, "action": action_upper,
            "channel": target_channel, "label": label_clean, "active": is_collab_active,
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

    agents_list = conv.setdefault("agents", [])
    from_existing = next((a.get("name") for a in agents_list if normalize_agent_id(a.get("id")) == from_id), None)
    to_existing = next((a.get("name") for a in agents_list if normalize_agent_id(a.get("id")) == to_id), None)
    from_name = resolve_role_title(from_id, from_existing or req.get("fromName"))
    to_name = resolve_role_title(to_id, to_existing or req.get("toName"))

    task_hints = {
        "RETURN_DEFECT": f"در حال رفع ایراد برگشتی از {from_name}",
        "WORKER_FIX": f"بازبینی اصلاحیه ارسال‌شده از {from_name}",
        "REVIEW_QUERY": f"پاسخ به پرسش بررسی از {from_name}",
        "INTERROGATE": f"در حال پاسخ‌گویی به بازخواست از {from_name}",
        "INTERROGATE_REPLY": f"بررسی پاسخ بازخواست از {from_name}",
        "QA_DISPATCH": f"اجرای تست QA به دستور {from_name}",
    }
    target_task_hint = task_hints.get(action_upper)
    if action_upper == "QA_REPORT" and result_upper:
        target_task_hint = f"گزارش QA ثبت شد ({result_upper})"

    collab_origin = normalize_origin({"origin": req.get("origin"), "subagentConvId": req.get("subagentConvId"), "senderRole": from_id}, conv)
    verified_sub = collab_origin == "subagent"
    upsert_agent_state(
        conv, from_id, name=from_name, status="ACTIVE",
        thought=req.get("thoughts") or req.get("thought") or req.get("question") or req.get("critique"),
        collaborating_with=to_id, increment_turn=True,
        subagent_conv_id=req.get("subagentConvId") if verified_sub else None,
        verified_subagent=verified_sub,
    )
    upsert_agent_state(conv, to_id, name=to_name, status="ACTIVE", task=target_task_hint, collaborating_with=from_id)

    msg_text = str(
        req.get("content")
        or req.get("crosstalkMessage")
        or req.get("question")
        or req.get("critique")
        or req.get("report")
        or req.get("fullReport")
        or label_clean
        or action_upper
    ).strip()

    collab_msg: dict[str, Any] = {
        "id": f"collab-{ts_ms}-{uuid.uuid4().hex[:6]}",
        "channel": target_channel,
        "action": action_upper,
        "requestType": req.get("requestType"),
        "severity": severity_clean,
        "parentSeq": req.get("parentSeq"),
        "result": result_upper or None,
        "senderCode": from_id.upper(),
        "senderName": from_name,
        "senderRole": from_id,
        "recipientCode": to_id.upper(),
        "recipientName": to_name,
        "recipientRole": to_id,
        "recipient": to_id,
        "timestamp": hms,
        "createdAtMs": ts_ms,
        "content": msg_text,
        "thoughts": req.get("thoughts") or req.get("thought"),
        "critique": req.get("critique"),
        "question": req.get("question"),
        "report": req.get("report") or req.get("fullReport"),
        "origin": req.get("origin"),
        "subagentConvId": req.get("subagentConvId"),
        "findingId": effective_fid,
        "workItemId": req.get("workItemId"),
        "reproSteps": req.get("reproSteps"),
        "convId": cid,
    }
    append_message(conv, collab_msg, action_type=action_upper, severity=severity_clean, label=label_clean)
    existing["lastSeq"] = collab_msg.get("seq")

    ev_seq = collab_msg.get("seq")
    if action_upper == "RETURN_DEFECT":
        if finding is not None:
            finding["state"] = "Fixing"
            finding["returnCount"] = int(finding.get("returnCount") or 0) + 1
            finding["reproSteps"] = repro_clean
            if req.get("workItemId"):
                finding["workItemId"] = req["workItemId"]
            finding["updatedAt"] = hms
            finding["updatedAtMs"] = ts_ms
            if ev_seq and ev_seq not in finding.setdefault("events", []):
                finding["events"].append(ev_seq)
        else:
            title_src = req.get("critique") or req.get("question") or req.get("content") or req.get("crosstalkMessage") or label_clean or "Defect"
            finding = {
                "id": effective_fid,
                "title": str(title_src).strip().splitlines()[0][:160],
                "severity": str(req.get("severity") or "HIGH").strip().upper(),
                "owner": to_id,
                "raisedBy": from_id,
                "workItemId": req.get("workItemId"),
                "round": cur_round,
                "state": "Open",
                "reproSteps": repro_clean,
                "returnCount": 0,
                "wontFixReason": None,
                "markedImportant": False,
                "events": [ev_seq] if ev_seq else [],
                "evidence": [],
                "createdAt": hms,
                "updatedAt": hms,
                "createdAtMs": ts_ms,
                "updatedAtMs": ts_ms,
            }
            findings_list.append(finding)
    elif action_upper == "WORKER_FIX" and finding is not None:
        finding["state"] = "InReview"
        finding["updatedAt"] = hms
        finding["updatedAtMs"] = ts_ms
        if ev_seq and ev_seq not in finding.setdefault("events", []):
            finding["events"].append(ev_seq)
    elif action_upper == "REVIEW_QUERY" and finding is not None:
        sev_upper = str(req.get("severity") or "").strip().upper()
        if bool(req.get("returnToFixing")) or result_upper == "REJECT" or sev_upper in {"HIGH", "CRITICAL"}:
            finding["state"] = "Fixing"
            finding["returnCount"] = int(finding.get("returnCount") or 0) + 1
        finding["updatedAt"] = hms
        finding["updatedAtMs"] = ts_ms
        if ev_seq and ev_seq not in finding.setdefault("events", []):
            finding["events"].append(ev_seq)
    elif action_upper == "QA_DISPATCH" and finding is not None:
        finding["state"] = "Testing"
        finding["updatedAt"] = hms
        finding["updatedAtMs"] = ts_ms
        if ev_seq and ev_seq not in finding.setdefault("events", []):
            finding["events"].append(ev_seq)
    elif action_upper == "QA_REPORT":
        has_ev_input = bool(
            finding is not None
            or str(req.get("evidenceCommand") or "").strip()
            or req.get("exitCode") is not None
            or req.get("evidenceExcerpt") is not None
        )
        if has_ev_input:
            raw_excerpt = req.get("evidenceExcerpt") if req.get("evidenceExcerpt") is not None else (req.get("report") or req.get("fullReport") or msg_text or "")
            excerpt_lines = str(raw_excerpt).splitlines()
            excerpt_text = "\n".join(excerpt_lines[:20]) if len(excerpt_lines) > 20 else str(raw_excerpt)
            ev_record = {
                "seq": ev_seq,
                "command": str(req.get("evidenceCommand") or "").strip(),
                "exitCode": req.get("exitCode"),
                "stdoutHash": hashlib.sha256(excerpt_text.encode("utf-8")).hexdigest(),
                "excerpt": excerpt_text,
                "runner": str(req.get("runner") or "substrate").strip(),
                "runnerReason": str(req.get("runnerReason") or "").strip() or None,
                "timestamp": hms,
                "createdAtMs": ts_ms,
            }
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
            finding["updatedAt"] = hms
            finding["updatedAtMs"] = ts_ms

    sync_pipeline_fields(conv)
    return finding, collab_msg


def apply_proposal_update(cid: str, conv: dict[str, Any], req: dict[str, Any]) -> dict[str, Any]:
    require_case_open(conv)
    ts_ms = now_ms()
    prop = {
        "id": str(req.get("id") or f"prop-{int(time.time())}"),
        "project": str(req.get("project") or ""),
        "title": str(req.get("title") or ""),
        "author": str(req.get("author") or "Team Manager"),
        "status": "AWAITING_APPROVAL",
        "summary": str(req.get("summary") or ""),
        "decisionOptions": list(req.get("decisionOptions") or []),
        "votes": list(req.get("votes") or []),
        "userDecision": None,
        "lastActionAt": None,
        "createdAtMs": ts_ms,
        "updatedAtMs": ts_ms,
    }
    conv["proposal"] = prop
    tt = conv.setdefault("thinkTank", dict(DEFAULT_THINK_TANK_STATE))
    tt["status"] = "ACTIVE"
    tt["phase"] = "Awaiting User Approval on Proposal"
    sync_pipeline_fields(conv)
    return prop


def apply_proposal_action(cid: str, conv: dict[str, Any], req: dict[str, Any]) -> Optional[dict[str, Any]]:
    require_case_open(conv)
    action = str(req.get("action") or "").strip().lower()
    if action not in {"approve", "request_revision", "select_option", "halt"}:
        raise CaseGateError(400, "Invalid proposal action; expected approve, request_revision, select_option, or halt.")
    current_prop = conv.get("proposal")
    if current_prop is None and action != "halt":
        raise CaseGateError(409, "No active proposal exists for this session.")

    tt = conv.setdefault("thinkTank", dict(DEFAULT_THINK_TANK_STATE))
    ts_ms, hms = now_ms(), now_hms()
    option_id = req.get("optionId")
    comment = req.get("comment")

    if current_prop is None:
        current_prop = {
            "id": f"prop-{int(time.time())}",
            "project": tt.get("project") or "",
            "title": tt.get("directive") or "Case Proposal",
            "author": "Council",
            "status": "HALTED",
            "summary": "",
            "decisionOptions": [],
            "votes": [],
            "userDecision": None,
            "lastActionAt": hms,
            "createdAtMs": ts_ms,
            "updatedAtMs": ts_ms,
        }
        conv["proposal"] = current_prop

    if action == "approve":
        current_prop["status"] = "APPROVED"
        current_prop["userDecision"] = {
            "action": "APPROVED", "optionId": option_id,
            "comment": comment or "طرح توسط کاربر تایید و دستور اجرای قطعی صادر شد.",
            "timestamp": hms, "createdAtMs": ts_ms,
        }
        tt["status"] = "EXECUTING"
        tt["progress"] = 90
        tt["phase"] = "Applying Changes & Final Production Verification"
        msg_content = f"[تایید رسمی کاربر]: طرح «{current_prop.get('title', '')}» مورد تایید قرار گرفت و دستور اجرا صادر شد."
        channel = "MAIN"
    elif action == "select_option":
        current_prop["userDecision"] = {
            "action": "OPTION_SELECTED", "optionId": option_id,
            "comment": comment, "timestamp": hms, "createdAtMs": ts_ms,
        }
        selected_text = option_id
        for opt in current_prop.get("decisionOptions") or []:
            if isinstance(opt, dict) and opt.get("id") == option_id:
                selected_text = opt.get("label", option_id)
                break
        msg_content = f"[انتخاب گزینه توسط کاربر]: «{selected_text}»\nپروسه با گزینه انتخابی ادامه می‌یابد."
        channel = "MAIN"
    elif action == "request_revision":
        current_prop["status"] = "REVISION_REQUESTED"
        current_prop["userDecision"] = {
            "action": "REVISION_REQUESTED",
            "comment": comment or "درخواست اصلاح و بازنگری توسط کاربر ثبت شد.",
            "timestamp": hms, "createdAtMs": ts_ms,
        }
        tt["status"] = "ACTIVE"
        tt["phase"] = "Council Revising Plan According to Feedback"
        msg_content = f"[درخواست اصلاح از سوی کاربر]: لطفا طرح بازنگری و مجددا چکش‌کاری شود.\nتوضیحات: {comment or 'عدم تایید نسخه فعلی'}"
        channel = "SUBAGENTS"
    else:
        current_prop["status"] = "HALTED"
        tt["status"] = "HALTED"
        tt["phase"] = "Session Halted by Operator"
        msg_content = "[دستور توقف توسط کاربر]: نشست اتاق فکر به درخواست صریح کاربر متوقف گردید."
        channel = "MAIN"

    current_prop["lastActionAt"] = hms
    current_prop["updatedAtMs"] = ts_ms
    append_message(conv, {
        "id": f"act-{ts_ms}-{uuid.uuid4().hex[:4]}",
        "channel": channel, "senderCode": "OPERATOR", "senderName": "Operator",
        "senderRole": "owner", "isOperator": True, "origin": "user",
        "timestamp": hms, "createdAtMs": ts_ms, "content": msg_content, "convId": cid,
    }, action_type="DECISION")
    sync_pipeline_fields(conv)
    return current_prop


def apply_proposal_vote(cid: str, conv: dict[str, Any], req: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    require_case_open(conv)
    tt = conv.setdefault("thinkTank", dict(DEFAULT_THINK_TANK_STATE))
    ts_ms, hms = now_ms(), now_hms()

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
            "votes": [], "userDecision": None, "lastActionAt": None,
            "createdAtMs": ts_ms, "updatedAtMs": ts_ms,
        }

    prop = conv["proposal"]
    votes = prop.setdefault("votes", [])
    canon_voter = normalize_agent_id(req.get("voter")) or str(req.get("voter") or "").strip()
    stance_upper = str(req.get("stance") or "APPROVE").upper().strip()
    voter_name = resolve_role_title(canon_voter, req.get("voterName"))
    comment_clean = str(req.get("comment") or "").strip()

    vote_entry = {
        "voter": canon_voter,
        "voterName": voter_name,
        "voterRole": req.get("voterRole") or canon_voter,
        "stance": stance_upper,
        "confidence": max(0, min(100, int(req.get("confidence") if req.get("confidence") is not None else 90))),
        "comment": comment_clean,
        "counterArgument": str(req.get("counterArgument") or "").strip() or None,
        "timestamp": hms,
        "createdAtMs": ts_ms,
    }
    replaced = False
    for idx_v, existing in enumerate(votes):
        if normalize_agent_id(existing.get("voter", "")) == canon_voter:
            votes[idx_v] = vote_entry
            replaced = True
            break
    if not replaced:
        votes.append(vote_entry)
    prop["updatedAtMs"] = ts_ms

    stance_labels = {
        "APPROVE": "موافق (تأیید طرح)",
        "CONDITIONAL": "موافق مشروط",
        "CRITIQUE": "نقد و چالش راهبردی",
        "REJECT": "مخالف (رد طرح)",
    }
    stance_badge = stance_labels.get(stance_upper, stance_upper)
    target_role = "team-manager" if canon_voter != "team-manager" else "main_agent"
    msg_entry: dict[str, Any] = {
        "id": f"vote-{ts_ms}-{uuid.uuid4().hex[:4]}",
        "channel": "COUNCIL",
        "senderCode": canon_voter.upper(),
        "senderName": voter_name,
        "senderRole": req.get("voterRole") or canon_voter,
        "recipientCode": target_role.upper(),
        "recipientName": resolve_role_title(target_role),
        "recipientRole": target_role,
        "timestamp": hms,
        "createdAtMs": ts_ms,
        "content": f"{stance_badge} (اطمینان: {vote_entry['confidence']}٪)\n{comment_clean}",
        "thoughts": comment_clean if stance_upper in {"APPROVE", "CONDITIONAL"} else None,
        "critique": str(req.get("counterArgument") or comment_clean).strip() if stance_upper in {"CRITIQUE", "REJECT"} else None,
        "origin": req.get("origin"),
        "subagentConvId": req.get("subagentConvId"),
        "requestType": "DECISION",
        "convId": cid,
    }
    append_message(conv, msg_entry, action_type="VOTE", label=stance_badge)

    vote_origin = normalize_origin({"origin": req.get("origin"), "subagentConvId": req.get("subagentConvId"), "senderRole": canon_voter}, conv)
    verified_sub = vote_origin == "subagent"
    upsert_agent_state(
        conv, canon_voter, name=voter_name, role=req.get("voterRole") or canon_voter,
        status="ACTIVE", thought=f"{stance_badge}: {comment_clean[:80]}",
        subagent_conv_id=req.get("subagentConvId") if verified_sub else None,
        verified_subagent=verified_sub,
    )
    sync_pipeline_fields(conv)
    return vote_entry, prop, msg_entry


def apply_chat_send(cid: str, conv: dict[str, Any], req: dict[str, Any]) -> tuple[dict[str, Any], bool, bool]:
    require_case_open(conv)
    msg_dict = dict(req)
    ts_ms, hms = now_ms(), now_hms()
    if not msg_dict.get("id"):
        msg_dict["id"] = f"msg-{ts_ms}-{uuid.uuid4().hex[:6]}"
    if not msg_dict.get("timestamp"):
        msg_dict["timestamp"] = hms
    msg_dict.setdefault("createdAtMs", ts_ms)

    if not (msg_dict.get("recipient") or msg_dict.get("recipientName") or msg_dict.get("recipientCode") or msg_dict.get("recipientRole")):
        mention_match = re.search(r"@([A-Za-z0-9_\u0600-\u06FF-]+)", str(msg_dict.get("content") or ""))
        if mention_match:
            recip = mention_match.group(1).strip()
            msg_dict["recipient"] = recip
            msg_dict["recipientName"] = recip
            msg_dict["recipientCode"] = recip.upper()

    if any(isinstance(ex, dict) and ex.get("id") == msg_dict.get("id") for ex in conv.get("messages") or []):
        return msg_dict, True, False

    bucket = role_bucket(msg_dict.get("senderRole"))
    if msg_dict.get("isReview"):
        review = conv.get("review") or {}
        if bucket not in {"main", "manager"}:
            raise CaseGateError(409, "Only the main agent and team manager can post review messages.")
        if (
            review.get("status") not in {"DISPATCH_PENDING", "DISPATCH_FAILED", "AWAITING_TEAM_REVIEW"}
            or not msg_dict.get("reviewId")
            or msg_dict.get("reviewId") != review.get("id")
        ):
            raise CaseGateError(409, "Review messages must reference the current pending review request.")
    elif not msg_dict.get("isOperator"):
        enforce_role_cap(conv, msg_dict.get("senderRole"), is_review=False, review_id=msg_dict.get("reviewId"))

    is_btw = bool(msg_dict.get("isBtw") or str(msg_dict.get("content") or "").startswith("/btw") or "/btw" in str(msg_dict.get("senderCode") or ""))
    if is_btw:
        msg_dict["isBtw"] = True
        msg_dict["channel"] = "SUBAGENTS"
    elif str(msg_dict.get("channel") or "").upper() == "ALL":
        msg_dict["channel"] = "MAIN"

    agents_modified = False
    is_closed = str((conv.get("thinkTank") or {}).get("status") or "").upper() in {"COMPLETED", "DONE", "CLOSED"}
    sender_clean = normalize_agent_id(msg_dict.get("senderCode") or msg_dict.get("senderRole"))
    recipient_clean = normalize_agent_id(msg_dict.get("recipient") or msg_dict.get("recipientCode") or msg_dict.get("recipientRole"))

    if sender_clean and not msg_dict.get("isOperator") and sender_clean not in OPERATOR_ALIASES and not is_closed:
        resolved_origin = normalize_origin(msg_dict, conv)
        verified_sub = resolved_origin == "subagent"
        agents_modified |= upsert_agent_state(
            conv, sender_clean,
            name=msg_dict.get("senderName"), role=msg_dict.get("senderRole"), code=msg_dict.get("senderCode"),
            status="ACTIVE", thought=msg_dict.get("thoughts") or msg_dict.get("thought"),
            collaborating_with=recipient_clean if (recipient_clean and recipient_clean != sender_clean) else None,
            increment_turn=True,
            subagent_conv_id=msg_dict.get("subagentConvId") if verified_sub else None,
            verified_subagent=verified_sub,
        )
    if recipient_clean and recipient_clean != sender_clean and recipient_clean not in OPERATOR_ALIASES and recipient_clean not in {"all", "council"} and not is_closed:
        agents_modified |= upsert_agent_state(
            conv, recipient_clean,
            name=msg_dict.get("recipientName") or msg_dict.get("recipient"),
            role=msg_dict.get("recipientRole"), code=msg_dict.get("recipientCode"),
            status="ACTIVE", collaborating_with=sender_clean,
        )

    append_message(conv, msg_dict)
    return msg_dict, False, agents_modified


def apply_governance_extend(cid: str, conv: dict[str, Any], req: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    require_case_open(conv)
    tt = conv.setdefault("thinkTank", dict(DEFAULT_THINK_TANK_STATE))
    additional = int(req.get("additionalRounds") if req.get("additionalRounds") is not None else 3)
    tt["maxRounds"] = min(500, normalize_round_limit(tt.get("maxRounds", 50)) + max(1, additional))
    tt["roundStatus"] = "ACTIVE"
    ts_ms, hms = now_ms(), now_hms()
    msg = {
        "id": f"gov-{uuid.uuid4()}",
        "channel": "MAIN", "senderCode": "OWNER", "senderName": "کاربر",
        "senderRole": "owner", "isOperator": True, "origin": "user",
        "timestamp": hms, "createdAtMs": ts_ms,
        "content": f"سقف دورهای گفتگو با درخواست کاربر به {tt['maxRounds']} افزایش یافت.",
        "convId": cid,
    }
    append_message(conv, msg, action_type="GOVERNANCE")
    return {"status": "extended", "convId": cid, "maxRounds": tt["maxRounds"], "roundStatus": "ACTIVE"}, msg


def apply_governance_reopen(
    cid: str, conv: dict[str, Any], conversations_store: dict[str, dict[str, Any]], store: Any = None,
) -> tuple[Optional[str], list[str]]:
    return apply_task_update(cid, conv, {"reopen": True}, conversations_store, store=store)


def apply_governance_compress(cid: str, conv: dict[str, Any]) -> dict[str, Any]:
    require_case_open(conv)
    tt = conv.setdefault("thinkTank", dict(DEFAULT_THINK_TANK_STATE))
    tt["roundStatus"] = "REVIEW_REQUESTED"
    tt["phase"] = "درخواست بازبینی مدیر تیم"
    conv["review"] = {
        "id": f"review-{uuid.uuid4()}",
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
    sync_pipeline_fields(conv)
    return conv["review"]


def apply_review_dispatch(cid: str, conv: dict[str, Any], req: dict[str, Any]) -> dict[str, Any]:
    require_case_open(conv)
    review = conv.get("review")
    if not review or review.get("status") not in {"DISPATCH_PENDING", "DISPATCH_FAILED", "AWAITING_TEAM_REVIEW"}:
        raise CaseGateError(409, "There is no pending team review request.")
    status_val = str(req.get("status") or "").strip().lower()
    review["dispatchStatus"] = status_val
    review["dispatchError"] = str(req.get("error") or "")[:800] if status_val == "failed" else ""
    review["status"] = "AWAITING_TEAM_REVIEW" if status_val == "sent" else "DISPATCH_FAILED"
    return review


def apply_review_submit(cid: str, conv: dict[str, Any], req: dict[str, Any]) -> dict[str, Any]:
    require_case_open(conv)
    existing = conv.get("review")
    if not existing or existing.get("status") not in {"AWAITING_TEAM_REVIEW", "DISPATCH_PENDING"}:
        raise CaseGateError(409, "A team review was not requested for this session.")
    if req.get("reviewId") != existing.get("id"):
        raise CaseGateError(409, "The review submission does not match the current review request.")

    review_messages = {
        role_bucket(m.get("senderRole")): m
        for m in conv.get("messages") or []
        if isinstance(m, dict)
        and m.get("isReview") is True
        and m.get("reviewId") == existing.get("id")
        and role_bucket(m.get("senderRole")) in {"manager", "main"}
    }
    if "manager" not in review_messages or "main" not in review_messages:
        raise CaseGateError(409, "The team manager and main agent must first post their real review messages.")
    mgr_sum = str(req.get("managerSummary") or "").strip()
    main_sum = str(req.get("mainSummary") or "").strip()
    if mgr_sum != str(review_messages["manager"].get("content", "")).strip() or main_sum != str(review_messages["main"].get("content", "")).strip():
        raise CaseGateError(422, "Review summaries must match the current messages visible in the Think Tank room.")
    cont = list(req.get("continueReasons") or [])
    comp = list(req.get("completionReasons") or [])
    evid = list(req.get("evidence") or [])
    if not all(str(r).strip() for r in cont + comp + evid):
        raise CaseGateError(422, "Review reasons and evidence cannot be blank.")

    try:
        decision = evaluate_review(req.get("confidence"), mgr_sum, main_sum, req.get("recommendation"))
    except ValueError as err:
        raise CaseGateError(422, str(err)) from err

    review = {
        **existing, **decision,
        "continueReasons": [str(item).strip() for item in cont],
        "completionReasons": [str(item).strip() for item in comp],
        "evidence": [str(item).strip() for item in evid],
        "submittedAt": time.time(),
    }
    if not review["humanRequired"] and review["decision"] == "complete":
        unresolved = [
            f for f in (conv.get("findings") or [])
            if isinstance(f, dict) and str(f.get("state") or "").lower() in {"open", "fixing", "inreview", "testing"}
        ]
        if unresolved:
            ids = ", ".join(str(f.get("id") or "?") for f in unresolved[:5])
            raise CaseGateError(409, f"Cannot complete session via review while {len(unresolved)} unresolved finding(s) remain ({ids}).")
    conv["review"] = review
    tt = conv.setdefault("thinkTank", dict(DEFAULT_THINK_TANK_STATE))
    ts_ms, hms = now_ms(), now_hms()
    if review["humanRequired"]:
        tt["roundStatus"] = "WAITING_FOR_HUMAN"
        tt["phase"] = "در انتظار تصمیم شما"
    elif review["decision"] == "complete":
        for f in conv.get("findings") or []:
            if isinstance(f, dict) and str(f.get("state") or "").lower() == "verified":
                f.update({"state": "Closed", "updatedAt": hms, "updatedAtMs": ts_ms})
        for ag in conv.get("agents", []):
            ag.update({
                "status": "COMPLETED", "activeTool": None, "tool": None,
                "collaboratingWith": [], "updatedAtMs": ts_ms,
            })
        for st in conv.get("subtasks", []):
            st.update({"status": "COMPLETED", "updatedAt": hms, "updatedAtMs": ts_ms})
        rebuild_file_locks(conv)
        for col_name in ("messages", "interactions"):
            for item in conv.get(col_name, []):
                if isinstance(item, dict):
                    item["resolved"] = True
        tt.update({
            "roundStatus": "COMPLETE",
            "status": "COMPLETED",
            "progress": 100,
            "pipelineStage": 5,
            "isClosed": True,
            "phase": "بازبینی مدیر و ایجنت اصلی کامل شد",
        })
        tt["closureReceipt"] = build_closure_receipt(conv, None)
    else:
        tt["roundStatus"] = "ACTIVE"
        tt["status"] = "ACTIVE"
        tt["phase"] = "ادامه کار بر اساس بازبینی تیم"
    sync_pipeline_fields(conv)
    return review


def apply_review_decision(cid: str, conv: dict[str, Any], req: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    require_case_open(conv)
    review = conv.get("review")
    if not review or review.get("status") != "WAITING_FOR_HUMAN" or not review.get("humanRequired"):
        raise CaseGateError(409, "No human decision is currently required.")
    decided_at = time.time()
    ts_ms, hms = now_ms(), now_hms()
    decision = str(req.get("decision") or "").strip().lower()
    note = str(req.get("note") or "")
    review["decision"] = decision
    review["humanDecision"] = {"decision": decision, "note": note, "decidedAt": decided_at, "dispatchStatus": "pending"}
    review["status"] = "HUMAN_CONTINUE" if decision == "continue" else "HUMAN_STOP"
    tt = conv.setdefault("thinkTank", dict(DEFAULT_THINK_TANK_STATE))
    tt["roundStatus"] = "ACTIVE" if decision == "continue" else "HALTED"
    tt["status"] = "ACTIVE" if decision == "continue" else "HALTED"
    tt["phase"] = "ادامه با تصمیم کاربر" if decision == "continue" else "توقف با تصمیم کاربر"
    msg = {
        "id": f"review-decision-{uuid.uuid4()}",
        "channel": "MAIN", "senderCode": "OWNER", "senderName": "کاربر",
        "senderRole": "owner", "isOperator": True, "origin": "user",
        "timestamp": hms, "createdAtMs": ts_ms,
        "content": ("ادامه کار" if decision == "continue" else "توقف کار") + (f" - {note.strip()}" if note.strip() else ""),
        "convId": cid,
    }
    append_message(conv, msg, action_type="DECISION")
    sync_pipeline_fields(conv)
    return review, msg


def apply_review_decision_dispatch(cid: str, conv: dict[str, Any], req: dict[str, Any]) -> dict[str, Any]:
    review = conv.get("review")
    human_decision = (review or {}).get("humanDecision")
    if not human_decision:
        raise CaseGateError(409, "There is no human review decision to deliver.")
    status_val = str(req.get("status") or "").strip().lower()
    human_decision["dispatchStatus"] = status_val
    human_decision["dispatchError"] = str(req.get("error") or "")[:800] if status_val == "failed" else ""
    return review


def apply_telemetry_tool(
    cid: str,
    raw_cid: str,
    conv: dict[str, Any],
    req: dict[str, Any],
    session_resolver: Any,
    conversations_store: dict[str, dict[str, Any]],
    *,
    mapped: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    tt = conv.setdefault("thinkTank", dict(DEFAULT_THINK_TANK_STATE))
    had_tt_before = has_thinktank_activity(conv)
    is_closed = bool(tt.get("isClosed")) or str(tt.get("status") or "").upper() in {"COMPLETED", "DONE", "CLOSED"}
    if not is_closed and tt.get("status") in {"DISCONNECTED", "UNKNOWN", "IDLE"}:
        tt["status"] = "ACTIVE"
        if not had_tt_before:
            conv["_telemetryOnly"] = True

    telemetry = conv.setdefault("telemetry", {"toolCalls": [], "terminalLogs": [], "backgroundTasks": []})
    calls = telemetry.setdefault("toolCalls", [])
    previous = next((c for c in calls if isinstance(c, dict) and c.get("id") == req.get("id")), None)
    if previous is not None:
        return {"duplicate": True, "convId": cid, "entry": previous, "autoCollabMsg": None, "agentUpdated": False, "durableAgentEvent": False}

    ts_ms, hms = now_ms(), now_hms()
    mapped_role = mapped.get("roleId") if mapped else None
    req_agent_id = req.get("agentId")
    req_agent_name = req.get("agentName")
    entry_agent_id = mapped_role or req_agent_id or "antigravity"
    entry_agent_name = (
        req_agent_name
        if (req_agent_name and req_agent_name != "Antigravity")
        else (mapped.get("roleTitle") or mapped_role if mapped else (req_agent_name or "Antigravity"))
    )
    tool_name = str(req.get("tool") or "").strip()
    entry = SyncEventStore.compact_tool_entry({
        "id": req.get("id"),
        "agentId": entry_agent_id,
        "agentName": entry_agent_name,
        "tool": tool_name,
        "args": req.get("args") or {},
        "output": req.get("output") or "",
        "error": req.get("error") or "",
        "status": req.get("status") or "SUCCESS",
        "latencyMs": None,
        "timestamp": hms,
        "createdAtMs": ts_ms,
        "source": "antigravity-hook",
        "stepIdx": req.get("stepIdx"),
    })
    if mapped:
        entry["subagentConvId"] = raw_cid
    calls.insert(0, entry)
    telemetry["toolCalls"] = calls[:25]

    agent_updated = False
    durable_agent_event = False
    auto_collab_msg: Optional[dict[str, Any]] = None
    caller_role = mapped_role if (mapped_role and mapped_role not in {"user", "subagent"}) else normalize_agent_id(req_agent_id or "main_agent")
    if not caller_role or caller_role in {"user", "antigravity"}:
        caller_role = "main_agent"
    caller_name = req_agent_name if (req_agent_name and req_agent_name != "Antigravity") else ("هماهنگ‌کننده اصلی" if caller_role == "main_agent" else resolve_role_title(caller_role))

    def _record_hook_interaction(msg_id: str, to_role: str, to_name: str, summary: str, action: str, child_cid: Optional[str]) -> Optional[dict[str, Any]]:
        if not to_role or to_role == caller_role or to_role in {"user", "subagent"} or not has_thinktank_activity(conv):
            return None
        if any(isinstance(m, dict) and m.get("id") == msg_id for m in conv.get("messages") or []):
            return None
        return append_message(conv, {
            "id": msg_id, "channel": "SUBAGENTS",
            "senderCode": caller_role.upper(), "senderName": caller_name, "senderRole": caller_role,
            "recipientCode": to_role.upper(), "recipientName": to_name or to_role, "recipientRole": to_role,
            "timestamp": hms, "createdAtMs": ts_ms, "content": summary,
            "origin": "subagent" if mapped else "main-proxy",
            "subagentConvId": child_cid or raw_cid, "convId": cid,
        }, action_type=action)

    if not is_closed:
        if mapped_role and mapped_role not in {"user", "subagent"}:
            was_known = any(normalize_agent_id(a.get("id", "")) == mapped_role and a.get("verifiedSubagent") for a in conv.get("agents") or [])
            changed = upsert_agent_state(
                conv, mapped_role,
                name=req_agent_name if (req_agent_name and req_agent_name != "Antigravity") else None,
                tool=tool_name, status="WORKING",
                subagent_conv_id=raw_cid, verified_subagent=True, increment_turn=True,
            )
            agent_updated |= changed
            if changed and not was_known:
                durable_agent_event = True
        else:
            ag_target = normalize_agent_id(req_agent_id or "main_agent")
            if ag_target and ag_target != "user":
                agent_updated |= upsert_agent_state(conv, ag_target, name=req_agent_name, tool=tool_name, status="ACTIVE")

        args = req.get("args") or {}
        if tool_name.endswith("invoke_subagent"):
            durable_agent_event = True
            type_name = str(args.get("TypeName") or args.get("typeName") or args.get("type_name") or "").strip()
            role_desc = str(args.get("Role") or args.get("role") or args.get("Description") or "").strip()
            role_id = normalize_agent_id(type_name) or normalize_agent_id(role_desc)
            if len(role_id) > 48 and " " in role_id:
                role_id = ""
            uuid_matches = re.findall(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", str(req.get("output") or ""), re.IGNORECASE)
            spawned_cid = next((u for u in uuid_matches if u.lower() not in {cid.lower(), raw_cid.lower()}), None)
            if spawned_cid and role_id and role_id != "user":
                session_resolver.subagent_session_map[spawned_cid] = {"parentConvId": cid, "roleId": role_id, "roleTitle": role_desc}
                save_subagent_link(spawned_cid, cid, role_id, role_desc or None, store=session_resolver.store)
                if spawned_cid in conversations_store and is_phantom_child_conv(conversations_store[spawned_cid]):
                    conversations_store.pop(spawned_cid, None)
                    session_resolver.store.delete_conversation(spawned_cid)
                agent_updated |= upsert_agent_state(
                    conv, role_id, task=role_desc or None, tool="invoke_subagent", status="WORKING",
                    subagent_conv_id=spawned_cid, verified_subagent=True, increment_turn=True,
                )
            elif role_id and role_id != "user":
                session_resolver.pending_subagent_invokes.setdefault(cid, []).append({"roleId": role_id, "roleTitle": role_desc, "ts": time.time()})
                agent_updated |= upsert_agent_state(
                    conv, role_id, task=role_desc or None, tool="invoke_subagent", status="WORKING", increment_turn=True,
                )
            if role_id and role_id != "user":
                auto_collab_msg = _record_hook_interaction(
                    f"hook-delegate-{req.get('id')}", role_id, role_desc or role_id,
                    f"واگذاری اجرا به زیرعامل {role_desc or role_id}", "DELEGATE", spawned_cid,
                )
        elif tool_name.endswith("send_message"):
            recip_cid = str(args.get("Recipient") or args.get("recipient") or "").strip()
            if recip_cid:
                recip_info = session_resolver.ensure_subagent_mapping(recip_cid, conversations_store, is_phantom_child_conv)
                recip_role = recip_info.get("roleId") if recip_info else None
                if not recip_role:
                    direct_role = normalize_agent_id(recip_cid)
                    if direct_role in CANONICAL_ROLES:
                        recip_role = direct_role
                if recip_role and recip_role not in {"user", "subagent"}:
                    durable_agent_event = True
                    agent_updated |= upsert_agent_state(
                        conv, recip_role, tool="send_message", status="WORKING",
                        subagent_conv_id=recip_cid if recip_info else None,
                        verified_subagent=bool(recip_info), increment_turn=True,
                    )
                    auto_collab_msg = _record_hook_interaction(
                        f"hook-msg-{req.get('id')}", recip_role,
                        (recip_info or {}).get("roleTitle") or resolve_role_title(recip_role),
                        f"ارسال پیام / ادامه کار با {recip_role}", "DELEGATE", recip_cid,
                    )

    return {
        "duplicate": False, "convId": cid, "entry": entry,
        "autoCollabMsg": auto_collab_msg, "agentUpdated": agent_updated,
        "durableAgentEvent": durable_agent_event, "callerRole": caller_role, "toolName": tool_name,
    }


def build_conv_row(cid: str, c: dict[str, Any], target_cid: str) -> dict[str, Any]:
    tt = c.get("thinkTank") or {}
    updated_s = get_conv_sort_ts(c)
    updated_ms = int(c.get("updatedAtMs") or (updated_s * 1000.0 if updated_s > 0 else 0))
    is_current = cid == target_cid
    p_name = tt.get("project") or ("مکالمه جاری" if is_current else "اتاق فکر بدون عنوان")
    is_closed = bool(tt.get("isClosed")) or str(tt.get("status") or "").upper() in {"COMPLETED", "DONE", "CLOSED"}
    return {
        "id": cid,
        "isCurrent": is_current,
        "projectScope": "bound" if c.get("projectId") else "unassigned",
        "workspaceUri": c.get("workspaceUri"),
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
        "messagesCount": len(c.get("messages") or []),
        "subtasksCount": len(c.get("subtasks") or []),
        "updated_at": c.get("updated_at") or updated_s,
        "updatedAtMs": updated_ms,
    }


def build_conversations_list(
    conversations_store: dict[str, dict[str, Any]],
    target_cid: str,
    *,
    subagent_map: Optional[dict[str, Any]] = None,
    include_target_if_in_store: bool = False,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for cid, c in sorted(conversations_store.items(), key=lambda item: get_conv_sort_ts(item[1]), reverse=True):
        if cid == "default" or not is_meaningful_conversation(cid, c, target_cid, subagent_map=subagent_map):
            continue
        rows.append(build_conv_row(cid, c, target_cid))
    curr_idx = next((i for i, r in enumerate(rows) if r["id"] == target_cid), None)
    if curr_idx is not None and curr_idx > 0:
        c_item = rows.pop(curr_idx)
        c_item["isCurrent"] = True
        rows.insert(0, c_item)
    elif curr_idx is None and target_cid in conversations_store:
        if not include_target_if_in_store or is_meaningful_conversation(target_cid, conversations_store[target_cid], target_cid, subagent_map=subagent_map):
            rows.insert(0, build_conv_row(target_cid, conversations_store[target_cid], target_cid))
    return rows


def build_status_snapshot(
    cid: str,
    conv: dict[str, Any],
    conversations_list: list[dict[str, Any]],
    cursor: dict[str, Any],
) -> dict[str, Any]:
    imported_snapshot = cursor.get("last_event_type") == "SNAPSHOT_IMPORTED"
    state_age_seconds = max(0.0, time.time() - float(cursor.get("updated_at") or time.time()))
    freshness = "imported_snapshot" if imported_snapshot else ("empty" if int(cursor.get("seq") or 0) == 0 else "updated")
    pstate = sync_pipeline_fields(conv)
    return {
        "convId": cid,
        "parentConvId": conv.get("parentConvId") or cid.split("--run-")[0],
        "workspaceUri": conv.get("workspaceUri"),
        "projectId": conv.get("projectId"),
        "hasSession": pstate["hasSession"],
        "pipelineStage": pstate["pipelineStage"],
        "isClosed": pstate["isClosed"],
        "updatedAtMs": int(conv.get("updatedAtMs") or now_ms()),
        "thinkTank": conv["thinkTank"],
        "agents": conv["agents"],
        "subtasks": conv.get("subtasks", []),
        "fileLocks": conv.get("fileLocks", []),
        "findings": conv.get("findings", []),
        "messages": conv.get("messages", []),
        "interactions": conv.get("interactions", []),
        "graph": build_interaction_graph(conv),
        "proposal": conv.get("proposal"),
        "review": conv.get("review"),
        "telemetry": conv.get("telemetry", {"toolCalls": [], "terminalLogs": [], "backgroundTasks": []}),
        "collaborations": conv.get("collaborations", []),
        "originCounts": compute_origin_counts(conv),
        "roleUsage": role_usage(conv.get("messages", [])),
        "closureReceipt": (conv.get("thinkTank") or {}).get("closureReceipt"),
        "conversationsList": conversations_list,
        "sync": cursor,
        "serverTime": now_hms(),
        "stateFreshness": freshness,
        "stateAgeSeconds": int(state_age_seconds),
        "syncMode": "durable-websocket",
        "schemaVersion": "4.0",
    }
