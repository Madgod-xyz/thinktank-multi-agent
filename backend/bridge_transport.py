"""Verified HTTP transport and durable offline outbox for ThinkTank v4.0 events."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from contextlib import closing
from pathlib import Path
from typing import Any, Optional

API_BASE = os.environ.get("THINKTANK_API_BASE", "http://127.0.0.1:8780/api").rstrip("/")
API_PORT = int(os.environ.get("THINKTANK_PORT") or urllib.parse.urlsplit(API_BASE).port or 8780)
CONFIG_DIR = Path(os.environ.get("THINKTANK_HOME") or (Path.home() / ".gemini" / "config")).expanduser()
OUTBOX_DB = Path(os.environ.get("THINKTANK_OUTBOX_DB", CONFIG_DIR / "think_tank_outbox.sqlite3"))

_SIBLING_BACKEND = Path(__file__).resolve().parent.parent / "backend"
_GLOBAL_BACKEND = CONFIG_DIR / "thinktank" / "backend"
_DEFAULT_BACKEND = _SIBLING_BACKEND if (_SIBLING_BACKEND / "app.py").is_file() else _GLOBAL_BACKEND
BACKEND_DIR = Path(os.environ.get("THINKTANK_BACKEND_DIR", _DEFAULT_BACKEND)).expanduser()


def _request(url: str, *, data: Optional[dict[str, Any]] = None, event_id: Optional[str] = None, timeout: float = 6.0) -> dict[str, Any]:
    body = None if data is None else json.dumps(data, ensure_ascii=False).encode("utf-8")
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if event_id:
        headers["X-ThinkTank-Event-Id"] = event_id
    req = urllib.request.Request(url, data=body, headers=headers, method="POST" if body is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
        return json.loads(raw) if raw else {"status": "ok"}


def _health_check(timeout: float = 2.0) -> bool:
    for path in ("health", "status"):
        try:
            result = _request(f"{API_BASE}/{path}", timeout=timeout)
            if isinstance(result, dict) and result.get("syncMode") == "durable-websocket" and bool(
                result.get("ok") or (result.get("sync") or {}).get("generation")
            ):
                return True
        except Exception:
            continue
    return False


def ensure_backend_running() -> bool:
    if _health_check():
        return True
    if os.environ.get("THINKTANK_AUTO_START", "1").lower() in {"0", "false", "no"}:
        return False
    if not BACKEND_DIR.is_dir():
        return False
    flags = 0
    if sys.platform == "win32":
        flags = getattr(subprocess, "DETACHED_PROCESS", 0x00000008) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
    try:
        subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", str(API_PORT)],
            cwd=str(BACKEND_DIR), stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
    except Exception:
        return False
    deadline = time.monotonic() + 4.0
    while time.monotonic() < deadline:
        if _health_check(timeout=1.5):
            return True
        time.sleep(0.15)
    return False


def _connect_outbox(timeout: float = 5.0) -> sqlite3.Connection:
    OUTBOX_DB.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(OUTBOX_DB), timeout=timeout)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=FULL")
    db.execute(
        "CREATE TABLE IF NOT EXISTS outbox (event_id TEXT PRIMARY KEY, endpoint TEXT NOT NULL, data_json TEXT NOT NULL, created_at REAL NOT NULL)"
    )
    return db


def outbox_queue_count() -> int:
    if not OUTBOX_DB.is_file():
        return 0
    try:
        with closing(_connect_outbox(timeout=1.0)) as db:
            row = db.execute("SELECT COUNT(*) FROM outbox").fetchone()
            return int(row[0]) if row else 0
    except Exception:
        return 0


def _enqueue(endpoint: str, data: dict[str, Any], event_id: str, *, db_timeout: float = 5.0) -> dict[str, Any]:
    with closing(_connect_outbox(timeout=db_timeout)) as db:
        with db:
            db.execute(
                "INSERT OR IGNORE INTO outbox (event_id, endpoint, data_json, created_at) VALUES (?, ?, ?, ?)",
                (event_id, endpoint, json.dumps(data, ensure_ascii=False), time.time()),
            )
    return {"status": "queued_offline", "eventId": event_id, "error": "Backend unavailable; event saved to durable outbox."}


def _delete_outbox_event(event_id: str, *, db_timeout: float = 5.0) -> None:
    with closing(_connect_outbox(timeout=db_timeout)) as db:
        with db:
            db.execute("DELETE FROM outbox WHERE event_id = ?", (event_id,))


def flush_outbox_fast(*, max_events: int = 2, timeout: float = 0.2) -> bool:
    if max_events <= 0 or not OUTBOX_DB.is_file():
        return True
    db_timeout = min(max(timeout, 0.05), 0.25)
    with closing(_connect_outbox(timeout=db_timeout)) as db:
        rows = db.execute(
            "SELECT event_id, endpoint, data_json FROM outbox ORDER BY created_at, event_id LIMIT ?",
            (max_events,),
        ).fetchall()
    for event_id, endpoint, data_json in rows:
        try:
            _request(f"{API_BASE}/{endpoint.lstrip('/')}", data=json.loads(data_json), event_id=event_id, timeout=timeout)
        except urllib.error.HTTPError as error:
            if 400 <= error.code < 500:
                _delete_outbox_event(event_id, db_timeout=db_timeout)
                continue
            return False
        except Exception:
            return False
        _delete_outbox_event(event_id, db_timeout=db_timeout)
    return True


def api_post_fast(endpoint: str, data: dict[str, Any], conv_id: Optional[str] = None, *, event_id: Optional[str] = None, timeout: float = 0.35) -> dict[str, Any]:
    payload = dict(data)
    if conv_id:
        payload["convId"] = conv_id
    stable_event_id = str(event_id or payload.pop("eventId", None) or uuid.uuid4())
    payload.pop("eventId", None)
    db_timeout = min(max(timeout, 0.05), 0.25)
    _enqueue(endpoint, payload, stable_event_id, db_timeout=db_timeout)
    try:
        result = _request(f"{API_BASE}/{endpoint.lstrip('/')}", data=payload, event_id=stable_event_id, timeout=timeout)
    except urllib.error.HTTPError as error:
        if 400 <= error.code < 500:
            _delete_outbox_event(stable_event_id, db_timeout=db_timeout)
            return {"status": "error", "httpStatus": error.code, "error": error.read().decode("utf-8", errors="replace")}
        return {"status": "queued_offline", "eventId": stable_event_id}
    except Exception:
        return {"status": "queued_offline", "eventId": stable_event_id}
    _delete_outbox_event(stable_event_id, db_timeout=db_timeout)
    result.setdefault("eventId", stable_event_id)
    flush_outbox_fast(max_events=2, timeout=min(timeout, 0.2))
    return result


def _drain_outbox(limit: int = 10) -> bool:
    return flush_outbox_fast(max_events=limit, timeout=6.0)


def api_post(endpoint: str, data: dict[str, Any], conv_id: Optional[str] = None) -> dict[str, Any]:
    payload = dict(data)
    if conv_id:
        payload["convId"] = conv_id
    event_id = str(payload.pop("eventId", None) or uuid.uuid4())
    url = f"{API_BASE}/{endpoint.lstrip('/')}"
    for attempt in range(2):
        try:
            result = _request(url, data=payload, event_id=event_id, timeout=8.0)
            result.setdefault("eventId", event_id)
            _drain_outbox(limit=3)
            return result
        except urllib.error.HTTPError as error:
            return {"status": "error", "httpStatus": error.code, "error": error.read().decode("utf-8", errors="replace")}
        except Exception:
            if attempt == 0 and ensure_backend_running():
                continue
            return _enqueue(endpoint, payload, event_id)
    return _enqueue(endpoint, payload, event_id)


def api_get(endpoint: str, conv_id: Optional[str] = None) -> Optional[dict[str, Any]]:
    if not ensure_backend_running():
        return {"status": "offline", "syncMode": "disconnected"}
    url = f"{API_BASE}/{endpoint.lstrip('/')}" + (f"?convId={urllib.parse.quote(conv_id)}" if conv_id else "")
    try:
        return _request(url)
    except Exception:
        return {"status": "offline", "syncMode": "disconnected"}
