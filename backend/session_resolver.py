"""Brain transcript parent discovery, safe atomic JSON I/O, and hysteretic workspace binding."""

from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

try:
    from .catalog import normalize_agent_id, normalize_workspace_uri
except ImportError:
    from catalog import normalize_agent_id, normalize_workspace_uri

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
HEAD_SCAN_BYTES = 16 * 1024
TAIL_SCAN_BYTES = 512 * 1024
MAX_CANDIDATE_TRANSCRIPTS = 12


def resolve_session_file() -> Path:
    explicit = os.environ.get("THINKTANK_SESSION_FILE", "").strip()
    if explicit:
        return Path(explicit)
    base = os.environ.get("THINKTANK_HOME", "").strip()
    root = Path(base) if base else (Path.home() / ".gemini" / "config")
    return root / "active_antigravity_session.json"


def resolve_subagent_links_file() -> Path:
    return resolve_session_file().with_name("subagent_links.json")


def resolve_brain_dir() -> Path:
    explicit = os.environ.get("THINKTANK_ANTIGRAVITY_BRAIN_DIR", "").strip()
    if explicit:
        return Path(explicit)
    return Path.home() / ".gemini" / "antigravity" / "brain"


def read_json_dict(path: str | Path) -> dict[str, Any]:
    target = Path(path) if path else None
    if not target or not target.is_file():
        return {}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def write_json_atomic(path: str | Path, data: dict[str, Any]) -> bool:
    if not path:
        return False
    target = Path(path)
    tmp = target.with_name(f"{target.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        for attempt in range(3):
            try:
                os.replace(tmp, target)
                return True
            except PermissionError:
                if attempt < 2:
                    time.sleep(0.015)
            except OSError:
                if attempt < 2:
                    time.sleep(0.015)
        return False
    except Exception:
        return False
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def extract_role_from_tail(tail_text: str, child_cid: str) -> tuple[bool, Optional[str], Optional[str]]:
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


def save_subagent_link(child_cid: str, parent_cid: str, role_id: Optional[str], role_title: Optional[str], store: Any = None) -> None:
    if not child_cid or not parent_cid or child_cid == parent_cid or "--run-" in child_cid:
        return
    if store is not None:
        store.upsert_subagent_link(child_cid, parent_cid, role_id, role_title)
    links_file = resolve_subagent_links_file()
    links = read_json_dict(links_file)
    links[child_cid] = {"parentConversationId": parent_cid, "roleId": role_id, "roleTitle": role_title}
    write_json_atomic(links_file, links)


def discover_parent_from_brain(
    child_cid: str,
    *,
    subagent_map: Optional[dict[str, dict[str, Any]]] = None,
    store: Any = None,
    non_child_check: Optional[Callable[[str], bool]] = None,
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    if not child_cid or not isinstance(child_cid, str) or child_cid == "default" or "--run-" in child_cid:
        return None, None, None
    if non_child_check and non_child_check(child_cid):
        return None, None, None

    if subagent_map and child_cid in subagent_map:
        m = subagent_map[child_cid]
        if m.get("parentConvId") and m["parentConvId"] != child_cid:
            return m["parentConvId"], m.get("roleId") or None, m.get("roleTitle") or None

    links_file = resolve_subagent_links_file()
    links = read_json_dict(links_file)
    cached = links.get(child_cid)
    if isinstance(cached, dict):
        cp = str(cached.get("parentConversationId") or cached.get("parentConvId") or "").strip()
        if cp and cp != child_cid:
            return cp, cached.get("roleId") or None, cached.get("roleTitle") or None

    brain_dir = resolve_brain_dir()
    if not brain_dir.is_dir():
        return None, None, None

    child_tpath = brain_dir / child_cid / ".system_generated" / "logs" / "transcript.jsonl"
    if child_tpath.is_file():
        try:
            with child_tpath.open("rb") as fp_c:
                head = fp_c.read(HEAD_SCAN_BYTES).decode("utf-8", errors="ignore")
            if '"USER_EXPLICIT"' in head or '"USER_INPUT"' in head:
                return None, None, None
        except Exception:
            pass

    candidates: list[Path] = []
    seen_dirs: set[str] = {child_cid}
    sess_data = read_json_dict(resolve_session_file())
    sess_cid = str(sess_data.get("conversationId") or "").strip()
    if sess_cid and sess_cid not in seen_dirs and sess_cid not in links and not (subagent_map and sess_cid in subagent_map):
        st = brain_dir / sess_cid / ".system_generated" / "logs" / "transcript.jsonl"
        if st.is_file():
            candidates.append(st)
            seen_dirs.add(sess_cid)

    recent: list[tuple[float, Path]] = []
    try:
        for entry in brain_dir.iterdir():
            if not entry.is_dir() or entry.name in seen_dirs:
                continue
            tp = entry / ".system_generated" / "logs" / "transcript.jsonl"
            if tp.is_file():
                try:
                    recent.append((tp.stat().st_mtime, tp))
                except OSError:
                    continue
    except OSError:
        return None, None, None

    recent.sort(key=lambda item: item[0], reverse=True)
    for _, tp in recent[:MAX_CANDIDATE_TRANSCRIPTS]:
        candidates.append(tp)

    for cand_path in candidates:
        parent_cid = cand_path.parent.parent.parent.name
        if not parent_cid or parent_cid == child_cid:
            continue
        try:
            size = cand_path.stat().st_size
            with cand_path.open("rb") as fp_p:
                fp_p.seek(max(0, size - TAIL_SCAN_BYTES))
                tail_text = fp_p.read().decode("utf-8", errors="ignore")
        except Exception:
            continue
        if child_cid not in tail_text:
            continue
        matched, role_id, role_title = extract_role_from_tail(tail_text, child_cid)
        if not matched:
            continue
        save_subagent_link(child_cid, parent_cid, role_id, role_title, store=store)
        return parent_cid, role_id, role_title
    return None, None, None


class SessionResolver:
    """Coordinate child-to-parent subagent links and hysteretic workspace session resolution."""

    def __init__(self, store: Any) -> None:
        self.store = store
        self.subagent_session_map: dict[str, dict[str, Any]] = {}
        self.pending_subagent_invokes: dict[str, list[dict[str, Any]]] = {}
        self.sessions_by_workspace: dict[str, dict[str, Any]] = {}
        self.negative_child_cache: dict[str, float] = {}
        self.active_conv_id: str = "default"
        self.active_conv_workspace_uri: Optional[str] = None

    def is_non_child(self, cid: str, conversations_store: dict[str, dict[str, Any]], is_phantom_fn: Callable[[Any], bool]) -> bool:
        if not cid or cid == "default" or "--run-" in cid:
            return True
        if cid in conversations_store and not is_phantom_fn(conversations_store[cid]):
            return True
        cached_ts = self.negative_child_cache.get(cid)
        if cached_ts is not None and (time.time() - cached_ts) < 60.0:
            return True
        return False

    def ensure_subagent_mapping(
        self,
        raw_cid: Optional[str],
        conversations_store: dict[str, dict[str, Any]],
        is_phantom_fn: Callable[[Any], bool],
        *,
        parent_cid: Optional[str] = None,
        role_id: Optional[str] = None,
        role_title: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        clean_cid = (raw_cid or "").strip()
        if not clean_cid or clean_cid == "default" or "--run-" in clean_cid:
            return None
        explicit_parent = (parent_cid or "").strip() or None
        if explicit_parent == clean_cid:
            explicit_parent = None
        if not explicit_parent and clean_cid in conversations_store and not is_phantom_fn(conversations_store[clean_cid]):
            self.subagent_session_map.pop(clean_cid, None)
            self.store.delete_subagent_link(clean_cid)
            return None

        norm_role = normalize_agent_id(role_id) if role_id else ""
        if len(norm_role) > 48 and " " in norm_role:
            norm_role = ""
        clean_title = (role_title or "").strip() or None

        existing = self.subagent_session_map.get(clean_cid)
        if existing:
            if norm_role and existing.get("roleId") in {"", None, "subagent"}:
                existing["roleId"] = norm_role
                save_subagent_link(clean_cid, existing["parentConvId"], norm_role, clean_title or existing.get("roleTitle"), store=self.store)
            if clean_title and not existing.get("roleTitle"):
                existing["roleTitle"] = clean_title
            if clean_cid in conversations_store and is_phantom_fn(conversations_store[clean_cid]):
                conversations_store.pop(clean_cid, None)
                self.store.delete_conversation(clean_cid)
            return existing

        if not explicit_parent:
            dp, dr, dt = discover_parent_from_brain(
                clean_cid,
                subagent_map=self.subagent_session_map,
                store=self.store,
                non_child_check=lambda cid: self.is_non_child(cid, conversations_store, is_phantom_fn),
            )
            if dp and dp != clean_cid:
                explicit_parent = dp
                norm_role = norm_role or (normalize_agent_id(dr) if dr else "")
                clean_title = clean_title or dt

        if not explicit_parent:
            self.negative_child_cache[clean_cid] = time.time()
            return None
        if explicit_parent in self.subagent_session_map:
            explicit_parent = self.subagent_session_map[explicit_parent]["parentConvId"]

        if not norm_role:
            pending_list = self.pending_subagent_invokes.get(explicit_parent)
            if pending_list:
                now_ts = time.time()
                pending_list[:] = [p for p in pending_list if now_ts - float(p.get("ts") or 0) <= 120.0]
                if pending_list:
                    picked = pending_list.pop(0)
                    norm_role = normalize_agent_id(picked.get("roleId"))
                    clean_title = clean_title or picked.get("roleTitle") or None

        entry = {"parentConvId": explicit_parent, "roleId": norm_role or "subagent", "roleTitle": clean_title or ""}
        self.subagent_session_map[clean_cid] = entry
        save_subagent_link(clean_cid, explicit_parent, entry["roleId"] if entry["roleId"] != "subagent" else None, clean_title, store=self.store)
        if clean_cid in conversations_store and is_phantom_fn(conversations_store[clean_cid]):
            conversations_store.pop(clean_cid, None)
            self.store.delete_conversation(clean_cid)
        return entry

    def refresh_from_session_file(
        self,
        conversations_store: dict[str, dict[str, Any]],
        has_activity_fn: Callable[[Any], bool],
        is_unclosed_fn: Callable[[Any], bool],
        is_phantom_fn: Callable[[Any], bool],
    ) -> None:
        sdata = read_json_dict(resolve_session_file())
        if not sdata:
            return
        raw_ws_map = sdata.get("sessionsByWorkspace")
        if isinstance(raw_ws_map, dict):
            for ws_k, ws_info in raw_ws_map.items():
                norm_k = normalize_workspace_uri(ws_k)
                if not norm_k or not isinstance(ws_info, dict):
                    continue
                ws_cid = str(ws_info.get("conversationId") or "").strip()
                if not ws_cid:
                    continue
                mapped_ws = self.ensure_subagent_mapping(ws_cid, conversations_store, is_phantom_fn)
                resolved_ws_cid = mapped_ws["parentConvId"] if mapped_ws else ws_cid
                existing_entry = self.sessions_by_workspace.get(norm_k) or {}
                existing_cid = str(existing_entry.get("conversationId") or "").strip()
                existing_unclosed = existing_cid in conversations_store and is_unclosed_fn(conversations_store[existing_cid])
                cand_has_tt = resolved_ws_cid in conversations_store and has_activity_fn(conversations_store[resolved_ws_cid])
                if existing_unclosed and not cand_has_tt and existing_cid != resolved_ws_cid:
                    continue
                prev_ts = float(existing_entry.get("timestamp") or 0.0)
                cand_ts = float(ws_info.get("timestamp") or 0.0)
                if norm_k not in self.sessions_by_workspace or cand_ts >= prev_ts:
                    self.sessions_by_workspace[norm_k] = {
                        "conversationId": resolved_ws_cid,
                        "projectId": ws_info.get("projectId"),
                        "timestamp": cand_ts,
                    }
        raw_cid = str(sdata.get("conversationId") or "").strip()
        if raw_cid:
            mapped = self.ensure_subagent_mapping(raw_cid, conversations_store, is_phantom_fn)
            cand_cid = mapped["parentConvId"] if mapped else raw_cid
            curr_conv = conversations_store.get(self.active_conv_id)
            cand_conv = conversations_store.get(cand_cid)
            if not (is_unclosed_fn(curr_conv) and not has_activity_fn(cand_conv) and self.active_conv_id != cand_cid):
                self.active_conv_id = cand_cid
                self.active_conv_workspace_uri = normalize_workspace_uri(sdata.get("workspaceUri"))

    def resolve_workspace_conv_id(
        self,
        workspace_uri: Optional[str],
        conversations_store: dict[str, dict[str, Any]],
        has_activity_fn: Callable[[Any], bool],
        is_unclosed_fn: Callable[[Any], bool],
        sort_ts_fn: Callable[[dict[str, Any]], float],
    ) -> Optional[str]:
        norm_ws = normalize_workspace_uri(workspace_uri)
        if not norm_ws:
            return None
        ws_candidates = [
            (cid, c) for cid, c in conversations_store.items()
            if cid != "default"
            and "--run-" not in cid
            and not c.get("isArchivedRun")
            and normalize_workspace_uri(c.get("workspaceUri")) == norm_ws
            and has_activity_fn(c)
        ]
        ws_entry = self.sessions_by_workspace.get(norm_ws)
        if ws_entry and ws_entry.get("conversationId"):
            mapped_cid = str(ws_entry["conversationId"])
            if "--run-" not in mapped_cid and mapped_cid in conversations_store and is_unclosed_fn(conversations_store[mapped_cid]):
                return mapped_cid
        if ws_candidates:
            ws_candidates.sort(key=lambda kv: (0 if is_unclosed_fn(kv[1]) else 1, -sort_ts_fn(kv[1])))
            return ws_candidates[0][0]
        if ws_entry and ws_entry.get("conversationId"):
            mapped_cid = str(ws_entry["conversationId"])
            if "--run-" not in mapped_cid:
                return mapped_cid
        return None

    def resolve_for_workspace(
        self,
        workspace_uri: Optional[str],
        conversations_store: dict[str, dict[str, Any]],
        has_activity_fn: Callable[[Any], bool],
        is_unclosed_fn: Callable[[Any], bool],
        is_phantom_fn: Callable[[Any], bool],
        sort_ts_fn: Callable[[dict[str, Any]], float],
    ) -> tuple[str, bool, Optional[str]]:
        self.refresh_from_session_file(conversations_store, has_activity_fn, is_unclosed_fn, is_phantom_fn)
        norm_ws = normalize_workspace_uri(workspace_uri)
        if norm_ws:
            ws_cid = self.resolve_workspace_conv_id(norm_ws, conversations_store, has_activity_fn, is_unclosed_fn, sort_ts_fn)
            if ws_cid:
                return ws_cid, True, norm_ws
            file_ws = normalize_workspace_uri(read_json_dict(resolve_session_file()).get("workspaceUri"))
            active_ws = normalize_workspace_uri(
                (conversations_store.get(self.active_conv_id) or {}).get("workspaceUri")
                or self.active_conv_workspace_uri
                or file_ws
            )
            if active_ws and active_ws != norm_ws:
                return "", False, norm_ws
            if self.active_conv_id and self.active_conv_id != "default" and not active_ws:
                return self.active_conv_id, True, norm_ws
            return "", False, norm_ws
        return self.active_conv_id, True, None
