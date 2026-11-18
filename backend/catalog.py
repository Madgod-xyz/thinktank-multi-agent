"""Canonical 7+1 role catalog, unified alias map, URI normalizer, and request types."""

from __future__ import annotations

import json
import os
import re
import urllib.parse
from pathlib import Path
from typing import Any, Optional

CANONICAL_ROLES: tuple[str, ...] = (
    "main_agent",
    "team-manager",
    "council-critic",
    "code-reviewer",
    "qa-reviewer",
    "ui-frontend-designer",
    "backend-auditor",
    "ecommerce_seo_operator",
    "wp_technical_operator",
)

UNDERSCORE_ROLES: frozenset[str] = frozenset({
    "main_agent",
    "ecommerce_seo_operator",
    "wp_technical_operator",
})

OPERATOR_ALIASES: frozenset[str] = frozenset({
    "user",
    "human",
    "operator",
    "owner",
    "usr",
})

ROLE_ALIAS_MAP: dict[str, str] = {
    "main": "main_agent",
    "root": "main_agent",
    "coordinator": "main_agent",
    "main-agent": "main_agent",
    "main_agent": "main_agent",
    "orchestrator": "main_agent",
    "antigravity": "main_agent",
    "عامل اصلی": "main_agent",
    "manager": "team-manager",
    "team_manager": "team-manager",
    "team-manager": "team-manager",
    "council-architect": "team-manager",
    "council_architect": "team-manager",
    "requirements-auditor": "team-manager",
    "context-memory-curator": "team-manager",
    "data-intelligence-curator": "team-manager",
    "performance-cost-analyst": "team-manager",
    "skill-coach": "team-manager",
    "مدیر تیم": "team-manager",
    "critic": "council-critic",
    "council_critic": "council-critic",
    "council-critic": "council-critic",
    "evidence-critical-reviewer": "council-critic",
    "agent-evaluator": "council-critic",
    "نقاد شورا": "council-critic",
    "reviewer": "code-reviewer",
    "code_reviewer": "code-reviewer",
    "code-reviewer": "code-reviewer",
    "integration-reviewer": "code-reviewer",
    "integration_reviewer": "code-reviewer",
    "security_reviewer": "code-reviewer",
    "کد ریویور": "code-reviewer",
    "qa": "qa-reviewer",
    "qa_reviewer": "qa-reviewer",
    "qa-reviewer": "qa-reviewer",
    "tester": "qa-reviewer",
    "visual-qa": "qa-reviewer",
    "flutter_a11y_agent": "qa-reviewer",
    "تستر qa": "qa-reviewer",
    "designer": "ui-frontend-designer",
    "designer_solver": "ui-frontend-designer",
    "ui_frontend_designer": "ui-frontend-designer",
    "ui-frontend-designer": "ui-frontend-designer",
    "motion-director": "ui-frontend-designer",
    "طراح رابط": "ui-frontend-designer",
    "backend": "backend-auditor",
    "backend_auditor": "backend-auditor",
    "backend-auditor": "backend-auditor",
    "backend_engineer": "backend-auditor",
    "implementer": "backend-auditor",
    "deep-researcher": "backend-auditor",
    "research-scout": "backend-auditor",
    "متخصص بک‌اند": "backend-auditor",
    "seo": "ecommerce_seo_operator",
    "seo_specialist": "ecommerce_seo_operator",
    "ecommerce-seo-operator": "ecommerce_seo_operator",
    "ecommerce_seo_operator": "ecommerce_seo_operator",
    "متخصص سئو": "ecommerce_seo_operator",
    "wp": "wp_technical_operator",
    "wordpress": "wp_technical_operator",
    "woocommerce": "wp_technical_operator",
    "wp-technical-operator": "wp_technical_operator",
    "wp_technical_operator": "wp_technical_operator",
    "متخصص ووکامرس": "wp_technical_operator",
}

VALID_REQUEST_TYPES: frozenset[str] = frozenset({
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
})

ACTION_REQUEST_TYPE_MAP: dict[str, str] = {
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
    "VOTE": "DECISION",
    "PROPOSAL": "DECISION",
    "COMPLETE": "DECISION",
    "GOVERNANCE": "DECISION",
    "MESSAGE": "MESSAGE",
}

