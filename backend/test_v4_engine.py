import atexit
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PLUGIN_ROOT / "backend"
TOOLS_DIR = PLUGIN_ROOT / "tools"

_TEST_TMP = tempfile.TemporaryDirectory(prefix="thinktank_v4_test_", ignore_cleanup_errors=True)
atexit.register(_TEST_TMP.cleanup)

os.environ["THINKTANK_HOME"] = _TEST_TMP.name
os.environ["THINKTANK_STATE_FILE"] = str(Path(_TEST_TMP.name) / "think_tank_live_state.json")
os.environ["THINKTANK_SYNC_DB"] = str(Path(_TEST_TMP.name) / "think_tank_sync.sqlite3")
os.environ["THINKTANK_SESSION_FILE"] = str(Path(_TEST_TMP.name) / "active_antigravity_session.json")
os.environ["THINKTANK_ANTIGRAVITY_BRAIN_DIR"] = str(Path(_TEST_TMP.name) / "brain")
os.environ["THINKTANK_OUTBOX_DB"] = str(Path(_TEST_TMP.name) / "outbox.sqlite3")

for _p in (str(BACKEND_DIR), str(TOOLS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from fastapi.testclient import TestClient  # noqa: E402
import app as backend_app  # noqa: E402
import catalog  # noqa: E402
import install_plugin as plugin_installer  # noqa: E402
import store as store_mod  # noqa: E402
import thinktank_antigravity_hook as hook_bridge  # noqa: E402
import thinktank_bridge  # noqa: E402


class ThinkTankV4EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(backend_app.app)

    def setUp(self) -> None:
        self.conv_id = f"v4-{self._testMethodName}"
        res = self.client.post(
            "/api/task/update",
            json={
                "convId": self.conv_id,
                "project": "ThinkTankV4",
                "directive": "Verify modular v4 engine",
                "status": "ACTIVE",
                "progress": 15,
                "round": 1,
            },
        )
        self.assertEqual(res.status_code, 200, res.text)

    def _create_finding(self, *, to_agent: str = "backend-auditor", round_num: int = 1, repro: str = "1. Trigger API 2. Observe error") -> str:
        res = self.client.post(
            "/api/agent/collaborate",
            json={
                "convId": self.conv_id,
                "fromAgent": "council-critic",
                "toAgent": to_agent,
                "action": "RETURN_DEFECT",
                "severity": "HIGH",
                "reproSteps": repro,
                "content": f"Defect in round {round_num}",
                "origin": "subagent",
                "subagentConvId": f"critic-child-{round_num}",
            },
        )
        self.assertEqual(res.status_code, 200, res.text)
        return res.json()["finding"]["id"]

    # 1. AUD-04 & AUD-08: V3 SQLite migration, legacy JSON import, prune_bloat, zero live JSON writes
    def test_01_sqlite_migration_prune_and_no_json_state_write(self) -> None:
        self.assertFalse(Path(os.environ["THINKTANK_STATE_FILE"]).exists(), "v4 must never write think_tank_live_state.json")

        with tempfile.TemporaryDirectory(prefix="tt_v3_mig_") as tmpdir:
            tmp = Path(tmpdir)
            db_path = tmp / "v3_sync.sqlite3"
            # Build a legacy v3 schema without workspace_uri/project_id/has_session/is_closed columns
            raw = sqlite3.connect(str(db_path))
            raw.executescript(
                """
                CREATE TABLE conversations (
                    conversation_id TEXT PRIMARY KEY,
                    generation TEXT NOT NULL,
                    seq INTEGER NOT NULL DEFAULT 0,
                    snapshot_json TEXT NOT NULL DEFAULT '{}',
                    updated_at REAL NOT NULL
                );
                CREATE TABLE events (
                    conversation_id TEXT NOT NULL,
                    seq INTEGER NOT NULL,
                    event_id TEXT NOT NULL,
                    generation TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    source TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY (conversation_id, seq),
                    UNIQUE (conversation_id, event_id)
                );
                """
            )
            bloated_snap = {
                "id": "legacy-cid-1",
                "workspaceUri": "file:///c:/Legacy/Repo",
                "projectId": "proj-legacy",
                "thinkTank": {"project": "LegacyV3", "status": "ACTIVE", "isClosed": False},
                "messages": [{"id": "m1", "content": "Legacy msg"}],
                "telemetry": {
                    "toolCalls": [{"id": f"tc-{i}", "output": "X" * 800, "args": {"Prompt": "P" * 400}} for i in range(35)],
                    "terminalLogs": [],
                    "backgroundTasks": [],
                },
            }
            raw.execute(
                "INSERT INTO conversations VALUES (?, ?, ?, ?, ?)",
                ("legacy-cid-1", "gen-1", 6, json.dumps(bloated_snap), 1700000000.0),
            )
            raw.execute(
                "INSERT INTO events VALUES (?, 1, 'ev-1', 'gen-1', 'NEW_MESSAGE', '{}', 'api', 1700000000.0)",
                ("legacy-cid-1",),
            )
            for idx in range(2, 7):
                raw.execute(
                    "INSERT INTO events VALUES (?, ?, ?, 'gen-1', 'TELEMETRY_UPDATE', '{}', 'api', 1700000001.0)",
                    ("legacy-cid-1", idx, f"ev-tel-{idx}"),
                )
            raw.commit()
            raw.close()

            st = store_mod.SyncEventStore(str(db_path), retention=150)
            try:
                convs = st.load_conversations()
                self.assertIn("legacy-cid-1", convs)
                self.assertEqual(convs["legacy-cid-1"]["project_id"], "proj-legacy")
                self.assertTrue(convs["legacy-cid-1"]["has_session"])
                self.assertFalse(convs["legacy-cid-1"]["is_closed"])

                # Legacy files import
                legacy_links = tmp / "links.json"
                legacy_links.write_text(json.dumps({"child-99": {"parentConversationId": "legacy-cid-1", "roleId": "tt-backend-auditor"}}), encoding="utf-8")
                legacy_sess = tmp / "sess.json"
                legacy_sess.write_text(json.dumps({"sessionsByWorkspace": {"file:///c:/Legacy/Repo": {"conversationId": "legacy-cid-1", "timestamp": 1700000100.0}}}), encoding="utf-8")
                imp = st.import_legacy_files(links_file=legacy_links, session_file=legacy_sess)
                self.assertEqual(imp["links"], 1)
                self.assertEqual(imp["workspaces"], 1)

                stats = st.prune_bloat(telemetry_keep=10, vacuum=True)
                self.assertEqual(stats["deletedTelemetryRows"], 5)
                self.assertEqual(stats["compactedSnapshots"], 1)
                compacted = st.load_conversations()["legacy-cid-1"]["snapshot"]
                self.assertEqual(len(compacted["telemetry"]["toolCalls"]), 10)
                self.assertLessEqual(len(compacted["telemetry"]["toolCalls"][0]["output"]), 240)
            finally:
                st.close()

    # 2. AUD-01, AUD-02, AUD-03, AUD-08: Single CASE_EVENT (seq+1), TRANSIENT_PULSE (seq+0), SYNC_SNAPSHOT/SYNC_REPLAY (no SYNC_READY)
    def test_02_single_case_event_transient_pulse_and_ws_replay(self) -> None:
        with self.client.websocket_connect(f"/ws?convId={self.conv_id}") as ws:
            first = ws.receive_json()
            # AUD-03: Never SYNC_READY; first frame is strictly SYNC_SNAPSHOT
            self.assertEqual(first["type"], "SYNC_SNAPSHOT")
            snap = first["snapshot"]
            self.assertEqual(snap["schemaVersion"], "4.0")
            self.assertEqual(snap["syncMode"], "durable-websocket")
            self.assertIsInstance(snap["updatedAtMs"], int)
            gen = first["generation"]
            seq0 = first["seq"]
            self.assertGreaterEqual(seq0, 1)

            # Mutating API -> exactly 1 CASE_EVENT with seq+1 and changedSlices
            r_sub = self.client.post(
                "/api/subtasks/upsert",
                json={
                    "convId": self.conv_id,
                    "id": "WBS-01",
                    "title": "Build WAL store",
                    "assignee": "backend-auditor",
                    "lockedFiles": ["backend/store.py"],
                    "acceptanceCriteria": "All tests pass",
                },
            )
            self.assertEqual(r_sub.status_code, 200, r_sub.text)
            ev1 = ws.receive_json()
            self.assertEqual(ev1["type"], "CASE_EVENT")
            self.assertEqual(ev1["seq"], seq0 + 1)
            self.assertIn("subtasks", ev1["changedSlices"])
            self.assertIn("fileLocks", ev1["changedSlices"])

            # Collaborate -> strictly 1 CASE_EVENT (no triple-broadcast storm!)
            r_col = self.client.post(
                "/api/agent/collaborate",
                json={
                    "convId": self.conv_id,
                    "fromAgent": "council-critic",
                    "toAgent": "backend-auditor",
                    "action": "RETURN_DEFECT",
                    "severity": "HIGH",
                    "reproSteps": "1. Test lock",
                    "content": "Defect 1",
                },
            )
            self.assertEqual(r_col.status_code, 200, r_col.text)
            ev2 = ws.receive_json()
            self.assertEqual(ev2["type"], "CASE_EVENT")
            self.assertEqual(ev2["seq"], seq0 + 2)
            self.assertIn("findings", ev2["changedSlices"])
            self.assertIn("interactions", ev2["changedSlices"])

            # Telemetry -> TRANSIENT_PULSE (seq does NOT advance!)
            r_tel = self.client.post(
                "/api/telemetry/host_tool",
                json={
                    "id": "pulse-read-1",
                    "convId": self.conv_id,
                    "tool": "read_file",
                    "status": "SUCCESS",
                    "stepIdx": 1,
                    "args": {"Path": "backend/store.py"},
                    "output": "ok",
                },
            )
            self.assertEqual(r_tel.status_code, 200)
            pulse = ws.receive_json()
            self.assertEqual(pulse["type"], "TRANSIENT_PULSE")
            self.assertEqual(pulse["pulseKind"], "TELEMETRY")
            self.assertEqual(backend_app.sync_store.cursor(self.conv_id)["seq"], seq0 + 2)

            # Next mutation stays contiguous at seq0 + 3
            r_chat = self.client.post(
                "/api/chat/send",
                json={
                    "convId": self.conv_id,
                    "senderCode": "BE",
                    "senderName": "Backend",
                    "senderRole": "backend-auditor",
                    "content": "Working on fix",
                },
            )
            self.assertEqual(r_chat.status_code, 200)
            ev3 = ws.receive_json()
            self.assertEqual(ev3["type"], "CASE_EVENT")
            self.assertEqual(ev3["seq"], seq0 + 3)

            # PING / PONG
            ws.send_json({"type": "SYNC_PING", "clientTime": 12345})
            pong = ws.receive_json()
            self.assertEqual(pong["type"], "SYNC_PONG")

        # Reconnect with generation & afterSeq -> strictly SYNC_REPLAY with missing events
        with self.client.websocket_connect(f"/ws?convId={self.conv_id}&generation={gen}&afterSeq={seq0}") as ws_rep:
            rep = ws_rep.receive_json()
            self.assertEqual(rep["type"], "SYNC_REPLAY")
            self.assertEqual([e["seq"] for e in rep["events"]], [seq0 + 1, seq0 + 2, seq0 + 3])

        # Reconnect with stale generation -> SYNC_SNAPSHOT
        with self.client.websocket_connect(f"/ws?convId={self.conv_id}&generation=wrong-gen&afterSeq=0") as ws_stale:
            stale = ws_stale.receive_json()
            self.assertEqual(stale["type"], "SYNC_SNAPSHOT")

    # 3. All HTTP 409/400/404/429 gates + idempotency + project guard + 5-stage lifecycle
    def test_03_all_gates_409_and_five_stage_lifecycle(self) -> None:
        # Project ID guard (409 on mismatch) & Event ID idempotency
        p_cid = "proj-guarded-conv-1"
        r_ok = self.client.post(
            "/api/task/update",
            headers={"X-ThinkTank-Project-Id": "proj-alpha", "X-ThinkTank-Event-Id": "evt-uniq-1"},
            json={"convId": p_cid, "project": "Guarded", "directive": "Lock project", "status": "ACTIVE"},
        )
        self.assertEqual(r_ok.status_code, 200, r_ok.text)

        r_dup = self.client.post(
            "/api/task/update",
            headers={"X-ThinkTank-Project-Id": "proj-alpha", "X-ThinkTank-Event-Id": "evt-uniq-1"},
            json={"convId": p_cid, "project": "Guarded", "directive": "Retry"},
        )
        self.assertEqual(r_dup.status_code, 200)
        self.assertEqual(r_dup.json()["status"], "duplicate")

        r_dup_diff = self.client.post(
            "/api/task/update",
            headers={"X-ThinkTank-Event-Id": "evt-uniq-1"},
            json={"convId": self.conv_id, "project": "Other"},
        )
        self.assertEqual(r_dup_diff.status_code, 409)

        r_mismatch = self.client.post(
            "/api/chat/send",
            headers={"X-ThinkTank-Project-Id": "proj-beta"},
            json={"convId": p_cid, "senderCode": "BE", "senderName": "BE", "senderRole": "backend-auditor", "content": "hijack"},
        )
        self.assertEqual(r_mismatch.status_code, 409)

        # WBS acceptance & single-owner file locks -> 409
        self.assertEqual(
            self.client.post(
                "/api/subtasks/upsert",
                json={"convId": self.conv_id, "id": "t-no-acc", "title": "No acc", "assignee": "backend-auditor"},
            ).status_code,
            409,
        )
        self.assertEqual(
            self.client.post(
                "/api/subtasks/upsert",
                json={
                    "convId": self.conv_id, "id": "t-be", "title": "Own file",
                    "assignee": "backend-auditor", "lockedFiles": ["backend/app.py"], "acceptanceCriteria": "Tests pass",
                },
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                "/api/subtasks/upsert",
                json={
                    "convId": self.conv_id, "id": "t-ui", "title": "Conflict file",
                    "assignee": "ui-frontend-designer", "lockedFiles": ["backend/app.py"], "acceptanceCriteria": "Conflict",
                },
            ).status_code,
            409,
        )

        # RETURN_DEFECT gates (400 bad sev, 409 blank repro, 409 max 7 per round)
        self.assertEqual(
            self.client.post(
                "/api/agent/collaborate",
                json={"convId": self.conv_id, "fromAgent": "council-critic", "toAgent": "backend-auditor", "action": "RETURN_DEFECT", "severity": "LOW", "reproSteps": "1. x", "content": "low"},
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                "/api/agent/collaborate",
                json={"convId": self.conv_id, "fromAgent": "council-critic", "toAgent": "backend-auditor", "action": "RETURN_DEFECT", "severity": "HIGH", "reproSteps": "  ", "content": "blank"},
            ).status_code,
            409,
        )
        fids = [self._create_finding(round_num=1, repro=f"1. Repro {i}") for i in range(7)]
        self.assertEqual(fids[-1], "F-07")
        self.assertEqual(
            self.client.post(
                "/api/agent/collaborate",
                json={"convId": self.conv_id, "fromAgent": "council-critic", "toAgent": "backend-auditor", "action": "RETURN_DEFECT", "severity": "MEDIUM", "reproSteps": "1. 8th", "content": "8th"},
            ).status_code,
            409,
        )

        # WontFix without reason -> 409; resolve F-02..F-07 as WontFix with reason -> 200
        self.assertEqual(
            self.client.post("/api/findings/action", json={"convId": self.conv_id, "findingId": "F-02", "action": "wontfix", "reason": "  "}).status_code,
            409,
        )
        for fid in fids[1:]:
            self.assertEqual(
                self.client.post("/api/findings/action", json={"convId": self.conv_id, "findingId": fid, "action": "wontfix", "reason": "Test scope"}).status_code,
                200,
            )

        # F-01: Open -> WORKER_FIX (InReview) -> REVIEW_QUERY(returnToFixing) -> Fixing -> WORKER_FIX -> QA_DISPATCH -> QA_REPORT FAIL -> Fixing -> WORKER_FIX -> QA_DISPATCH -> QA_REPORT PASS
        self.assertEqual(
            self.client.post("/api/agent/collaborate", json={"convId": self.conv_id, "fromAgent": "qa-reviewer", "toAgent": "code-reviewer", "action": "QA_REPORT", "findingId": "F-01", "result": "PASS", "evidenceCommand": "pytest", "exitCode": 0}).status_code,
            409,
        )
        r_fix1 = self.client.post("/api/agent/collaborate", json={"convId": self.conv_id, "fromAgent": "backend-auditor", "toAgent": "code-reviewer", "action": "WORKER_FIX", "findingId": "F-01", "content": "Fixed 1"})
        self.assertEqual(r_fix1.status_code, 200)
        self.assertEqual(r_fix1.json()["finding"]["state"], "InReview")

        r_rq_bounce = self.client.post("/api/agent/collaborate", json={"convId": self.conv_id, "fromAgent": "code-reviewer", "toAgent": "backend-auditor", "action": "REVIEW_QUERY", "findingId": "F-01", "returnToFixing": True, "content": "Handle null edge"})
        self.assertEqual(r_rq_bounce.status_code, 200)
        self.assertEqual(r_rq_bounce.json()["finding"]["state"], "Fixing")
        self.assertEqual(r_rq_bounce.json()["finding"]["returnCount"], 1)

        self.assertEqual(self.client.post("/api/agent/collaborate", json={"convId": self.conv_id, "fromAgent": "backend-auditor", "toAgent": "code-reviewer", "action": "WORKER_FIX", "findingId": "F-01", "content": "Fixed null"}).status_code, 200)
        r_qad = self.client.post("/api/agent/collaborate", json={"convId": self.conv_id, "fromAgent": "code-reviewer", "toAgent": "qa-reviewer", "action": "QA_DISPATCH", "findingId": "F-01", "content": "Verify"})
        self.assertEqual(r_qad.status_code, 200)
        self.assertEqual(r_qad.json()["finding"]["state"], "Testing")

        # Missing evidence / bad exit / missing runnerReason -> 409
        self.assertEqual(self.client.post("/api/agent/collaborate", json={"convId": self.conv_id, "fromAgent": "qa-reviewer", "toAgent": "code-reviewer", "action": "QA_REPORT", "findingId": "F-01", "result": "PASS", "evidenceCommand": "", "exitCode": 0}).status_code, 409)
        self.assertEqual(self.client.post("/api/agent/collaborate", json={"convId": self.conv_id, "fromAgent": "qa-reviewer", "toAgent": "code-reviewer", "action": "QA_REPORT", "findingId": "F-01", "result": "PASS", "evidenceCommand": "unittest", "exitCode": 1}).status_code, 409)
        self.assertEqual(self.client.post("/api/agent/collaborate", json={"convId": self.conv_id, "fromAgent": "qa-reviewer", "toAgent": "code-reviewer", "action": "QA_REPORT", "findingId": "F-01", "result": "PASS", "evidenceCommand": "unittest", "exitCode": 0, "runner": "host-fallback", "runnerReason": ""}).status_code, 409)

        # Complete blocked while F-01 is Testing -> 409
        self.assertEqual(self.client.post("/api/task/update", json={"convId": self.conv_id, "status": "COMPLETED", "progress": 100}).status_code, 409)

        # QA_REPORT PASS -> Verified
        r_pass = self.client.post(
            "/api/agent/collaborate",
            json={
                "convId": self.conv_id, "fromAgent": "qa-reviewer", "toAgent": "code-reviewer",
                "action": "QA_REPORT", "findingId": "F-01", "result": "PASS",
                "evidenceCommand": "python -m unittest", "exitCode": 0, "evidenceExcerpt": "OK",
                "runner": "substrate", "content": "All green",
            },
        )
        self.assertEqual(r_pass.status_code, 200)
        self.assertEqual(r_pass.json()["finding"]["state"], "Verified")

        # Complete succeeds -> Closed + closureReceipt
        r_close = self.client.post(
            "/api/task/update",
            json={"convId": self.conv_id, "status": "COMPLETED", "progress": 100, "summary": "Verified", "origin": "subagent", "subagentConvId": "tm-child"},
        )
        self.assertEqual(r_close.status_code, 200, r_close.text)
        receipt = r_close.json()["closureReceipt"]
        self.assertTrue(receipt["qaAllExitZero"])
        self.assertEqual(receipt["findingsVerified"], 1)
        self.assertEqual(receipt["findingsWontFix"], 6)

        # Closed case blocks writes (409); reopen restores mutability
        self.assertEqual(
            self.client.post("/api/chat/send", json={"convId": self.conv_id, "senderCode": "BE", "senderName": "BE", "senderRole": "backend-auditor", "content": "blocked"}).status_code,
            409,
        )
        self.assertEqual(self.client.post("/api/governance/reopen", json={"convId": self.conv_id}).status_code, 200)
        self.assertEqual(
            self.client.post("/api/chat/send", json={"convId": self.conv_id, "senderCode": "BE", "senderName": "BE", "senderRole": "backend-auditor", "content": "reopened"}).status_code,
            200,
        )

    # 4. AUD-06 & AUD-07: Complete interaction graph (votes + channel posts without @mention) + role alias parity
    def test_04_complete_interaction_graph_and_alias_parity(self) -> None:
        # Role alias parity across backend catalog, hook, and sidecar roles.mjs
        for raw_id, expected in (
            ("coordinator", "main_agent"),
            ("tt-backend-auditor", "backend-auditor"),
            ("agent_ui_frontend_designer", "ui-frontend-designer"),
            ("ecommerce-seo-operator", "ecommerce_seo_operator"),
            ("wp-technical-operator", "wp_technical_operator"),
        ):
            self.assertEqual(catalog.normalize_agent_id(raw_id), expected)
            self.assertEqual(hook_bridge._normalize_role_id(raw_id), expected)

        # Proposal vote must record directed interaction voter -> team-manager (action=VOTE, requestType=DECISION)
        self.assertEqual(
            self.client.post(
                "/api/proposal/update",
                json={"convId": self.conv_id, "id": "p-v4", "project": "V4", "title": "Plan", "author": "TM", "summary": "Summary"},
            ).status_code,
            200,
        )
        r_vote = self.client.post(
            "/api/proposal/vote",
            json={"convId": self.conv_id, "voter": "council-critic", "stance": "APPROVE", "confidence": 96, "comment": "Strong design"},
        )
        self.assertEqual(r_vote.status_code, 200, r_vote.text)

        # Channel post WITHOUT @mention must still record directed interaction (never dropped!)
        r_post_no_mention = self.client.post(
            "/api/chat/send",
            json={
                "convId": self.conv_id,
                "channel": "SYNC",
                "senderCode": "BE",
                "senderName": "Backend",
                "senderRole": "backend-auditor",
                "content": "Schema updated without mention",
            },
        )
        self.assertEqual(r_post_no_mention.status_code, 200, r_post_no_mention.text)

        r_tm_post = self.client.post(
            "/api/chat/send",
            json={
                "convId": self.conv_id,
                "channel": "MAIN",
                "senderCode": "TM",
                "senderName": "Team Manager",
                "senderRole": "team-manager",
                "content": "Checkpoint update without mention",
            },
        )
        self.assertEqual(r_tm_post.status_code, 200, r_tm_post.text)

        snap = self.client.get("/api/status", params={"convId": self.conv_id}).json()
        interactions = snap["interactions"]
        self.assertTrue(
            any(
                ev["from"] == "council-critic" and ev["to"] == "team-manager" and ev["action"] == "VOTE" and ev["requestType"] == "DECISION"
                for ev in interactions
            ),
            f"Vote interaction missing: {interactions}",
        )
        self.assertTrue(
            any(ev["from"] == "backend-auditor" and ev["to"] == "team-manager" for ev in interactions),
            f"Channel post without @mention was dropped: {interactions}",
        )
        self.assertTrue(
            any(ev["from"] == "team-manager" and ev["to"] == "main_agent" for ev in interactions),
            f"Team-manager fallback target wrong: {interactions}",
        )
        edges = {(e["from"], e["to"]): e for e in snap["graph"]["edges"]}
        self.assertIn(("council-critic", "team-manager"), edges)
        self.assertIn(("backend-auditor", "team-manager"), edges)
        self.assertIn(("team-manager", "main_agent"), edges)

    # 5. Workspace hysteresis, parent transcript discovery, auto-DELEGATE, and Windows .tmp cleanup (AUD-05)
    def test_05_hysteresis_parent_discovery_and_windows_atomic_tmp_cleanup(self) -> None:
        ws_uri = "file:///c:/workspaces/v4-hysteresis"
        tt_cid = "aaaaaaaa-0000-1111-2222-333333333333"
        plain_cid = "bbbbbbbb-0000-1111-2222-333333333333"
        child_cid = "cccccccc-0000-1111-2222-333333333333"

        self.assertEqual(
            self.client.post("/api/task/update", json={"convId": tt_cid, "project": "Hyst", "directive": "Pin", "status": "ACTIVE"}).status_code,
            200,
        )
        self.assertEqual(
            self.client.post("/api/host/active-session", json={"conversationId": tt_cid, "workspaceUri": ws_uri, "eventSource": "pre-invocation"}).status_code,
            200,
        )
        # Plain background tab post-tool-use cannot hijack ws_uri
        self.assertEqual(
            self.client.post("/api/host/active-session", json={"conversationId": plain_cid, "workspaceUri": ws_uri, "eventSource": "post-tool-use"}).status_code,
            200,
        )
        ctx = self.client.get("/api/host/context", params={"workspaceUri": ws_uri}).json()
        self.assertEqual(ctx["conversationId"], tt_cid)

        # Auto-DELEGATE on invoke_subagent advances seq (+1) and binds child
        r_inv = self.client.post(
            "/api/telemetry/host_tool",
            json={
                "id": "inv-v4-1", "convId": tt_cid, "tool": "invoke_subagent",
                "status": "SUCCESS", "stepIdx": 1,
                "args": {"TypeName": "tt-backend-auditor", "Role": "Backend Worker"},
                "output": f"Created child {child_cid}",
            },
        )
        self.assertEqual(r_inv.status_code, 200)
        st = self.client.get("/api/status", params={"convId": child_cid}).json()
        self.assertEqual(st["convId"], tt_cid)
        self.assertTrue(any(e["from"] == "main_agent" and e["to"] == "backend-auditor" and e["action"] == "DELEGATE" for e in st["interactions"]))

        # Parent transcript discovery from Brain dir
        brain_dir = Path(os.environ["THINKTANK_ANTIGRAVITY_BRAIN_DIR"])
        p_uuid = "dddddddd-0000-1111-2222-333333333333"
        c_uuid = "eeeeeeee-0000-1111-2222-333333333333"
        p_log = brain_dir / p_uuid / ".system_generated" / "logs" / "transcript.jsonl"
        p_log.parent.mkdir(parents=True, exist_ok=True)
        p_log.write_text(
            json.dumps({"step_index": 0, "source": "USER_EXPLICIT", "content": "Start"}) + "\n"
            + json.dumps({"step_index": 1, "tool_calls": [{"name": "invoke_subagent", "args": {"TypeName": "tt-code-reviewer", "Role": "Reviewer"}}]}) + "\n"
            + json.dumps({"step_index": 2, "content": f'Created the following subagent:\n{{"conversationId": "{c_uuid}"}}'}) + "\n",
            encoding="utf-8",
        )
        disc_p, disc_r, _ = hook_bridge._discover_parent_from_brain(c_uuid)
        self.assertEqual(disc_p, p_uuid)
        self.assertEqual(disc_r, "code-reviewer")

        # AUD-05: Windows PermissionError retry + guaranteed .tmp cleanup in finally
        with tempfile.TemporaryDirectory(prefix="tt_win_tmp_") as tmpdir:
            target = Path(tmpdir) / "active_antigravity_session.json"
            calls = {"n": 0}
            real_replace = os.replace

            def _flaky_replace(src, dst):
                calls["n"] += 1
                if calls["n"] < 3:
                    raise PermissionError(13, "WinError 5 simulated lock")
                return real_replace(src, dst)

            with patch("os.replace", side_effect=_flaky_replace):
                ok = hook_bridge.write_json_atomic(target, {"conversationId": p_uuid})
            self.assertTrue(ok)
            self.assertEqual(calls["n"], 3)
            self.assertEqual(list(Path(tmpdir).glob("*.tmp")), [])

            with patch("os.replace", side_effect=PermissionError(13, "Always locked")):
                ok_fail = hook_bridge.write_json_atomic(target, {"conversationId": "fail"})
            self.assertFalse(ok_fail)
            self.assertEqual(list(Path(tmpdir).glob("*.tmp")), [], "Failed atomic write must still unlink .tmp")

    # 6. CLI (status, doctor, prune-db), installer v3 pruning, and governance 95% review gate
    def test_06_cli_installer_and_governance_review_gate(self) -> None:
        # Governance 95% gate + role caps 429
        self.assertEqual(self.client.post("/api/task/update", json={"convId": self.conv_id, "roleCaps": {"main": 1, "manager": 1, "subagents": 1}}).status_code, 200)
        self.assertEqual(self.client.post("/api/chat/send", json={"convId": self.conv_id, "senderCode": "BE", "senderName": "BE", "senderRole": "backend-auditor", "content": "1"}).status_code, 200)
        self.assertEqual(self.client.post("/api/chat/send", json={"convId": self.conv_id, "senderCode": "BE", "senderName": "BE", "senderRole": "backend-auditor", "content": "2"}).status_code, 429)

        r_comp = self.client.post("/api/governance/compress_final", json={"convId": self.conv_id})
        self.assertEqual(r_comp.status_code, 200)
        rev_id = r_comp.json()["review"]["id"]
        self.assertEqual(self.client.post("/api/governance/review_dispatch", json={"convId": self.conv_id, "status": "sent"}).status_code, 200)
        self.assertEqual(
            self.client.post("/api/chat/send", json={"convId": self.conv_id, "senderCode": "TM", "senderName": "TM", "senderRole": "team-manager", "content": "Manager summary", "isReview": True, "reviewId": rev_id}).status_code,
            200,
        )
        self.assertEqual(
            self.client.post("/api/chat/send", json={"convId": self.conv_id, "senderCode": "MA", "senderName": "MA", "senderRole": "main_agent", "content": "Main summary", "isReview": True, "reviewId": rev_id}).status_code,
            200,
        )
        r_sub_rev = self.client.post(
            "/api/governance/submit_review",
            json={
                "convId": self.conv_id, "reviewId": rev_id,
                "managerSummary": "Manager summary", "mainSummary": "Main summary",
                "confidence": 80, "recommendation": "continue",
                "continueReasons": ["More checks"], "completionReasons": ["Core ready"], "evidence": ["unittest ok"],
            },
        )
        self.assertEqual(r_sub_rev.status_code, 200)
        self.assertTrue(r_sub_rev.json()["review"]["humanRequired"])
        r_dec = self.client.post("/api/governance/review_decision", json={"convId": self.conv_id, "decision": "continue", "note": "Proceed"})
        self.assertEqual(r_dec.status_code, 200)
        self.assertEqual(r_dec.json()["review"]["status"], "HUMAN_CONTINUE")

        # CLI status, doctor, prune-db
        with tempfile.TemporaryDirectory(prefix="tt_cli_db_") as tmpdir:
            tmp = Path(tmpdir)
            db_file = tmp / "think_tank_sync.sqlite3"
            st = store_mod.SyncEventStore(str(db_file))
            st.commit(conversation_id="c1", event_id="e1", event_type="TELEMETRY_UPDATE", payload={}, snapshot={"id": "c1", "telemetry": {"toolCalls": []}})
            st.close()
            buf = io.StringIO()
            with patch.object(sys, "argv", ["thinktank_bridge.py", "prune-db", "--db", str(db_file), "--keep", "5"]), redirect_stdout(buf):
                thinktank_bridge.main()
            prune_res = json.loads(buf.getvalue())
            self.assertTrue(prune_res["ok"])
            self.assertEqual(prune_res["deletedTelemetryRows"], 1)

            with patch.object(thinktank_bridge.bridge_transport, "_request", return_value={"convId": self.conv_id, "pipelineStage": 2, "thinkTank": {"status": "ACTIVE", "round": 1, "maxRounds": 50}}):
                buf_st = io.StringIO()
                with patch.object(sys, "argv", ["thinktank_bridge.py", "status", "--conv-id", self.conv_id, "--json"]), redirect_stdout(buf_st):
                    thinktank_bridge.main()
                self.assertEqual(json.loads(buf_st.getvalue())["convId"], self.conv_id)

            (tmp / "hooks.json").write_text('{"thinktank-live-sync": {"enabled": true}}', encoding="utf-8")
            with patch.object(thinktank_bridge.bridge_transport, "_request", return_value={"ok": True, "syncMode": "durable-websocket"}):
                buf_doc = io.StringIO()
                with patch.object(sys, "argv", ["thinktank_bridge.py", "doctor", "--home", str(tmp)]), redirect_stdout(buf_doc):
                    thinktank_bridge.main()
                doc_res = json.loads(buf_doc.getvalue())
                self.assertTrue(doc_res["ok"])
                self.assertTrue(doc_res["hooksConfigured"])

        # Installer prunes obsolete v3 files & orphaned .tmp files + respects --no-hook
        with tempfile.TemporaryDirectory(prefix="tt_v4_install_") as tmpdir:
            target = Path(tmpdir)
            for sc_base in (
                target / "plugins" / "team-orchestration-director" / "sidecars" / "think-tank",
                target / "thinktank" / "sidecars" / "think-tank",
            ):
                (sc_base / "tests").mkdir(parents=True, exist_ok=True)
                for obs in ("app.js", "i18n.js", "activity.js", "conversation-context.mjs", "ui-preferences.mjs"):
                    (sc_base / obs).write_text("// v3", encoding="utf-8")
                (sc_base / "tests" / "ui_i18n.test.cjs").write_text("// cjs", encoding="utf-8")
            orphan_tmp = target / "active_antigravity_session.json.999.1.tmp"
            orphan_tmp.write_text("{}", encoding="utf-8")

            res_no_hook = plugin_installer.install_plugin(PLUGIN_ROOT, target, install_hook=False)
            self.assertFalse(res_no_hook["hooksInstalled"])
            self.assertTrue(res_no_hook["hooksSkipped"])
            self.assertFalse((target / "hooks.json").exists())
            self.assertFalse(orphan_tmp.exists())
            self.assertEqual(res_no_hook["prunedTmpFiles"], 1)
            for sc_base in (
                target / "plugins" / "team-orchestration-director" / "sidecars" / "think-tank",
                target / "thinktank" / "sidecars" / "think-tank",
            ):
                for obs in ("app.js", "i18n.js", "activity.js", "conversation-context.mjs", "ui-preferences.mjs"):
                    self.assertFalse((sc_base / obs).exists())
                self.assertFalse((sc_base / "tests" / "ui_i18n.test.cjs").exists())
                self.assertTrue((sc_base / "tokens.css").is_file())
                self.assertTrue((sc_base / "app.css").is_file())

    # 7. Stage 3 Remediation Regression Tests (F-03, F-06, F-07)
    def test_07_remediation_f03_f06_f07(self) -> None:
        # F-03: --new-run archives old run, resets events/seq/generation, and broadcasts all wiped slices + durableAgentEvent
        child_run_cid = "ffffffff-0000-1111-2222-333333333333"
        self.assertEqual(
            self.client.post(
                "/api/subtasks/upsert",
                json={
                    "convId": self.conv_id, "id": "WBS-RUN1", "title": "Old run task",
                    "assignee": "backend-auditor", "acceptanceCriteria": "Done",
                },
            ).status_code,
            200,
        )
        old_cursor = backend_app.sync_store.cursor(self.conv_id)
        old_gen = old_cursor["generation"]
        old_seq = old_cursor["seq"]

        with self.client.websocket_connect(f"/ws?convId={self.conv_id}") as ws_live:
            ws_live.receive_json()  # SYNC_SNAPSHOT
            r_new = self.client.post("/api/task/update", json={"convId": self.conv_id, "newRun": True, "project": "Run2", "directive": "Fresh run"})
            self.assertEqual(r_new.status_code, 200, r_new.text)
            ev_new = ws_live.receive_json()
            self.assertEqual(ev_new["type"], "CASE_EVENT")
            self.assertEqual(ev_new["seq"], 1)
            self.assertNotEqual(ev_new["generation"], old_gen)
            for slice_key in ("findings", "subtasks", "fileLocks", "messages", "interactions", "graph", "proposal", "review", "telemetry", "closureReceipt"):
                self.assertIn(slice_key, ev_new["changedSlices"])
            self.assertEqual(ev_new["subtasks"], [])

        # Reconnect with old generation & seq after --new-run must force SYNC_SNAPSHOT (no old-run bleed)
        with self.client.websocket_connect(f"/ws?convId={self.conv_id}&generation={old_gen}&afterSeq={old_seq}") as ws_old_gen:
            frame = ws_old_gen.receive_json()
            self.assertEqual(frame["type"], "SYNC_SNAPSHOT")
            self.assertEqual(frame["snapshot"]["subtasks"], [])

        # durableAgentEvent: first non-delegation tool call of verified subagent commits durable AGENTS_UPDATE (seq+1)
        self.assertEqual(
            self.client.post(
                "/api/telemetry/host_tool",
                json={
                    "id": "inv-durable-1", "convId": self.conv_id, "tool": "invoke_subagent",
                    "status": "SUCCESS", "stepIdx": 1,
                    "args": {"TypeName": "tt-qa-reviewer", "Role": "QA"},
                    "output": f"Created {child_run_cid}",
                },
            ).status_code,
            200,
        )
        child_2 = "12121212-0000-1111-2222-333333333333"
        backend_app.session_resolver.subagent_session_map[child_2] = {"parentConvId": self.conv_id, "roleId": "ecommerce_seo_operator", "roleTitle": "SEO"}
        seq_before = backend_app.sync_store.cursor(self.conv_id)["seq"]
        with self.client.websocket_connect(f"/ws?convId={self.conv_id}") as ws_dur:
            ws_dur.receive_json()
            r_child_tool = self.client.post(
                "/api/telemetry/host_tool",
                json={"id": "seo-read-1", "convId": child_2, "tool": "read_file", "status": "SUCCESS", "stepIdx": 0, "args": {"Path": "README.md"}},
            )
            self.assertEqual(r_child_tool.status_code, 200)
            ev_dur = ws_dur.receive_json()
            self.assertEqual(ev_dur["type"], "CASE_EVENT")
            self.assertEqual(ev_dur["eventKind"], "AGENTS_UPDATE")
            self.assertIn("telemetry", ev_dur["changedSlices"])
        self.assertEqual(backend_app.sync_store.cursor(self.conv_id)["seq"], seq_before + 1)

        # F-06: install_plugin prunes stale v3 .mjs and test_*.py files + F-07: hook aliases match catalog 100%
        self.assertTrue(set(catalog.ROLE_ALIAS_MAP.keys()).issubset(set(hook_bridge.ROLE_ALIASES.keys())))
        for k, v in catalog.ROLE_ALIAS_MAP.items():
            self.assertEqual(hook_bridge.ROLE_ALIASES[k], v)

        with tempfile.TemporaryDirectory(prefix="tt_f06_prune_") as tmpdir:
            target = Path(tmpdir)
            for sc_dir in (
                target / "plugins" / "team-orchestration-director" / "sidecars" / "think-tank" / "tests",
                target / "thinktank" / "sidecars" / "think-tank" / "tests",
            ):
                sc_dir.mkdir(parents=True, exist_ok=True)
                (sc_dir / "ui-contract.test.mjs").write_text("// stale v3", encoding="utf-8")
            for be_dir in (
                target / "plugins" / "team-orchestration-director" / "backend",
                target / "thinktank" / "backend",
            ):
                be_dir.mkdir(parents=True, exist_ok=True)
                (be_dir / "test_remediation_gates.py").write_text("# stale v3", encoding="utf-8")
            plugin_installer.install_plugin(PLUGIN_ROOT, target, install_hook=False)
            self.assertFalse((target / "plugins" / "team-orchestration-director" / "sidecars" / "think-tank" / "tests" / "ui-contract.test.mjs").exists())
            self.assertFalse((target / "thinktank" / "sidecars" / "think-tank" / "tests" / "ui-contract.test.mjs").exists())
            self.assertFalse((target / "plugins" / "team-orchestration-director" / "backend" / "test_remediation_gates.py").exists())
            self.assertFalse((target / "thinktank" / "backend" / "test_remediation_gates.py").exists())

        # F-07: apply_review_submit enforces unresolved findings gate & builds closureReceipt on completion
        fid = self._create_finding(round_num=1, repro="1. Trigger review block")
        self.assertEqual(self.client.post("/api/governance/compress_final", json={"convId": self.conv_id}).status_code, 200)
        rev_id = self.client.get("/api/status", params={"convId": self.conv_id}).json()["review"]["id"]
        self.assertEqual(self.client.post("/api/governance/review_dispatch", json={"convId": self.conv_id, "status": "sent"}).status_code, 200)
        self.client.post("/api/chat/send", json={"convId": self.conv_id, "senderCode": "TM", "senderName": "TM", "senderRole": "team-manager", "content": "Mgr sum", "isReview": True, "reviewId": rev_id})
        self.client.post("/api/chat/send", json={"convId": self.conv_id, "senderCode": "MA", "senderName": "MA", "senderRole": "main_agent", "content": "Main sum", "isReview": True, "reviewId": rev_id})
        r_blk = self.client.post(
            "/api/governance/submit_review",
            json={
                "convId": self.conv_id, "reviewId": rev_id,
                "managerSummary": "Mgr sum", "mainSummary": "Main sum",
                "confidence": 99, "recommendation": "complete",
                "continueReasons": ["None"], "completionReasons": ["Ready"], "evidence": ["unittest"],
            },
        )
        self.assertEqual(r_blk.status_code, 409)
        self.assertEqual(self.client.post("/api/findings/action", json={"convId": self.conv_id, "findingId": fid, "action": "wontfix", "reason": "Resolved in test"}).status_code, 200)
        r_ok = self.client.post(
            "/api/governance/submit_review",
            json={
                "convId": self.conv_id, "reviewId": rev_id,
                "managerSummary": "Mgr sum", "mainSummary": "Main sum",
                "confidence": 99, "recommendation": "complete",
                "continueReasons": ["None"], "completionReasons": ["Ready"], "evidence": ["unittest"],
            },
        )
        self.assertEqual(r_ok.status_code, 200, r_ok.text)
        self.assertTrue(r_ok.json()["thinkTank"]["isClosed"])
        self.assertIsNotNone(r_ok.json()["closureReceipt"])


if __name__ == "__main__":
    unittest.main()
