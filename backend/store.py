"""Single-source-of-truth SQLite WAL engine for ThinkTank v4.0."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional

try:
    from .catalog import normalize_agent_id, normalize_workspace_uri
except ImportError:
    from catalog import normalize_agent_id, normalize_workspace_uri


def _extract_conv_meta(snapshot: Any) -> tuple[Optional[str], Optional[str], int, int]:
    if not isinstance(snapshot, dict):
        return None, None, 0, 0
    ws_uri = normalize_workspace_uri(snapshot.get("workspaceUri"))
    pid = str(snapshot.get("projectId") or "").strip() or None
    tt = snapshot.get("thinkTank") if isinstance(snapshot.get("thinkTank"), dict) else {}
    has_sess = bool(
        snapshot.get("hasSession")
        or tt.get("hasSession")
        or tt.get("isClosed")
        or str(tt.get("project") or "").strip()
        or str(tt.get("directive") or "").strip()
        or snapshot.get("messages")
        or snapshot.get("subtasks")
        or snapshot.get("findings")
        or snapshot.get("proposal")
        or tt.get("triageDecision")
        or int(tt.get("runIndex") or 1) > 1
    )
    is_closed = bool(
        snapshot.get("isClosed")
        or tt.get("isClosed")
        or str(tt.get("status") or "").upper() in {"COMPLETED", "DONE", "CLOSED"}
    )
    return ws_uri, pid, (1 if has_sess else 0), (1 if is_closed else 0)


class SyncEventStore:
    """Atomically persist conversations, ordered events, subagent links, and workspace sessions."""

    def __init__(self, db_path: str, retention: int = 150) -> None:
        if retention < 1:
            raise ValueError("retention must be at least 1")
        self.db_path = str(db_path)
        self.retention = int(retention)
        self._lock = threading.RLock()
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.db_path, timeout=10.0, isolation_level=None, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=NORMAL")
        self._db.execute("PRAGMA busy_timeout=5000")
        self._db.execute("PRAGMA temp_store=MEMORY")
        self._db.execute("PRAGMA foreign_keys=ON")
        self._init_and_migrate_schema()

    def _init_and_migrate_schema(self) -> None:
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                conversation_id TEXT PRIMARY KEY,
                generation TEXT NOT NULL,
                seq INTEGER NOT NULL DEFAULT 0,
                snapshot_json TEXT NOT NULL DEFAULT '{}',
                workspace_uri TEXT,
                project_id TEXT,
                has_session INTEGER NOT NULL DEFAULT 0,
                is_closed INTEGER NOT NULL DEFAULT 0,
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
            CREATE TABLE IF NOT EXISTS subagent_links (
                child_cid TEXT PRIMARY KEY,
                parent_cid TEXT NOT NULL,
                role_id TEXT,
                role_title TEXT,
                updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS workspace_sessions (
                workspace_uri TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                project_id TEXT,
                updated_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS events_cursor_idx ON events (conversation_id, seq);
            """
        )
        cols = {row["name"] for row in self._db.execute("PRAGMA table_info(conversations)").fetchall()}
        migrated = False
        for col_name, col_def in (
            ("workspace_uri", "TEXT"),
            ("project_id", "TEXT"),
            ("has_session", "INTEGER NOT NULL DEFAULT 0"),
            ("is_closed", "INTEGER NOT NULL DEFAULT 0"),
        ):
            if col_name not in cols:
                self._db.execute(f"ALTER TABLE conversations ADD COLUMN {col_name} {col_def}")
                migrated = True
        self._db.execute("CREATE INDEX IF NOT EXISTS conversations_ws_idx ON conversations (workspace_uri, updated_at DESC)")
        if migrated:
            rows = self._db.execute("SELECT conversation_id, snapshot_json FROM conversations").fetchall()
            for r in rows:
                try:
                    snap = json.loads(r["snapshot_json"])
                except Exception:
                    continue
                ws_uri, pid, has_sess, is_closed = _extract_conv_meta(snap)
                self._db.execute(
                    "UPDATE conversations SET workspace_uri = ?, project_id = ?, has_session = ?, is_closed = ? WHERE conversation_id = ?",
                    (ws_uri, pid, has_sess, is_closed, r["conversation_id"]),
                )

    def import_legacy_files(
        self,
        *,
        state_file: Optional[str | Path] = None,
        session_file: Optional[str | Path] = None,
        links_file: Optional[str | Path] = None,
    ) -> dict[str, int]:
        stats = {"links": 0, "workspaces": 0, "conversations": 0}
        now = time.time()

        def _load_dict(p: Optional[str | Path]) -> dict[str, Any]:
            if not p:
                return {}
            path_obj = Path(p)
            if not path_obj.is_file():
                return {}
            try:
                data = json.loads(path_obj.read_text(encoding="utf-8"))
                return data if isinstance(data, dict) else {}
            except Exception:
                return {}

        with self._lock:
            links_data = _load_dict(links_file)
            state_data = _load_dict(state_file)
            sess_data = _load_dict(session_file)

            for child_cid, info in {**dict(state_data.get("subagentSessionMap") or {}), **links_data}.items():
                if not isinstance(info, dict):
                    continue
                parent_cid = str(info.get("parentConversationId") or info.get("parentConvId") or "").strip()
                if not child_cid or not parent_cid or child_cid == parent_cid or "--run-" in child_cid:
                    continue
                role_id = normalize_agent_id(info.get("roleId")) or "subagent"
                role_title = str(info.get("roleTitle") or "").strip() or None
                cur = self._db.execute(
                    "INSERT OR IGNORE INTO subagent_links (child_cid, parent_cid, role_id, role_title, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (str(child_cid).strip(), parent_cid, role_id, role_title, now),
                )
                stats["links"] += max(0, cur.rowcount)

            raw_ws = sess_data.get("sessionsByWorkspace")
            if isinstance(raw_ws, dict):
                for ws_key, ws_info in raw_ws.items():
                    norm_ws = normalize_workspace_uri(ws_key)
                    if not norm_ws or not isinstance(ws_info, dict):
                        continue
                    cid = str(ws_info.get("conversationId") or "").strip()
                    if not cid:
                        continue
                    ts = float(ws_info.get("timestamp") or now)
                    cur = self._db.execute(
                        "INSERT OR IGNORE INTO workspace_sessions (workspace_uri, conversation_id, project_id, updated_at) VALUES (?, ?, ?, ?)",
                        (norm_ws, cid, ws_info.get("projectId"), ts),
                    )
                    stats["workspaces"] += max(0, cur.rowcount)

            conv_count = int(self._db.execute("SELECT COUNT(*) FROM conversations").fetchone()[0])
            legacy_convs = state_data.get("conversations")
            if conv_count == 0 and isinstance(legacy_convs, dict) and legacy_convs:
                for cid, snap in legacy_convs.items():
                    if not cid or not isinstance(snap, dict):
                        continue
                    self.commit(
                        conversation_id=str(cid),
                        event_id=f"legacy-import-{cid}",
                        event_type="SNAPSHOT_IMPORTED",
                        payload={"source": "legacy-state"},
                        snapshot=snap,
                        source="migration",
                    )
                    stats["conversations"] += 1
        return stats

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
        row = self._db.execute("SELECT * FROM conversations WHERE conversation_id = ?", (conversation_id,)).fetchone()
        if row is None:
            now = time.time()
            self._db.execute(
                "INSERT INTO conversations (conversation_id, generation, seq, snapshot_json, updated_at) VALUES (?, ?, 0, '{}', ?)",
                (conversation_id, str(uuid.uuid4()), now),
            )
            row = self._db.execute("SELECT * FROM conversations WHERE conversation_id = ?", (conversation_id,)).fetchone()
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
            row = self._db.execute("SELECT snapshot_json FROM conversations WHERE conversation_id = ?", (conversation_id,)).fetchone()
            return json.loads(row["snapshot_json"]) if row else None

    def find_event_id(self, event_id: str) -> Optional[dict[str, Any]]:
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
        ws_uri, pid, has_sess, is_closed = _extract_conv_meta(snapshot)
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
                    "UPDATE conversations SET seq = ?, snapshot_json = ?, workspace_uri = ?, project_id = ?, has_session = ?, is_closed = ?, updated_at = ? WHERE conversation_id = ?",
                    (seq, snapshot_json, ws_uri, pid, has_sess, is_closed, now, conversation_id),
                )
                self._db.execute(
                    "INSERT INTO events (conversation_id, seq, event_id, generation, event_type, payload_json, source, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (conversation_id, seq, event_id, conv["generation"], event_type, payload_json, source, now),
                )
                self._db.execute("DELETE FROM events WHERE conversation_id = ? AND seq <= ?", (conversation_id, seq - self.retention))
                row = self._db.execute("SELECT * FROM events WHERE conversation_id = ? AND seq = ?", (conversation_id, seq)).fetchone()
                self._db.execute("COMMIT")
                return self._decode_event(row)
            except BaseException:
                self._db.execute("ROLLBACK")
                raise

    def save_snapshot_only(self, conversation_id: str, snapshot: dict[str, Any]) -> None:
        snapshot_json = self._json(snapshot)
        ws_uri, pid, has_sess, is_closed = _extract_conv_meta(snapshot)
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                self._ensure_conversation(conversation_id)
                now = time.time()
                self._db.execute(
                    "UPDATE conversations SET snapshot_json = ?, workspace_uri = ?, project_id = ?, has_session = ?, is_closed = ?, updated_at = ? WHERE conversation_id = ?",
                    (snapshot_json, ws_uri, pid, has_sess, is_closed, now, conversation_id),
                )
                self._db.execute("COMMIT")
            except BaseException:
                self._db.execute("ROLLBACK")
                raise

    def reset_conversation_events(self, conversation_id: str, snapshot: dict[str, Any]) -> str:
        """Rotate generation, reset seq to 0, and clear prior run events on --new-run."""
        new_gen = str(uuid.uuid4())
        snapshot_json = self._json(snapshot)
        ws_uri, pid, has_sess, is_closed = _extract_conv_meta(snapshot)
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                self._ensure_conversation(conversation_id)
                now = time.time()
                self._db.execute("DELETE FROM events WHERE conversation_id = ?", (conversation_id,))
                self._db.execute(
                    "UPDATE conversations SET generation = ?, seq = 0, snapshot_json = ?, workspace_uri = ?, project_id = ?, has_session = ?, is_closed = ?, updated_at = ? WHERE conversation_id = ?",
                    (new_gen, snapshot_json, ws_uri, pid, has_sess, is_closed, now, conversation_id),
                )
                self._db.execute("COMMIT")
                return new_gen
            except BaseException:
                self._db.execute("ROLLBACK")
                raise

    def delete_conversation(self, conversation_id: str) -> None:
        with self._lock:
            self._db.execute("DELETE FROM conversations WHERE conversation_id = ?", (conversation_id,))

    def replay(self, conversation_id: str, generation: str, after_seq: int) -> dict[str, Any]:
        if not isinstance(after_seq, int) or after_seq < 0:
            raise ValueError("after_seq must be a non-negative integer")
        with self._lock:
            conv = self._db.execute("SELECT generation, seq FROM conversations WHERE conversation_id = ?", (conversation_id,)).fetchone()
            if conv is None:
                return {"status": "snapshot_required", "events": []}
            bounds = self._db.execute("SELECT MIN(seq) AS first_seq FROM events WHERE conversation_id = ?", (conversation_id,)).fetchone()
            first_seq = bounds["first_seq"]
            if generation != conv["generation"] or after_seq > conv["seq"] or (first_seq is not None and after_seq < first_seq - 1):
                return {"status": "snapshot_required", "events": []}
            rows = self._db.execute("SELECT * FROM events WHERE conversation_id = ? AND seq > ? ORDER BY seq", (conversation_id, after_seq)).fetchall()
            return {"status": "replay", "generation": conv["generation"], "seq": conv["seq"], "events": [self._decode_event(r) for r in rows]}

    def load_conversations(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            rows = self._db.execute(
                "SELECT conversation_id, generation, seq, snapshot_json, workspace_uri, project_id, has_session, is_closed, updated_at FROM conversations ORDER BY conversation_id"
            ).fetchall()
            return {
                r["conversation_id"]: {
                    "generation": r["generation"], "seq": r["seq"],
                    "snapshot": json.loads(r["snapshot_json"]),
                    "workspace_uri": r["workspace_uri"], "project_id": r["project_id"],
                    "has_session": bool(r["has_session"]), "is_closed": bool(r["is_closed"]),
                    "updated_at": r["updated_at"],
                }
                for r in rows
            }

    def upsert_subagent_link(self, child_cid: str, parent_cid: str, role_id: Optional[str], role_title: Optional[str]) -> None:
        if not child_cid or not parent_cid or child_cid == parent_cid or "--run-" in child_cid:
            return
        with self._lock:
            self._db.execute(
                "INSERT INTO subagent_links (child_cid, parent_cid, role_id, role_title, updated_at) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(child_cid) DO UPDATE SET parent_cid = excluded.parent_cid, role_id = COALESCE(excluded.role_id, subagent_links.role_id), "
                "role_title = COALESCE(excluded.role_title, subagent_links.role_title), updated_at = excluded.updated_at",
                (child_cid, parent_cid, role_id, role_title, time.time()),
            )

    def delete_subagent_link(self, child_cid: str) -> None:
        with self._lock:
            self._db.execute("DELETE FROM subagent_links WHERE child_cid = ?", (child_cid,))

    def load_subagent_links(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            rows = self._db.execute("SELECT child_cid, parent_cid, role_id, role_title, updated_at FROM subagent_links").fetchall()
            return {
                r["child_cid"]: {"parentConvId": r["parent_cid"], "roleId": r["role_id"] or "subagent", "roleTitle": r["role_title"] or "", "updatedAt": r["updated_at"]}
                for r in rows
            }

    def upsert_workspace_session(self, workspace_uri: str, conversation_id: str, project_id: Optional[str] = None, updated_at: Optional[float] = None) -> None:
        norm_ws = normalize_workspace_uri(workspace_uri)
        if not norm_ws or not conversation_id:
            return
        with self._lock:
            self._db.execute(
                "INSERT INTO workspace_sessions (workspace_uri, conversation_id, project_id, updated_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(workspace_uri) DO UPDATE SET conversation_id = excluded.conversation_id, project_id = COALESCE(excluded.project_id, workspace_sessions.project_id), updated_at = excluded.updated_at",
                (norm_ws, conversation_id, project_id, float(updated_at or time.time())),
            )

    def load_workspace_sessions(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            rows = self._db.execute("SELECT workspace_uri, conversation_id, project_id, updated_at FROM workspace_sessions").fetchall()
            return {
                r["workspace_uri"]: {"conversationId": r["conversation_id"], "projectId": r["project_id"], "timestamp": r["updated_at"]}
                for r in rows
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
        if isinstance(out.get("toolCalls"), list):
            out["toolCalls"] = [cls.compact_tool_entry(c) for c in out["toolCalls"][:max_calls]]
        if isinstance(out.get("terminalLogs"), list):
            out["terminalLogs"] = [
                ({**item, "output": item["output"][:400]} if isinstance(item, dict) and isinstance(item.get("output"), str) and len(item["output"]) > 400 else item)
                for item in out["terminalLogs"][:max_calls]
            ]
        return out

    def prune_bloat(self, *, telemetry_keep: int = 20, max_events_per_conv: Optional[int] = None, vacuum: bool = True) -> dict[str, int]:
        limit = max(1, int(max_events_per_conv or self.retention))
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                cur = self._db.execute("DELETE FROM events WHERE event_type = 'TELEMETRY_UPDATE'")
                deleted_tel = max(0, cur.rowcount)
                cur_ret = self._db.execute(
                    "DELETE FROM events WHERE EXISTS (SELECT 1 FROM conversations c WHERE c.conversation_id = events.conversation_id AND events.seq <= c.seq - ?)",
                    (limit,),
                )
                deleted_ret = max(0, cur_ret.rowcount)
                compacted_snaps = 0
                for r in self._db.execute("SELECT conversation_id, snapshot_json FROM conversations").fetchall():
                    try:
                        snap = json.loads(r["snapshot_json"])
                    except Exception:
                        continue
                    if not isinstance(snap, dict) or not isinstance(snap.get("telemetry"), dict):
                        continue
                    comp = self.compact_telemetry_store(snap["telemetry"], max_calls=telemetry_keep)
                    if comp != snap["telemetry"]:
                        snap["telemetry"] = comp
                        self._db.execute("UPDATE conversations SET snapshot_json = ? WHERE conversation_id = ?", (self._json(snap), r["conversation_id"]))
                        compacted_snaps += 1
                self._db.execute("COMMIT")
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
            if vacuum:
                self._db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                if self.db_path != ":memory:":
                    self._db.execute("VACUUM")
                    self._db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            return {"deletedTelemetryRows": deleted_tel, "deletedRetentionRows": deleted_ret, "compactedSnapshots": compacted_snaps}

    def close(self) -> None:
        with self._lock:
            self._db.close()