ROLE_CATALOG_FILE = Path(__file__).resolve().with_name("role_catalog.json")
_CATALOG_CACHE: Optional[tuple[float, list[dict[str, Any]]]] = None


def load_role_catalog() -> list[dict[str, Any]]:
    global _CATALOG_CACHE
    if ROLE_CATALOG_FILE.is_file():
        try:
            mtime = ROLE_CATALOG_FILE.stat().st_mtime
            if _CATALOG_CACHE and _CATALOG_CACHE[0] == mtime:
                return _CATALOG_CACHE[1]
            raw = json.loads(ROLE_CATALOG_FILE.read_text(encoding="utf-8"))
            roles = raw if isinstance(raw, list) else list(raw.get("roles", []))
            for item in roles:
                if not isinstance(item, dict) or not item.get("id"):
                    continue
                cid = str(item["id"]).strip()
                ROLE_ALIAS_MAP.setdefault(cid.lower(), cid)
                if item.get("monogram"):
                    ROLE_ALIAS_MAP.setdefault(str(item["monogram"]).strip().lower(), cid)
                for alias in item.get("aliases") or []:
                    if isinstance(alias, str) and alias.strip():
                        ROLE_ALIAS_MAP.setdefault(alias.strip().lower(), cid)
            _CATALOG_CACHE = (mtime, roles)
            return roles
        except Exception:
            pass
    return []


def normalize_agent_id(raw_id: Optional[str]) -> str:
    if not raw_id or not isinstance(raw_id, str):
        return ""
    load_role_catalog()
    clean = re.sub(r"^(?:(?:agent|tt)[_-])+", "", raw_id.strip().lower())
    if not clean:
        return ""
    if clean in ROLE_ALIAS_MAP:
        return ROLE_ALIAS_MAP[clean]
    dashed = clean.replace("_", "-")
    if dashed in ROLE_ALIAS_MAP:
        return ROLE_ALIAS_MAP[dashed]
    m = re.match(r"^sub(?:agent)?[_-]?(\d+)$", clean)
    if m:
        return f"subagent_{m.group(1)}"
    if "_" in clean and clean not in UNDERSCORE_ROLES:
        return dashed
    return clean


def find_role_entry(role_id: Optional[str]) -> Optional[dict[str, Any]]:
    norm = normalize_agent_id(role_id)
    if not norm:
        return None
    for item in load_role_catalog():
        if normalize_agent_id(item.get("id")) == norm:
            return item
    return None


def resolve_role_title(role_id: Optional[str], fallback: Optional[str] = None) -> str:
    norm = normalize_agent_id(role_id)
    entry = find_role_entry(norm)
    if fallback and fallback.strip() and fallback.strip().lower() not in {norm, "antigravity", ""}:
        return fallback.strip()
    if entry and entry.get("title"):
        return str(entry["title"])
    return (fallback or norm or "agent").strip()


def normalize_workspace_uri(raw: Any) -> Optional[str]:
    if isinstance(raw, (list, tuple)):
        for item in raw:
            norm = normalize_workspace_uri(item)
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
        val = val.lower()
    return val or None


def infer_request_type(action_upper: str, explicit: Optional[str] = None) -> str:
    clean = str(explicit or "").strip().upper()
    if clean in VALID_REQUEST_TYPES:
        return clean
    return ACTION_REQUEST_TYPE_MAP.get(str(action_upper or "MESSAGE").strip().upper(), "MESSAGE")


def extract_mentions_and_citations(text: str) -> tuple[list[str], list[int]]:
    if not isinstance(text, str) or not text:
        return [], []
    mentions: list[str] = []
    for raw in re.findall(r"@([A-Za-z0-9_\u0600-\u06FF-]+)", text):
        norm = normalize_agent_id(raw)
        if norm and norm not in mentions:
            mentions.append(norm)
    citations: list[int] = []
    for num in re.findall(r"#(\d+)\b", text):
        try:
            seq_val = int(num)
            if seq_val > 0 and seq_val not in citations:
                citations.append(seq_val)
        except ValueError:
            pass
    return mentions, citations
