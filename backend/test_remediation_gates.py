import atexit
import io
import json
import os
import re
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
AGENTS_DIR = PLUGIN_ROOT / "agents"

_TEST_TMP = tempfile.TemporaryDirectory(prefix="thinktank_gates_test_", ignore_cleanup_errors=True)
atexit.register(_TEST_TMP.cleanup)

os.environ["THINKTANK_HOME"] = _TEST_TMP.name
os.environ["THINKTANK_STATE_FILE"] = str(Path(_TEST_TMP.name) / "state.json")
os.environ["THINKTANK_SYNC_DB"] = str(Path(_TEST_TMP.name) / "sync.sqlite3")
os.environ["THINKTANK_SESSION_FILE"] = str(Path(_TEST_TMP.name) / "active_session.json")
os.environ["THINKTANK_ANTIGRAVITY_BRAIN_DIR"] = str(Path(_TEST_TMP.name) / "brain")

for _p in (str(BACKEND_DIR), str(TOOLS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from fastapi.testclient import TestClient  # noqa: E402
import app as backend_app  # noqa: E402
import install_plugin as plugin_installer  # noqa: E402
import thinktank_antigravity_hook as hook_bridge  # noqa: E402
import thinktank_bridge  # noqa: E402

EMOJI_PATTERN = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u26FF\u2700-\u27BF\u23F3\u21A9\uFE0F]")


class RemediationGatesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(backend_app.app)

    def setUp(self) -> None:
        self.conv_id = f"case-{self._testMethodName}"
        res = self.client.post(
            "/api/task/update",
            json={
                "convId": self.conv_id,
                "project": "TestProject",
                "directive": "Verify backend remediation gates",
                "status": "ACTIVE",
                "progress": 10,
                "round": 1,
            },
        )
        self.assertEqual(res.status_code, 200, res.text)

    def _create_finding(self, *, to_agent: str = "backend-auditor", round_num: int = 1, repro: str = "1. Call endpoint 2. Observe failure") -> str:
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

    # --- F-01: origin="subagent" validation + bridge warning + agent frontmatter/examples ---

    def test_f01_origin_validation_and_agent_docs(self) -> None:
        r_no_child = self.client.post(
            "/api/chat/send",
            json={
                "convId": self.conv_id,
                "senderCode": "BE",
                "senderName": "Backend",
                "senderRole": "backend-auditor",
                "content": "claimed subagent without child id",
                "origin": "subagent",
            },
        )
        self.assertEqual(r_no_child.status_code, 200, r_no_child.text)
        self.assertEqual(r_no_child.json()["message"]["origin"], "main-proxy")

        r_same_id = self.client.post(
            "/api/chat/send",
            json={
                "convId": self.conv_id,
                "senderCode": "BE",
                "senderName": "Backend",
                "senderRole": "backend-auditor",
                "content": "claimed subagent with parent id",
                "origin": "subagent",
                "subagentConvId": self.conv_id,
            },
        )
        self.assertEqual(r_same_id.status_code, 200, r_same_id.text)
        self.assertEqual(r_same_id.json()["message"]["origin"], "main-proxy")

        r_valid_child = self.client.post(
            "/api/chat/send",
            json={
                "convId": self.conv_id,
                "senderCode": "BE",
                "senderName": "Backend",
                "senderRole": "backend-auditor",
                "content": "genuine subagent event",
                "origin": "subagent",
                "subagentConvId": "child-conv-abc",
            },
        )
        self.assertEqual(r_valid_child.status_code, 200, r_valid_child.text)
        self.assertEqual(r_valid_child.json()["message"]["origin"], "subagent")

        r_inferred_child = self.client.post(
            "/api/chat/send",
            json={
                "convId": self.conv_id,
                "senderCode": "BE",
                "senderName": "Backend",
                "senderRole": "backend-auditor",
                "content": "inferred subagent from child id",
                "subagentConvId": "child-conv-xyz",
            },
        )
        self.assertEqual(r_inferred_child.status_code, 200, r_inferred_child.text)
        self.assertEqual(r_inferred_child.json()["message"]["origin"], "subagent")

        r_user = self.client.post(
            "/api/chat/send",
            json={
                "convId": self.conv_id,
                "senderCode": "USR",
                "senderName": "User",
                "senderRole": "human",
                "content": "user command",
            },
        )
        self.assertEqual(r_user.status_code, 200, r_user.text)
        self.assertEqual(r_user.json()["message"]["origin"], "user")

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ANTIGRAVITY_SUBAGENT_CONV_ID", None)
            err_buf = io.StringIO()
            with redirect_stderr(err_buf):
                resolved = thinktank_bridge._resolve_origin_fields("subagent", None)
            self.assertEqual(resolved, {"origin": "subagent"})
            self.assertIn("downgrade", err_buf.getvalue().lower())

        with patch.dict(os.environ, {"ANTIGRAVITY_SUBAGENT_CONV_ID": "env-child-77"}, clear=False):
            resolved_env = thinktank_bridge._resolve_origin_fields("subagent", None)
            self.assertEqual(resolved_env, {"origin": "subagent", "subagentConvId": "env-child-77"})

        agent_files = sorted(AGENTS_DIR.glob("*.md"))
        self.assertEqual(len(agent_files), 8)
        cli_subcmd_re = re.compile(
            r"thinktank_bridge\.py\b[^\n`]*(?:triage|peer-sync|return-defect|worker-fix|review-query|interrogate|qa-dispatch|qa-report|complete)\b"
        )
        for md_path in agent_files:
            text = md_path.read_text(encoding="utf-8")
            self.assertIn("enableWriteTools: true", text, f"Missing enableWriteTools in {md_path.name}")
            for idx, line in enumerate(text.splitlines(), 1):
                if cli_subcmd_re.search(line):
                    self.assertIn(
                        "--origin subagent --subagent-conv-id <CHILD_CONV_ID>",
                        line,
                        f"{md_path.name}:{idx} missing --origin subagent --subagent-conv-id <CHILD_CONV_ID>",
                    )

    # --- F-02: Strict Finding state machine, findingId requirement, and runnerReason ---

    def test_f02_finding_state_machine_and_evidence_gates(self) -> None:
        for action in ("WORKER_FIX", "QA_DISPATCH", "QA_REPORT"):
            r_missing = self.client.post(
                "/api/agent/collaborate",
                json={
                    "convId": self.conv_id,
                    "fromAgent": "backend-auditor",
                    "toAgent": "code-reviewer",
                    "action": action,
                    "content": "missing finding id",
                },
            )
            self.assertEqual(r_missing.status_code, 409, f"{action} without findingId: {r_missing.text}")

        for action in ("WORKER_FIX", "REVIEW_QUERY", "QA_DISPATCH", "QA_REPORT"):
            r_404 = self.client.post(
                "/api/agent/collaborate",
                json={
                    "convId": self.conv_id,
                    "fromAgent": "backend-auditor",
                    "toAgent": "code-reviewer",
                    "action": action,
                    "findingId": "F-99",
                    "content": "unknown finding",
                },
            )
            self.assertEqual(r_404.status_code, 404, f"{action} unknown finding: {r_404.text}")

        fid = self._create_finding()

        # Cannot QA_DISPATCH or QA_REPORT while Open
        for action in ("QA_DISPATCH", "QA_REPORT"):
            r_bad_state = self.client.post(
                "/api/agent/collaborate",
                json={
                    "convId": self.conv_id,
                    "fromAgent": "code-reviewer",
                    "toAgent": "qa-reviewer",
                    "action": action,
                    "findingId": fid,
                    "content": "premature QA",
                },
            )
            self.assertEqual(r_bad_state.status_code, 409, f"{action} on Open: {r_bad_state.text}")

        # WORKER_FIX: Open -> InReview
        r_fix = self.client.post(
            "/api/agent/collaborate",
            json={
                "convId": self.conv_id,
                "fromAgent": "backend-auditor",
                "toAgent": "code-reviewer",
                "action": "WORKER_FIX",
                "findingId": fid,
                "content": "Fixed root cause",
            },
        )
        self.assertEqual(r_fix.status_code, 200, r_fix.text)
        self.assertEqual(r_fix.json()["finding"]["state"], "InReview")

        # Verify InReview cannot skip QA_DISPATCH straight to QA_REPORT (409)
        r_skip_dispatch = self.client.post(
            "/api/agent/collaborate",
            json={
                "convId": self.conv_id,
                "fromAgent": "qa-reviewer",
                "toAgent": "code-reviewer",
                "action": "QA_REPORT",
                "findingId": fid,
                "result": "PASS",
                "evidenceCommand": "python -m unittest",
                "exitCode": 0,
                "runner": "substrate",
                "content": "skip dispatch",
            },
        )
        self.assertEqual(r_skip_dispatch.status_code, 409, r_skip_dispatch.text)

        # REVIEW_QUERY is allowed on InReview (without REJECT/HIGH stay in InReview)
        r_rq_ok = self.client.post(
            "/api/agent/collaborate",
            json={
                "convId": self.conv_id,
                "fromAgent": "code-reviewer",
                "toAgent": "backend-auditor",
                "action": "REVIEW_QUERY",
                "findingId": fid,
                "content": "Clarify guard ordering",
            },
        )
        self.assertEqual(r_rq_ok.status_code, 200, r_rq_ok.text)

        # Verify legacy lowercase state is tolerated case-insensitively and normalized back to CamelCase
        backend_app.conversations_store[self.conv_id]["findings"][0]["state"] = "inreview"

        # QA_DISPATCH: InReview -> Testing
        r_dispatch = self.client.post(
            "/api/agent/collaborate",
            json={
                "convId": self.conv_id,
                "fromAgent": "code-reviewer",
                "toAgent": "qa-reviewer",
                "action": "QA_DISPATCH",
                "findingId": fid,
                "content": "Run test suite",
            },
        )
        self.assertEqual(r_dispatch.status_code, 200, r_dispatch.text)
        self.assertEqual(r_dispatch.json()["finding"]["state"], "Testing")

        # host-fallback without runnerReason -> 409
        r_no_reason = self.client.post(
            "/api/agent/collaborate",
            json={
                "convId": self.conv_id,
                "fromAgent": "qa-reviewer",
                "toAgent": "code-reviewer",
                "action": "QA_REPORT",
                "findingId": fid,
                "result": "PASS",
                "evidenceCommand": "python -m unittest",
                "exitCode": 0,
                "evidenceExcerpt": "OK",
                "runner": "host-fallback",
                "runnerReason": "   ",
                "content": "PASS",
            },
        )
        self.assertEqual(r_no_reason.status_code, 409, r_no_reason.text)

        # PASS without exitCode==0 -> 409
        r_bad_exit = self.client.post(
            "/api/agent/collaborate",
            json={
                "convId": self.conv_id,
                "fromAgent": "qa-reviewer",
                "toAgent": "code-reviewer",
                "action": "QA_REPORT",
                "findingId": fid,
                "result": "PASS",
                "evidenceCommand": "python -m unittest",
                "exitCode": 1,
                "runner": "substrate",
                "content": "PASS",
            },
        )
        self.assertEqual(r_bad_exit.status_code, 409, r_bad_exit.text)

        # Valid QA_REPORT PASS with host-fallback + runnerReason -> Verified
        r_pass = self.client.post(
            "/api/agent/collaborate",
            json={
                "convId": self.conv_id,
                "fromAgent": "qa-reviewer",
                "toAgent": "code-reviewer",
                "action": "QA_REPORT",
                "findingId": fid,
                "result": "PASS",
                "evidenceCommand": "python -m unittest",
                "exitCode": 0,
                "evidenceExcerpt": "Ran 1 test - OK",
                "runner": "host-fallback",
                "runnerReason": "Windows plugin localhost integration test",
                "content": "PASS",
            },
        )
        self.assertEqual(r_pass.status_code, 200, r_pass.text)
        self.assertEqual(r_pass.json()["finding"]["state"], "Verified")

        # Once Verified, WORKER_FIX / QA_DISPATCH / QA_REPORT / REVIEW_QUERY are rejected (409)
        for action in ("WORKER_FIX", "QA_DISPATCH", "QA_REPORT", "REVIEW_QUERY"):
            r_after_verify = self.client.post(
                "/api/agent/collaborate",
                json={
                    "convId": self.conv_id,
                    "fromAgent": "qa-reviewer",
                    "toAgent": "code-reviewer",
                    "action": action,
                    "findingId": fid,
                    "content": "invalid after verify",
                },
            )
            self.assertEqual(r_after_verify.status_code, 409, f"{action} on Verified: {r_after_verify.text}")

        # RETURN_DEFECT on existing finding requires non-empty reproSteps, updates trimmed text, and blocks Closed/WontFix
        fid2 = self._create_finding()
        r_reopen_no_repro = self.client.post(
            "/api/agent/collaborate",
            json={
                "convId": self.conv_id,
                "fromAgent": "council-critic",
                "toAgent": "backend-auditor",
                "action": "RETURN_DEFECT",
                "findingId": fid2,
                "severity": "HIGH",
                "reproSteps": "   ",
                "question": "",
                "content": "reopen missing repro",
            },
        )
        self.assertEqual(r_reopen_no_repro.status_code, 409, r_reopen_no_repro.text)

        r_reopen_ok = self.client.post(
            "/api/agent/collaborate",
            json={
                "convId": self.conv_id,
                "fromAgent": "council-critic",
                "toAgent": "backend-auditor",
                "action": "RETURN_DEFECT",
                "findingId": fid2,
                "severity": "HIGH",
                "reproSteps": "  1. Retry POST 2. Verify trimmed save  ",
                "content": "reopen with repro",
            },
        )
        self.assertEqual(r_reopen_ok.status_code, 200, r_reopen_ok.text)
        self.assertEqual(r_reopen_ok.json()["finding"]["state"], "Fixing")
        self.assertEqual(r_reopen_ok.json()["finding"]["reproSteps"], "1. Retry POST 2. Verify trimmed save")

        r_wontfix = self.client.post(
            "/api/findings/action",
            json={"convId": self.conv_id, "findingId": fid2, "action": "wontfix", "reason": "Duplicate"},
        )
        self.assertEqual(r_wontfix.status_code, 200, r_wontfix.text)
        for terminal_state in ("WontFix", "Closed"):
            backend_app.conversations_store[self.conv_id]["findings"][1]["state"] = terminal_state
            r_terminal = self.client.post(
                "/api/agent/collaborate",
                json={
                    "convId": self.conv_id,
                    "fromAgent": "council-critic",
                    "toAgent": "backend-auditor",
                    "action": "RETURN_DEFECT",
                    "findingId": fid2,
                    "severity": "HIGH",
                    "reproSteps": "1. Still rejected",
                    "content": f"reject on {terminal_state}",
                },
            )
            self.assertEqual(r_terminal.status_code, 409, r_terminal.text)
            r_rq_terminal = self.client.post(
                "/api/agent/collaborate",
                json={
                    "convId": self.conv_id,
                    "fromAgent": "code-reviewer",
                    "toAgent": "backend-auditor",
                    "action": "REVIEW_QUERY",
                    "findingId": fid2,
                    "content": f"query on {terminal_state}",
                },
            )
            self.assertEqual(r_rq_terminal.status_code, 409, r_rq_terminal.text)

        # CLI parser enforces required --finding on worker-fix, qa-dispatch, qa-report
        for argv in (
            ["thinktank_bridge.py", "--conv-id", "c1", "worker-fix", "--fix", "fixed"],
            ["thinktank_bridge.py", "--conv-id", "c1", "qa-dispatch", "--scope", "api", "--checks", "unit"],
            ["thinktank_bridge.py", "--conv-id", "c1", "qa-report", "--status", "PASS", "--cmd", "pytest", "--exit-code", "0", "--excerpt", "ok"],
        ):
            with patch.object(sys, "argv", argv), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as ctx:
                    thinktank_bridge.main()
            self.assertNotEqual(ctx.exception.code, 0)

    # --- F-03: Closed case read-only guard, reopen, and resetCase ---

    def test_f03_closed_case_readonly_reopen_and_reset(self) -> None:
        fid = self._create_finding()
        self.client.post(
            "/api/agent/collaborate",
            json={"convId": self.conv_id, "fromAgent": "backend-auditor", "toAgent": "code-reviewer", "action": "WORKER_FIX", "findingId": fid, "content": "fix"},
        )
        self.client.post(
            "/api/agent/collaborate",
            json={"convId": self.conv_id, "fromAgent": "code-reviewer", "toAgent": "qa-reviewer", "action": "QA_DISPATCH", "findingId": fid, "content": "check"},
        )
        self.client.post(
            "/api/agent/collaborate",
            json={
                "convId": self.conv_id,
                "fromAgent": "qa-reviewer",
                "toAgent": "code-reviewer",
                "action": "QA_REPORT",
                "findingId": fid,
                "result": "PASS",
                "evidenceCommand": "unittest",
                "exitCode": 0,
                "evidenceExcerpt": "OK",
                "runner": "substrate",
                "content": "PASS",
            },
        )

        r_close = self.client.post(
            "/api/task/update",
            json={
                "convId": self.conv_id,
                "status": "COMPLETED",
                "progress": 100,
                "summary": "All gates passed.",
                "origin": "subagent",
                "subagentConvId": "tm-child-1",
            },
        )
        self.assertEqual(r_close.status_code, 200, r_close.text)
        status_closed = self.client.get("/api/status", params={"convId": self.conv_id}).json()
        self.assertTrue(status_closed["thinkTank"]["isClosed"])
        self.assertIsNotNone(status_closed["thinkTank"]["closureReceipt"])
        self.assertEqual(status_closed["findings"][0]["state"], "Closed")
        self.assertIn("All gates passed.", status_closed["messages"][-1]["content"])
        self.assertEqual(status_closed["messages"][-1]["origin"], "subagent")

        write_calls = [
            ("/api/agent/update", {"convId": self.conv_id, "id": "backend-auditor", "status": "ACTIVE"}),
            ("/api/chat/send", {"convId": self.conv_id, "senderCode": "BE", "senderName": "Backend", "senderRole": "backend-auditor", "content": "blocked"}),
            ("/api/agent/collaborate", {"convId": self.conv_id, "fromAgent": "backend-auditor", "toAgent": "ui-frontend-designer", "action": "PEER_SYNC", "content": "blocked"}),
            ("/api/subtasks/upsert", {"convId": self.conv_id, "title": "Blocked", "assignee": "backend-auditor", "acceptanceCriteria": "none"}),
            ("/api/findings/action", {"convId": self.conv_id, "findingId": fid, "action": "ack"}),
            ("/api/proposal/update", {"convId": self.conv_id, "id": "p1", "project": "TestProject", "title": "P", "author": "TM", "summary": "S"}),
            ("/api/proposal/action", {"convId": self.conv_id, "action": "approve"}),
            ("/api/proposal/vote", {"convId": self.conv_id, "voter": "council-critic", "stance": "APPROVE", "comment": "ok"}),
            ("/api/governance/extend_rounds", {"convId": self.conv_id, "additionalRounds": 3}),
            ("/api/governance/compress_final", {"convId": self.conv_id}),
        ]
        for path, body in write_calls:
            resp = self.client.post(path, json=body)
            self.assertEqual(resp.status_code, 409, f"{path} should return 409 when closed, got {resp.status_code}: {resp.text}")

        # Reopen via /api/governance/reopen
        r_reopen = self.client.post("/api/governance/reopen", json={"convId": self.conv_id})
        self.assertEqual(r_reopen.status_code, 200, r_reopen.text)
        status_reopened = self.client.get("/api/status", params={"convId": self.conv_id}).json()
        self.assertFalse(status_reopened["thinkTank"]["isClosed"])
        self.assertIsNone(status_reopened["thinkTank"]["closureReceipt"])
        self.assertEqual(status_reopened["thinkTank"]["status"], "ACTIVE")
        self.assertEqual(status_reopened["findings"][0]["state"], "Verified")

        # Write succeeds again
        r_write_ok = self.client.post(
            "/api/chat/send",
            json={"convId": self.conv_id, "senderCode": "BE", "senderName": "Backend", "senderRole": "backend-auditor", "content": "reopened ok"},
        )
        self.assertEqual(r_write_ok.status_code, 200, r_write_ok.text)

        # Close and reopen via /api/task/update(reopen=True)
        self.assertEqual(self.client.post("/api/task/update", json={"convId": self.conv_id, "status": "COMPLETED", "progress": 100}).status_code, 200)
        self.assertEqual(self.client.post("/api/task/update", json={"convId": self.conv_id, "reopen": True}).status_code, 200)
        self.assertFalse(self.client.get("/api/status", params={"convId": self.conv_id}).json()["thinkTank"]["isClosed"])

        # Seed stale telemetry across all 3 channels before resetCase to verify F-02 reset matches default_telemetry_store
        self.assertEqual(
            self.client.post(
                "/api/telemetry/tool_call",
                json={"convId": self.conv_id, "agentId": "backend-auditor", "tool": "pytest", "output": "ok"},
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                "/api/telemetry/terminal_log",
                json={"convId": self.conv_id, "agentId": "backend-auditor", "command": "python -m unittest", "output": "OK", "exitCode": 0},
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                "/api/telemetry/task",
                json={"convId": self.conv_id, "id": "task-1", "agentId": "backend-auditor", "title": "QA", "command": "pytest"},
            ).status_code,
            200,
        )
        pre_tel = self.client.get("/api/telemetry", params={"convId": self.conv_id}).json()
        self.assertEqual(len(pre_tel["toolCalls"]), 1)
        self.assertEqual(len(pre_tel["terminalLogs"]), 1)
        self.assertEqual(len(pre_tel["backgroundTasks"]), 1)

        # resetCase wipes case state cleanly
        r_reset = self.client.post("/api/task/update", json={"convId": self.conv_id, "resetCase": True})
        self.assertEqual(r_reset.status_code, 200, r_reset.text)
        status_reset = self.client.get("/api/status", params={"convId": self.conv_id}).json()
        self.assertFalse(status_reset["thinkTank"]["isClosed"])
        self.assertIsNone(status_reset["thinkTank"]["closureReceipt"])
        self.assertEqual(status_reset["thinkTank"]["status"], "ACTIVE")
        self.assertEqual(status_reset["thinkTank"]["round"], 1)
        self.assertEqual(status_reset["thinkTank"]["progress"], 5)
        self.assertIsNone(status_reset["thinkTank"].get("triageDecision"))
        self.assertEqual(status_reset["findings"], [])
        self.assertEqual(status_reset["subtasks"], [])
        self.assertEqual(status_reset["messages"], [])
        self.assertEqual(status_reset["collaborations"], [])
        self.assertEqual(status_reset["interactions"], [])
        self.assertEqual(status_reset["fileLocks"], [])
        self.assertIsNone(status_reset["proposal"])
        self.assertEqual(status_reset["telemetry"], {"toolCalls": [], "terminalLogs": [], "backgroundTasks": []})
        self.assertEqual(
            self.client.get("/api/telemetry", params={"convId": self.conv_id}).json(),
            {"toolCalls": [], "terminalLogs": [], "backgroundTasks": []},
        )
        self.assertIsNone(status_reset.get("review"))

    # --- F-04: roleCaps enforced in both /api/chat/send and /api/agent/collaborate + WS roleUsage ---

    def test_f04_role_caps_enforced_across_chat_and_collaborate(self) -> None:
        broadcasts = []
        orig_broadcast = backend_app.manager.broadcast

        async def _capture_broadcast(data):
            broadcasts.append(data)
            return await orig_broadcast(data)

        with patch.object(backend_app.manager, "broadcast", side_effect=_capture_broadcast):
            r_caps = self.client.post(
                "/api/task/update",
                json={"convId": self.conv_id, "roleCaps": {"main": 2, "manager": 2, "subagents": 2}},
            )
            self.assertEqual(r_caps.status_code, 200, r_caps.text)

            for i in range(2):
                r_ok = self.client.post(
                    "/api/agent/collaborate",
                    json={
                        "convId": self.conv_id,
                        "fromAgent": "backend-auditor",
                        "toAgent": "ui-frontend-designer",
                        "action": "PEER_SYNC",
                        "content": f"sync {i}",
                    },
                )
                self.assertEqual(r_ok.status_code, 200, r_ok.text)

            r_collab_429 = self.client.post(
                "/api/agent/collaborate",
                json={
                    "convId": self.conv_id,
                    "fromAgent": "backend-auditor",
                    "toAgent": "ui-frontend-designer",
                    "action": "PEER_SYNC",
                    "content": "over cap",
                },
            )
            self.assertEqual(r_collab_429.status_code, 429, r_collab_429.text)

            r_chat_429 = self.client.post(
                "/api/chat/send",
                json={
                    "convId": self.conv_id,
                    "senderCode": "BE",
                    "senderName": "Backend",
                    "senderRole": "backend-auditor",
                    "content": "over subagents cap via chat",
                },
            )
            self.assertEqual(r_chat_429.status_code, 429, r_chat_429.text)

            # Manager cap: 2 regular messages ok, review message exempt, 3rd non-review message -> 429
            for i in range(2):
                r_mgr = self.client.post(
                    "/api/chat/send",
                    json={
                        "convId": self.conv_id,
                        "senderCode": "TM",
                        "senderName": "Team Manager",
                        "senderRole": "team-manager",
                        "content": f"mgr {i}",
                    },
                )
                self.assertEqual(r_mgr.status_code, 200, r_mgr.text)

            backend_app.conversations_store[self.conv_id]["review"] = {
                "id": "rev-cap-exempt",
                "status": "AWAITING_TEAM_REVIEW",
            }
            r_review_exempt = self.client.post(
                "/api/chat/send",
                json={
                    "convId": self.conv_id,
                    "senderCode": "TM",
                    "senderName": "Team Manager",
                    "senderRole": "team-manager",
                    "content": "review check-in",
                    "isReview": True,
                    "reviewId": "rev-cap-exempt",
                },
            )
            self.assertEqual(r_review_exempt.status_code, 200, r_review_exempt.text)

            r_mgr_429 = self.client.post(
                "/api/chat/send",
                json={
                    "convId": self.conv_id,
                    "senderCode": "TM",
                    "senderName": "Team Manager",
                    "senderRole": "team-manager",
                    "content": "over manager cap",
                },
            )
            self.assertEqual(r_mgr_429.status_code, 429, r_mgr_429.text)

            self.assertEqual(
                self.client.post(
                    "/api/proposal/update",
                    json={"convId": self.conv_id, "id": "p1", "project": "TestProject", "title": "P", "author": "TM", "summary": "S"},
                ).status_code,
                200,
            )
            self.assertEqual(
                self.client.post(
                    "/api/proposal/vote",
                    json={"convId": self.conv_id, "voter": "council-critic", "stance": "APPROVE", "comment": "ok"},
                ).status_code,
                200,
            )

        checked_types = {"STATE_UPDATE", "NEW_MESSAGE", "COLLABORATION_UPDATE", "PROPOSAL_UPDATE"}
        matching = [b for b in broadcasts if b.get("type") in checked_types]
        self.assertGreaterEqual(len(matching), 8)
        for payload in matching:
            self.assertIsInstance(payload.get("roleUsage"), dict, f"Missing roleUsage in {payload.get('type')}")

    # --- F-05: requestType alignment, allowlist validation, and CLI --request-type ---

    def test_f05_request_type_alignment_and_bridge_flag(self) -> None:
        self.assertEqual(backend_app._infer_request_type("QA_DISPATCH", None), "QA_REPORT")
        self.assertEqual(backend_app._infer_request_type("ASSIGN_SUBTASK", None), "REFERRAL")
        self.assertEqual(backend_app._infer_request_type("SUBTASK_UPDATE", None), "REFERRAL")
        self.assertEqual(backend_app._infer_request_type("QA_REOPEN", None), "DEFECT_RETURN")
        for decision_action in ("PROPOSAL", "COMPLETE", "GOVERNANCE", "DECIDE"):
            self.assertEqual(backend_app._infer_request_type(decision_action, None), "DECISION")
        self.assertEqual(backend_app._infer_request_type("RETURN_DEFECT", "bogus_type"), "DEFECT_RETURN")
        self.assertEqual(backend_app._infer_request_type("PEER_SYNC", "question"), "QUESTION")

        fid = self._create_finding()
        self.client.post(
            "/api/agent/collaborate",
            json={"convId": self.conv_id, "fromAgent": "backend-auditor", "toAgent": "code-reviewer", "action": "WORKER_FIX", "findingId": fid, "content": "fixed"},
        )
        r_dispatch = self.client.post(
            "/api/agent/collaborate",
            json={"convId": self.conv_id, "fromAgent": "code-reviewer", "toAgent": "qa-reviewer", "action": "QA_DISPATCH", "findingId": fid, "content": "test it"},
        )
        self.assertEqual(r_dispatch.status_code, 200, r_dispatch.text)
        self.assertEqual(r_dispatch.json()["message"]["requestType"], "QA_REPORT")

        captured = []
        argv = [
            "thinktank_bridge.py",
            "--conv-id",
            self.conv_id,
            "peer-sync",
            "--from",
            "backend-auditor",
            "--to",
            "ui-frontend-designer",
            "--topic",
            "API",
            "--summary",
            "Contract",
            "--request-type",
            "QUESTION",
        ]
        with patch.object(sys, "argv", argv), patch.object(
            thinktank_bridge,
            "api_post",
            side_effect=lambda ep, data, cid=None: captured.append((ep, data, cid)) or {"status": "ok"},
        ), redirect_stdout(io.StringIO()):
            thinktank_bridge.main()
        self.assertEqual(captured[0][0], "agent/collaborate")
        self.assertEqual(captured[0][1]["requestType"], "QUESTION")
        self.assertEqual(captured[0][2], self.conv_id)

    # --- F-06: Zero Unicode emojis in backend/app.py & tools/thinktank_bridge.py ---

    def test_f06_zero_unicode_emojis(self) -> None:
        targets = [PLUGIN_ROOT / "backend/app.py", PLUGIN_ROOT / "tools/thinktank_bridge.py"]
        skills_dir = PLUGIN_ROOT / "skills"
        if skills_dir.is_dir():
            targets.extend(p for p in sorted(skills_dir.rglob("*.md")) if "_archived" not in p.parts)
        for path in targets:
            content = path.read_text(encoding="utf-8")
            matches = EMOJI_PATTERN.findall(content)
            self.assertEqual(matches, [], f"Emoji(s) found in {path.relative_to(PLUGIN_ROOT)}: {matches}")

    # --- F-07: RETURN_DEFECT severity allowlist, reproSteps requirement, max 7 findings per round ---

    def test_f07_critic_severity_repro_and_round_cap(self) -> None:
        r_bad_sev = self.client.post(
            "/api/agent/collaborate",
            json={
                "convId": self.conv_id,
                "fromAgent": "council-critic",
                "toAgent": "backend-auditor",
                "action": "RETURN_DEFECT",
                "severity": "LOW",
                "reproSteps": "1. Do X",
                "content": "Low defect",
            },
        )
        self.assertEqual(r_bad_sev.status_code, 400, r_bad_sev.text)

        r_no_repro = self.client.post(
            "/api/agent/collaborate",
            json={
                "convId": self.conv_id,
                "fromAgent": "council-critic",
                "toAgent": "backend-auditor",
                "action": "RETURN_DEFECT",
                "severity": "HIGH",
                "reproSteps": "   ",
                "question": "",
                "content": "Missing repro",
            },
        )
        self.assertEqual(r_no_repro.status_code, 409, r_no_repro.text)

        for i in range(7):
            fid = self._create_finding(round_num=1, repro=f"1. Repro {i}")
            self.assertEqual(fid, f"F-{i + 1:02d}")

        r_8th = self.client.post(
            "/api/agent/collaborate",
            json={
                "convId": self.conv_id,
                "fromAgent": "council-critic",
                "toAgent": "backend-auditor",
                "action": "RETURN_DEFECT",
                "severity": "MEDIUM",
                "reproSteps": "1. 8th defect",
                "content": "Too many in round 1",
            },
        )
        self.assertEqual(r_8th.status_code, 409, r_8th.text)

        self.assertEqual(
            self.client.post("/api/task/update", json={"convId": self.conv_id, "round": 2}).status_code,
            200,
        )
        fid_r2 = self._create_finding(round_num=2, repro="1. Round 2 defect")
        self.assertEqual(fid_r2, "F-08")
        findings = self.client.get("/api/status", params={"convId": self.conv_id}).json()["findings"]
        self.assertEqual(findings[-1]["round"], 2)

    # --- F-20: bridge_transport.py parity, install_plugin sync, ?conv_id= fallback ---

    def test_f20_transport_parity_installer_and_conv_id_fallback(self) -> None:
        self.assertEqual(
            (BACKEND_DIR / "bridge_transport.py").read_bytes(),
            (TOOLS_DIR / "bridge_transport.py").read_bytes(),
        )

        r_get = self.client.get("/api/status", params={"conv_id": self.conv_id})
        self.assertEqual(r_get.status_code, 200, r_get.text)
        self.assertEqual(r_get.json()["convId"], self.conv_id)

        r_post = self.client.post(f"/api/status?conv_id={self.conv_id}", json={})
        self.assertEqual(r_post.status_code, 200, r_post.text)
        self.assertEqual(r_post.json()["convId"], self.conv_id)

        r_tel = self.client.get("/api/telemetry", params={"conv_id": self.conv_id})
        self.assertEqual(r_tel.status_code, 200, r_tel.text)
        self.assertIn("toolCalls", r_tel.json())

        with tempfile.TemporaryDirectory(prefix="tt_install_test_") as tmp_target:
            target = Path(tmp_target)
            sidecar_targets = (
                target / "plugins" / "team-orchestration-director" / "sidecars" / "think-tank",
                target / "thinktank" / "sidecars" / "think-tank",
            )
            for sc_dir in sidecar_targets:
                (sc_dir / "assets" / "fonts").mkdir(parents=True, exist_ok=True)
                (sc_dir / "assets" / "avatars").mkdir(parents=True, exist_ok=True)
                (sc_dir / "roles.css").write_text("/* stale */", encoding="utf-8")
                (sc_dir / "tailwind.js").write_text("// stale", encoding="utf-8")
                (sc_dir / "assets" / "fonts" / "stale.woff2").write_bytes(b"stale")
                (sc_dir / "assets" / "avatars" / "legacy-stale-avatar.svg").write_text("<svg/>", encoding="utf-8")
            stale_archived = target / "plugins" / "team-orchestration-director" / "agents" / "_archived"
            stale_archived.mkdir(parents=True, exist_ok=True)
            (stale_archived / "old.md").write_text("old", encoding="utf-8")
            stale_pack = target / "plugins" / "team-orchestration-director" / "data-evidence-pack"
            stale_pack.mkdir(parents=True, exist_ok=True)
            (stale_pack / "old.txt").write_text("old", encoding="utf-8")
            stale_agent = target / "plugins" / "team-orchestration-director" / "agents" / "council-architect.md"
            stale_agent.parent.mkdir(parents=True, exist_ok=True)
            stale_agent.write_text("# stale", encoding="utf-8")
            stale_cmd = target / "plugins" / "team-orchestration-director" / "commands" / "obsolete.toml"
            stale_cmd.parent.mkdir(parents=True, exist_ok=True)
            stale_cmd.write_text("description = 'stale'\n", encoding="utf-8")

            install_res = plugin_installer.install_plugin(PLUGIN_ROOT, target)
            self.assertTrue(install_res["hooksInstalled"])
            self.assertTrue((target / "plugins" / "team-orchestration-director" / "backend" / "app.py").is_file())
            self.assertTrue((target / "thinktank" / "backend" / "app.py").is_file())
            self.assertTrue((target / "thinktank" / "backend" / "bridge_transport.py").is_file())
            self.assertTrue((target / "thinktank" / "sidecars" / "think-tank" / "index.html").is_file())
            self.assertTrue((target / "tools" / "thinktank_bridge.py").is_file())
            self.assertTrue((target / "tools" / "thinktank_antigravity_hook.py").is_file())
            self.assertTrue((target / "tools" / "install_antigravity_hook.py").is_file())
            self.assertTrue((target / "commands" / "thinktank.toml").is_file())
            self.assertTrue((target / "hooks.json").is_file())
            runtime_meta = json.loads((target / "thinktank" / "runtime.json").read_text(encoding="utf-8"))
            self.assertEqual(runtime_meta["pythonExecutable"], str(Path(sys.executable)))
            self.assertFalse(stale_archived.exists())
            self.assertFalse(stale_pack.exists())
            self.assertFalse(stale_agent.exists())
            self.assertFalse(stale_cmd.exists())

            src_avatars = {
                p.name for p in (PLUGIN_ROOT / "sidecars" / "think-tank" / "assets" / "avatars").glob("*.svg")
            }
            for sc_dir in sidecar_targets:
                self.assertFalse((sc_dir / "roles.css").exists())
                self.assertFalse((sc_dir / "tailwind.js").exists())
                self.assertFalse((sc_dir / "assets" / "fonts").exists())
                self.assertFalse((sc_dir / "assets" / "avatars" / "legacy-stale-avatar.svg").exists())
                for svg_name in src_avatars:
                    self.assertTrue((sc_dir / "assets" / "avatars" / svg_name).is_file())

    def test_multi_run_isolation_and_real_subagent_tracking(self) -> None:
        base_cid = "aaaaaaaa-1111-2222-3333-444444444444"
        broadcasts = []
        orig_broadcast = backend_app.manager.broadcast

        async def _capture_broadcast(data):
            broadcasts.append(data)
            return await orig_broadcast(data)

        with patch.object(backend_app.manager, "broadcast", side_effect=_capture_broadcast):
            # --- 1. Three consecutive isolated runs on the same conversation ---
            r1_task = self.client.post(
                "/api/task/update",
                json={
                    "convId": base_cid,
                    "project": "Run1Project",
                    "directive": "First run objective",
                    "status": "ACTIVE",
                    "progress": 20,
                    "round": 1,
                },
            )
            self.assertEqual(r1_task.status_code, 200, r1_task.text)
            self.assertEqual(r1_task.json()["thinkTank"]["runIndex"], 1)

            r1_sub = self.client.post(
                "/api/subtasks/upsert",
                json={
                    "convId": base_cid,
                    "title": "Run 1 Subtask",
                    "assignee": "backend-auditor",
                    "status": "IN_PROGRESS",
                    "acceptanceCriteria": "Pass unit tests",
                    "origin": "subagent",
                    "subagentConvId": "sub-run1-tm",
                },
            )
            self.assertEqual(r1_sub.status_code, 200, r1_sub.text)

            r1_def = self.client.post(
                "/api/agent/collaborate",
                json={
                    "convId": base_cid,
                    "fromAgent": "council-critic",
                    "toAgent": "backend-auditor",
                    "action": "RETURN_DEFECT",
                    "severity": "HIGH",
                    "reproSteps": "1. Reproduce in run 1",
                    "content": "Run 1 defect",
                    "origin": "subagent",
                    "subagentConvId": "sub-run1-cc",
                },
            )
            self.assertEqual(r1_def.status_code, 200, r1_def.text)
            self.assertEqual(r1_def.json()["finding"]["id"], "F-01")
            self.assertEqual(
                self.client.post(
                    "/api/agent/collaborate",
                    json={"convId": base_cid, "fromAgent": "backend-auditor", "toAgent": "code-reviewer", "action": "WORKER_FIX", "findingId": "F-01", "content": "Fixed run 1"},
                ).status_code,
                200,
            )
            self.assertEqual(
                self.client.post(
                    "/api/agent/collaborate",
                    json={"convId": base_cid, "fromAgent": "code-reviewer", "toAgent": "qa-reviewer", "action": "QA_DISPATCH", "findingId": "F-01", "content": "Test run 1"},
                ).status_code,
                200,
            )
            self.assertEqual(
                self.client.post(
                    "/api/agent/collaborate",
                    json={
                        "convId": base_cid,
                        "fromAgent": "qa-reviewer",
                        "toAgent": "code-reviewer",
                        "action": "QA_REPORT",
                        "findingId": "F-01",
                        "result": "PASS",
                        "evidenceCommand": "python -m unittest",
                        "exitCode": 0,
                        "evidenceExcerpt": "OK",
                        "runner": "substrate",
                        "content": "PASS",
                    },
                ).status_code,
                200,
            )
            r1_close = self.client.post(
                "/api/task/update",
                json={"convId": base_cid, "status": "COMPLETED", "progress": 100, "summary": "Run 1 complete"},
            )
            self.assertEqual(r1_close.status_code, 200, r1_close.text)

            # Triage on closed run archives Run 1 -> --run-1 and prepares Run 2 without reopening Run 1
            r2_triage = self.client.post(
                "/api/task/update",
                json={"convId": base_cid, "triageDecision": {"chosen": "thinktank", "thinktankReasons": ["Multi-role"]}},
            )
            self.assertEqual(r2_triage.status_code, 200, r2_triage.text)
            self.assertEqual(r2_triage.json()["archivedRunId"], f"{base_cid}--run-1")
            self.assertEqual(r2_triage.json()["thinkTank"]["runIndex"], 2)

            # Immediate set-task --new-run right after triage must NOT archive an empty --run-2
            r2_task = self.client.post(
                "/api/task/update",
                json={
                    "convId": base_cid,
                    "project": "Run2Project",
                    "directive": "Second run objective",
                    "status": "ACTIVE",
                    "progress": 15,
                    "round": 1,
                    "newRun": True,
                },
            )
            self.assertEqual(r2_task.status_code, 200, r2_task.text)
            self.assertIsNone(r2_task.json()["archivedRunId"])
            self.assertEqual(r2_task.json()["thinkTank"]["runIndex"], 2)
            self.assertNotIn(f"{base_cid}--run-2", backend_app.conversations_store)

            # Add Run 2 work so Run 2 has findings/messages
            r2_def = self.client.post(
                "/api/agent/collaborate",
                json={
                    "convId": base_cid,
                    "fromAgent": "council-critic",
                    "toAgent": "ui-frontend-designer",
                    "action": "RETURN_DEFECT",
                    "severity": "MEDIUM",
                    "reproSteps": "1. Reproduce in run 2",
                    "content": "Run 2 defect",
                    "origin": "subagent",
                    "subagentConvId": "sub-run2-cc",
                },
            )
            self.assertEqual(r2_def.status_code, 200, r2_def.text)
            self.assertEqual(r2_def.json()["finding"]["id"], "F-01")

            # Starting Run 3 with newRun=True (even if targeting archived --run-1) normalizes to base_cid and archives Run 2
            r3_task = self.client.post(
                "/api/task/update",
                json={
                    "convId": f"{base_cid}--run-1",
                    "project": "Run3Project",
                    "directive": "Third run objective",
                    "status": "ACTIVE",
                    "progress": 10,
                    "round": 1,
                    "newRun": True,
                },
            )
            self.assertEqual(r3_task.status_code, 200, r3_task.text)
            self.assertEqual(r3_task.json()["convId"], base_cid)
            self.assertEqual(r3_task.json()["archivedRunId"], f"{base_cid}--run-2")
            self.assertEqual(r3_task.json()["thinkTank"]["runIndex"], 3)

        # Verify zero bleed across runs 1, 2, and 3
        st_r3 = self.client.get("/api/status", params={"convId": base_cid}).json()
        self.assertEqual(st_r3["thinkTank"]["runIndex"], 3)
        self.assertEqual(st_r3["thinkTank"]["project"], "Run3Project")
        self.assertEqual(st_r3["findings"], [])
        self.assertEqual(st_r3["subtasks"], [])
        self.assertEqual(st_r3["messages"], [])
        self.assertFalse(st_r3["isClosed"])

        st_r1 = self.client.get("/api/status", params={"convId": f"{base_cid}--run-1"}).json()
        self.assertEqual(st_r1["thinkTank"]["runIndex"], 1)
        self.assertEqual(st_r1["thinkTank"]["project"], "Run1Project")
        self.assertTrue(st_r1["isClosed"])
        self.assertEqual(len(st_r1["subtasks"]), 1)
        self.assertEqual(len(st_r1["findings"]), 1)
        self.assertEqual(st_r1["findings"][0]["title"], "Run 1 defect")

        st_r2 = self.client.get("/api/status", params={"convId": f"{base_cid}--run-2"}).json()
        self.assertEqual(st_r2["thinkTank"]["runIndex"], 2)
        self.assertEqual(st_r2["thinkTank"]["project"], "Run2Project")
        self.assertTrue(st_r2["isClosed"])
        self.assertEqual(len(st_r2["findings"]), 1)
        self.assertEqual(st_r2["findings"][0]["title"], "Run 2 defect")

        # Verify _build_conv_row metadata & STATE_UPDATE conversationsList
        row_map = {row["id"]: row for row in st_r3["conversationsList"]}
        self.assertEqual(row_map[base_cid]["runIndex"], 3)
        self.assertEqual(row_map[base_cid]["parentConvId"], base_cid)
        self.assertFalse(row_map[base_cid]["isArchivedRun"])
        self.assertFalse(row_map[base_cid]["isClosed"])
        self.assertEqual(row_map[f"{base_cid}--run-1"]["runIndex"], 1)
        self.assertEqual(row_map[f"{base_cid}--run-1"]["parentConvId"], base_cid)
        self.assertTrue(row_map[f"{base_cid}--run-1"]["isArchivedRun"])
        self.assertTrue(row_map[f"{base_cid}--run-1"]["isClosed"])
        self.assertEqual(row_map[f"{base_cid}--run-2"]["runIndex"], 2)
        self.assertTrue(row_map[f"{base_cid}--run-2"]["isArchivedRun"])

        state_updates = [b for b in broadcasts if b.get("type") == "STATE_UPDATE" and b.get("convId") == base_cid]
        self.assertTrue(state_updates)
        self.assertIsInstance(state_updates[-1].get("conversationsList"), list)
        self.assertEqual(state_updates[-1]["thinkTank"]["runIndex"], 3)

        # Verify bridge CLI --new-run flag
        captured_cli = []
        argv = [
            "thinktank_bridge.py",
            "--conv-id",
            base_cid,
            "set-task",
            "--new-run",
            "--project",
            "CLIProject",
            "--directive",
            "CLI new run",
        ]
        with patch.object(sys, "argv", argv), patch.object(
            thinktank_bridge,
            "api_post",
            side_effect=lambda ep, data, cid=None: captured_cli.append((ep, data, cid)) or {"status": "updated"},
        ), redirect_stdout(io.StringIO()):
            thinktank_bridge.main()
        self.assertEqual(captured_cli[0][0], "task/update")
        self.assertTrue(captured_cli[0][1].get("newRun"))

        # --- 2. Real Subagent Activation & Live Telemetry Routing ---
        for raw_prefix, expected_role in (
            ("tt-backend-auditor", "backend-auditor"),
            ("tt-ui-frontend-designer", "ui-frontend-designer"),
            ("tt-council-critic", "council-critic"),
            ("tt-code-reviewer", "code-reviewer"),
            ("tt-qa-reviewer", "qa-reviewer"),
            ("tt-ecommerce_seo_operator", "ecommerce_seo_operator"),
            ("tt-wp_technical_operator", "wp_technical_operator"),
        ):
            self.assertEqual(backend_app.normalize_agent_id(raw_prefix), expected_role)

        self.assertEqual(
            self.client.post("/api/host/active-session", json={"conversationId": base_cid}).status_code,
            200,
        )

        child_uuid = "11111111-2222-3333-4444-555555555555"
        r_invoke = self.client.post(
            "/api/telemetry/host_tool",
            json={
                "id": "tool-invoke-1",
                "convId": base_cid,
                "tool": "invoke_subagent",
                "status": "SUCCESS",
                "stepIdx": 1,
                "args": {"TypeName": "tt-ui-frontend-designer", "Role": "Design Case Ledger UI"},
                "output": f"Started subagent ({base_cid}) child conversation {child_uuid}",
            },
        )
        self.assertEqual(r_invoke.status_code, 200, r_invoke.text)
        self.assertIn(child_uuid, backend_app.subagent_session_map)
        self.assertEqual(backend_app.subagent_session_map[child_uuid]["parentConvId"], base_cid)
        self.assertEqual(backend_app.subagent_session_map[child_uuid]["roleId"], "ui-frontend-designer")

        st_after_invoke = self.client.get("/api/status", params={"convId": base_cid}).json()
        ui_agent = next(a for a in st_after_invoke["agents"] if a["id"] == "ui-frontend-designer")
        self.assertEqual(ui_agent["status"], "WORKING")
        self.assertTrue(ui_agent["verifiedSubagent"])
        self.assertEqual(ui_agent["subagentConvId"], child_uuid)
        self.assertEqual(ui_agent["tool"], "invoke_subagent")
        self.assertEqual(ui_agent["turnsUsed"], 1)

        # Child active-session callback must remap back to parent base_cid
        r_child_active = self.client.post("/api/host/active-session", json={"conversationId": child_uuid})
        self.assertEqual(r_child_active.status_code, 200, r_child_active.text)
        self.assertEqual(r_child_active.json()["activeConversationId"], base_cid)
        self.assertEqual(backend_app.active_conv_id, base_cid)

        # Even if active_session.json has child_uuid, GET /api/status remaps it to base_cid
        session_file = Path(os.environ["THINKTANK_SESSION_FILE"])
        session_file.write_text(f'{{"conversationId": "{child_uuid}"}}', encoding="utf-8")
        st_default = self.client.get("/api/status").json()
        self.assertEqual(st_default["convId"], base_cid)

        # Child tool execution routes telemetry & WORKING status back to parent under ui-frontend-designer
        r_child_tool = self.client.post(
            "/api/telemetry/host_tool",
            json={
                "id": "tool-child-read-1",
                "convId": child_uuid,
                "tool": "read_file",
                "status": "SUCCESS",
                "stepIdx": 2,
                "args": {"Path": "sidecars/think-tank/app.js"},
                "output": "file contents",
                "agentId": "antigravity",
                "agentName": "Antigravity",
            },
        )
        self.assertEqual(r_child_tool.status_code, 200, r_child_tool.text)
        self.assertEqual(r_child_tool.json()["convId"], base_cid)
        self.assertEqual(r_child_tool.json()["entry"]["agentId"], "ui-frontend-designer")
        self.assertEqual(r_child_tool.json()["entry"]["subagentConvId"], child_uuid)
        self.assertNotIn(child_uuid, backend_app.conversations_store)

        # Parent send_message to child_uuid updates ui-frontend-designer
        r_send_msg = self.client.post(
            "/api/telemetry/host_tool",
            json={
                "id": "tool-send-msg-1",
                "convId": base_cid,
                "tool": "send_message",
                "status": "SUCCESS",
                "stepIdx": 3,
                "args": {"Recipient": child_uuid, "Message": "Sync tokens"},
                "output": "sent",
            },
        )
        self.assertEqual(r_send_msg.status_code, 200, r_send_msg.text)
        st_after_child = self.client.get("/api/status", params={"convId": base_cid}).json()
        ui_agent2 = next(a for a in st_after_child["agents"] if a["id"] == "ui-frontend-designer")
        self.assertEqual(ui_agent2["status"], "WORKING")
        self.assertEqual(ui_agent2["tool"], "send_message")
        self.assertEqual(ui_agent2["turnsUsed"], 3)

        # Verify subagent_session_map survives save/load reload
        backend_app.subagent_session_map = {}
        backend_app.load_persisted_state()
        self.assertIn(child_uuid, backend_app.subagent_session_map)
        self.assertEqual(backend_app.subagent_session_map[child_uuid]["roleId"], "ui-frontend-designer")

    def test_f01_f05_brain_discovery_and_settings_rename_safety(self) -> None:
        brain_dir = Path(os.environ["THINKTANK_ANTIGRAVITY_BRAIN_DIR"])
        session_file = Path(os.environ["THINKTANK_SESSION_FILE"])
        links_file = session_file.with_name("subagent_links.json")
        if links_file.exists():
            links_file.unlink()

        parent_uuid = "bbbbbbbb-1111-2222-3333-444444444444"
        child_be = "cccccccc-1111-2222-3333-444444444444"
        child_ui = "dddddddd-1111-2222-3333-444444444444"

        # Build synthetic brain transcripts matching Antigravity's JSONL schema
        parent_log = brain_dir / parent_uuid / ".system_generated" / "logs" / "transcript.jsonl"
        parent_log.parent.mkdir(parents=True, exist_ok=True)
        parent_lines = [
            json.dumps({"step_index": 0, "source": "USER_EXPLICIT", "type": "USER_INPUT", "content": "Build ThinkTank"}),
            json.dumps({
                "step_index": 1,
                "source": "MODEL",
                "type": "PLANNER_RESPONSE",
                "tool_calls": [
                    {"name": "invoke_subagent", "args": {"TypeName": '"tt-backend-auditor"', "Role": '"Backend Specialist"'}},
                    {"name": "invoke_subagent", "args": {"TypeName": '"tt-ui-frontend-designer"', "Role": '"UI Specialist"'}},
                ],
                "content": "",
            }),
            json.dumps({
                "step_index": 2,
                "source": "MODEL",
                "type": "GENERIC",
                "content": (
                    f'Created the following subagent:\n{{\n  "conversationId": "{child_be}",\n'
                    f'  "logAbsoluteUri": "file:///brain/{child_be}/.system_generated/logs/transcript.jsonl"\n}}'
                ),
            }),
            json.dumps({
                "step_index": 3,
                "source": "MODEL",
                "type": "GENERIC",
                "content": (
                    f'Created the following subagent:\n{{\n  "conversationId": "{child_ui}",\n'
                    f'  "logAbsoluteUri": "file:///brain/{child_ui}/.system_generated/logs/transcript.jsonl"\n}}'
                ),
            }),
        ]
        parent_log.write_text("\n".join(parent_lines) + "\n", encoding="utf-8")

        for child_id in (child_be, child_ui):
            clog = brain_dir / child_id / ".system_generated" / "logs" / "transcript.jsonl"
            clog.parent.mkdir(parents=True, exist_ok=True)
            clog.write_text(
                json.dumps({"step_index": 0, "source": "SYSTEM_SDK", "type": "EPHEMERAL_MESSAGE", "content": "init"})
                + "\n"
                + json.dumps({"step_index": 1, "source": "SYSTEM", "type": "SYSTEM_MESSAGE", "content": "task"})
                + "\n",
                encoding="utf-8",
            )

        # Initialize parent ThinkTank run & session file
        self.assertEqual(
            self.client.post(
                "/api/task/update",
                json={"convId": parent_uuid, "project": "BrainParentProject", "directive": "Audit brain routing", "status": "ACTIVE"},
            ).status_code,
            200,
        )
        session_file.write_text(json.dumps({"conversationId": parent_uuid}), encoding="utf-8")

        # 1. Hook PreInvocation for child_ui discovers parent_uuid without overwriting session_file
        with patch.object(hook_bridge, "_post_active_session") as mock_post_active:
            resp = hook_bridge.build_response("pre-invocation", {"conversationId": child_ui})
        self.assertIn(f"parent conversation ID: {parent_uuid}", resp["injectSteps"][0]["ephemeralMessage"])
        self.assertIn(f"--conv-id {parent_uuid} --origin subagent --subagent-conv-id {child_ui}", resp["injectSteps"][0]["ephemeralMessage"])
        self.assertEqual(json.loads(session_file.read_text(encoding="utf-8"))["conversationId"], parent_uuid)
        mock_post_active.assert_called_once()
        posted_active = mock_post_active.call_args[0][0]
        self.assertEqual(posted_active["parentConversationId"], parent_uuid)
        self.assertEqual(posted_active["roleId"], "ui-frontend-designer")

        tool_ev = hook_bridge.build_tool_event(
            {"conversationId": child_ui, "stepIdx": 2, "toolCall": {"name": "read_file", "args": {"Path": "app.js"}}, "output": "ok"}
        )
        self.assertEqual(tool_ev["parentConversationId"], parent_uuid)
        self.assertEqual(tool_ev["roleId"], "ui-frontend-designer")

        # Human parent session must NOT be misclassified as a child
        self.assertEqual(hook_bridge._discover_parent_from_brain(parent_uuid), (None, None, None))

        # 2. Live Antigravity PostToolUse(invoke_subagent) with empty output + child active-session + REPRO-C GET /api/status?convId=child_be
        self.assertEqual(
            self.client.post(
                "/api/telemetry/host_tool",
                json={
                    "id": "invoke-empty-out",
                    "convId": parent_uuid,
                    "tool": "invoke_subagent",
                    "status": "SUCCESS",
                    "stepIdx": 1,
                    "args": {"TypeName": "tt-backend-auditor", "Role": "Backend Specialist"},
                    "output": "",
                },
            ).status_code,
            200,
        )
        r_child_be_active = self.client.post("/api/host/active-session", json={"conversationId": child_be})
        self.assertEqual(r_child_be_active.status_code, 200, r_child_be_active.text)
        self.assertEqual(r_child_be_active.json()["activeConversationId"], parent_uuid)
        self.assertNotIn(child_be, backend_app.conversations_store)

        # REPRO-C: GET /api/status?convId=<child_be> returns parent session, never phantom empty child
        st_child_be = self.client.get("/api/status", params={"convId": child_be}).json()
        self.assertEqual(st_child_be["convId"], parent_uuid)
        self.assertTrue(st_child_be["hasSession"])
        self.assertEqual(st_child_be["thinkTank"]["project"], "BrainParentProject")
        be_agent = next(a for a in st_child_be["agents"] if a["id"] == "backend-auditor")
        self.assertEqual(be_agent["status"], "WORKING")
        self.assertTrue(be_agent["verifiedSubagent"])
        self.assertEqual(be_agent["subagentConvId"], child_be)

        # Phantom cleanup on load_persisted_state()
        backend_app.conversations_store[child_be] = backend_app.create_empty_conversation(child_be)
        backend_app.load_persisted_state()
        self.assertNotIn(child_be, backend_app.conversations_store)

        # 3. F-05: Fresh Run #2 stays visible in conversationsList while viewing --run-1, and Settings rename does NOT wipe active work
        f5_cid = "eeeeeeee-1111-2222-3333-444444444444"
        self.assertEqual(
            self.client.post(
                "/api/task/update",
                json={"convId": f5_cid, "project": "OrigProject", "directive": "Run 1", "status": "ACTIVE", "round": 1},
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                "/api/subtasks/upsert",
                json={"convId": f5_cid, "title": "Active task", "assignee": "backend-auditor", "acceptanceCriteria": "Done"},
            ).status_code,
            200,
        )
        # Settings rename while ACTIVE must update in-place without archiving or wiping subtasks
        r_rename = self.client.post(
            "/api/task/update",
            json={"convId": f5_cid, "project": "RenamedFromSettings", "directive": "Run 1 renamed", "round": 1},
        )
        self.assertEqual(r_rename.status_code, 200, r_rename.text)
        self.assertIsNone(r_rename.json()["archivedRunId"])
        st_renamed = self.client.get("/api/status", params={"convId": f5_cid}).json()
        self.assertEqual(st_renamed["thinkTank"]["runIndex"], 1)
        self.assertEqual(st_renamed["thinkTank"]["project"], "RenamedFromSettings")
        self.assertEqual(len(st_renamed["subtasks"]), 1)

        # Explicit --new-run creates Run #2 (empty except status=ACTIVE, runIndex=2, parentConvId=f5_cid)
        r_new_run = self.client.post(
            "/api/task/update",
            json={"convId": f5_cid, "newRun": True, "status": "ACTIVE", "round": 1},
        )
        self.assertEqual(r_new_run.status_code, 200, r_new_run.text)
        self.assertEqual(r_new_run.json()["archivedRunId"], f"{f5_cid}--run-1")

        # Negative check: empty runIndex=1 session touched only by host_tool (status=ACTIVE, no parentConvId/work) stays hidden
        telemetry_only_cid = "ffffffff-1111-2222-3333-444444444444"
        self.assertEqual(
            self.client.post(
                "/api/telemetry/host_tool",
                json={
                    "id": "host-only-1",
                    "convId": telemetry_only_cid,
                    "tool": "read_file",
                    "status": "SUCCESS",
                    "stepIdx": 0,
                    "args": {},
                    "output": "ok",
                },
            ).status_code,
            200,
        )
        self.assertEqual(backend_app.conversations_store[telemetry_only_cid]["thinkTank"]["status"], "ACTIVE")
        legacy_empty_cid = "12121212-1111-2222-3333-444444444444"
        legacy_conv = backend_app.create_empty_conversation(legacy_empty_cid)
        legacy_conv["parentConvId"] = legacy_empty_cid
        legacy_conv["thinkTank"]["runIndex"] = 1
        backend_app.conversations_store[legacy_empty_cid] = legacy_conv

        # Viewing --run-1 must still show Run #2 (f5_cid) in conversationsList, but NOT telemetry_only_cid or legacy_empty_cid
        # Even if parent transcript mentions f"{f5_cid}--run-1" or another conversation UUID outside invoke_subagent, neither may be misclassified as a child subagent.
        with open(parent_log, "a", encoding="utf-8") as fp:
            fp.write(
                json.dumps({"step_index": 4, "source": "MODEL", "type": "GENERIC", "content": f"Checked {f5_cid}--run-1 and {legacy_empty_cid}"})
                + "\n"
            )
        st_f5_run1 = self.client.get("/api/status", params={"convId": f"{f5_cid}--run-1"}).json()
        self.assertEqual(st_f5_run1["convId"], f"{f5_cid}--run-1")
        self.assertEqual(st_f5_run1["thinkTank"]["runIndex"], 1)
        self.assertEqual(hook_bridge._discover_parent_from_brain(f"{f5_cid}--run-1"), (None, None, None))
        st_viewing_run1 = self.client.get("/api/status", params={"convId": f"{f5_cid}--run-1"}).json()
        listed_ids = {row["id"] for row in st_viewing_run1["conversationsList"]}
        self.assertIn(f"{f5_cid}--run-1", listed_ids)
        self.assertIn(f5_cid, listed_ids)
        self.assertNotIn(telemetry_only_cid, listed_ids)
        self.assertNotIn(legacy_empty_cid, listed_ids)
        convs_api = self.client.get("/api/conversations").json()["conversations"]
        convs_api_ids = {row["id"] for row in convs_api}
        self.assertNotIn(telemetry_only_cid, convs_api_ids)
        self.assertNotIn(legacy_empty_cid, convs_api_ids)

    def test_workspace_scoped_host_context_sync_snapshot_and_cli_alias(self) -> None:
        ws_b_cid = "bbbbbbbb-1111-2222-3333-444444444444"
        ws_a_cid = "aaaaaaaa-1111-2222-3333-444444444444"
        ws_b_uri = "file:///c:/workspaces/project-beta"
        ws_a_uri = "file:///c:/workspaces/project-alpha"

        # Seed active ThinkTank case bound to workspace B
        self.assertEqual(
            self.client.post(
                "/api/task/update",
                json={"convId": ws_b_cid, "project": "Workspace Beta", "directive": "Blotters", "status": "ACTIVE", "progress": 20},
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                "/api/host/active-session",
                json={"conversationId": ws_b_cid, "workspaceUri": ws_b_uri},
            ).status_code,
            200,
        )
        # Later tool call in Workspace A must NOT hijack Workspace B host/context lookup
        self.assertEqual(
            self.client.post(
                "/api/host/active-session",
                json={"conversationId": ws_a_cid, "workspaceUri": ws_a_uri},
            ).status_code,
            200,
        )
        ctx_b = self.client.get("/api/host/context", params={"workspaceUri": "file:///c%3A/workspaces/project-beta/"}).json()
        self.assertEqual(ctx_b["conversationId"], ws_b_cid)
        self.assertTrue(ctx_b["hasSession"])

        # Negative cross-workspace test: workspace C must NOT inherit active_conv_id bound to workspace A/B
        ctx_c = self.client.get("/api/host/context", params={"workspaceUri": "file:///c:/workspaces/project-gamma"}).json()
        self.assertEqual(ctx_c["conversationId"], "")
        self.assertFalse(ctx_c["workspaceMatched"])
        self.assertFalse(ctx_c["hasSession"])

        # Archived --run-1 must carry isArchivedRun and never override active Run #2 in workspace lookup
        self.assertEqual(
            self.client.post(
                "/api/chat/send",
                json={"convId": ws_b_cid, "channel": "MAIN", "senderCode": "TM", "senderName": "Manager", "senderRole": "team-manager", "content": "Run 1 work"},
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                "/api/task/update",
                json={"convId": ws_b_cid, "newRun": True, "project": "Workspace Beta Run 2", "directive": "Run 2", "status": "ACTIVE"},
            ).status_code,
            200,
        )
        self.assertTrue(backend_app.conversations_store[f"{ws_b_cid}--run-1"].get("isArchivedRun"))
        self.assertEqual(backend_app._resolve_workspace_conv_id(ws_b_uri), ws_b_cid)

        # workspaceUri must be persisted to SQLite sync_store and restored on load_persisted_state()
        loaded_convs = backend_app.sync_store.load_conversations()
        self.assertEqual(
            backend_app._normalize_workspace_key(loaded_convs[ws_b_cid]["snapshot"].get("workspaceUri")),
            backend_app._normalize_workspace_key(ws_b_uri),
        )
        backend_app.sessions_by_workspace.clear()
        backend_app.load_persisted_state()
        self.assertEqual(
            backend_app.sessions_by_workspace[backend_app._normalize_workspace_key(ws_b_uri)]["conversationId"],
            ws_b_cid,
        )

        # WebSocket SYNC_SNAPSHOT includes hasSession, parentConvId, and conversationsList
        with self.client.websocket_connect(f"/ws?convId={ws_b_cid}") as ws:
            ready = ws.receive_json()
            self.assertEqual(ready["type"], "SYNC_READY")
            snap_msg = ws.receive_json()
            self.assertEqual(snap_msg["type"], "SYNC_SNAPSHOT")
            self.assertEqual(snap_msg["convId"], ws_b_cid)
            self.assertEqual(snap_msg["parentConvId"], ws_b_cid)
            self.assertTrue(snap_msg["hasSession"])
            self.assertTrue(any(row["id"] == ws_b_cid for row in snap_msg["conversationsList"]))

        # Hook record_active_session records sessionsByWorkspace without storing workspace URI into projectId
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            sess_file = tmp / "active_antigravity_session.json"
            with patch.dict(
                os.environ,
                {"THINKTANK_SESSION_FILE": str(sess_file), "THINKTANK_ANTIGRAVITY_BRAIN_DIR": str(tmp / "brain")},
            ), patch.object(hook_bridge, "_post_active_session"):
                hook_bridge.record_active_session(ws_b_cid, {"workspace": ws_b_uri})
                hook_bridge.record_active_session(ws_a_cid, {"workspace": ws_a_uri, "projectId": "proj-alpha"})
            saved = json.loads(sess_file.read_text(encoding="utf-8"))
            self.assertEqual(saved["conversationId"], ws_a_cid)
            self.assertEqual(saved["projectId"], "proj-alpha")
            self.assertIsNone(saved["sessionsByWorkspace"][hook_bridge._normalize_workspace_uri(ws_b_uri)]["projectId"])
            self.assertEqual(
                saved["sessionsByWorkspace"][hook_bridge._normalize_workspace_uri(ws_b_uri)]["conversationId"],
                ws_b_cid,
            )
            # Unpersisted active_antigravity_session.json workspaceUri must still block cross-workspace fallback
            unpersisted_cid = "cccccccc-1111-2222-3333-444444444444"
            sess_file.write_text(
                json.dumps({"conversationId": unpersisted_cid, "workspaceUri": ws_a_uri, "sessionsByWorkspace": {}}),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"THINKTANK_SESSION_FILE": str(sess_file)}):
                ctx_other = self.client.get("/api/host/context", params={"workspaceUri": "file:///c:/workspaces/project-delta"}).json()
                self.assertEqual(ctx_other["conversationId"], "")
                self.assertFalse(ctx_other["workspaceMatched"])
                st_other = self.client.get("/api/status", params={"workspaceUri": "file:///c:/workspaces/project-delta"}).json()
                self.assertEqual(st_other["convId"], "default")
                self.assertFalse(st_other["hasSession"])

        # CLI update-agent accepts 'agent-state' alias cleanly
        proc = subprocess.run(
            [sys.executable, str(TOOLS_DIR / "thinktank_bridge.py"), "agent-state", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("--id", proc.stdout)

    def test_deep_tracking_sync_latency_and_non_hijack(self) -> None:
        # 1. Lightweight /api/health endpoint
        for ep in ("/api/health", "/health"):
            res = self.client.get(ep)
            self.assertEqual(res.status_code, 200)
            body = res.json()
            self.assertTrue(body["ok"])
            self.assertEqual(body["syncMode"], "durable-websocket")

        # 2. Same-workspace active ThinkTank case must NOT be hijacked by background plain tab or post-tool-use
        ws_uri = "file:///c:/workspaces/shared-ws"
        tt_cid = "11111111-aaaa-2222-3333-444444444444"
        plain_cid = "22222222-bbbb-3333-4444-555555555555"

        self.assertEqual(
            self.client.post(
                "/api/task/update",
                json={"convId": tt_cid, "project": "Shared WS Case", "directive": "Keep pinned", "status": "ACTIVE", "progress": 30},
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                "/api/host/active-session",
                json={"conversationId": tt_cid, "workspaceUri": ws_uri, "eventSource": "pre-invocation"},
            ).status_code,
            200,
        )
        seq_before = backend_app.sync_store.cursor(tt_cid)["seq"]

        # WebSocket connect with projectId & repeated host/active-session must NOT create seq gaps
        with self.client.websocket_connect(f"/ws?convId={tt_cid}&projectId=proj-shared") as _:
            pass
        self.assertEqual(backend_app.sync_store.cursor(tt_cid)["seq"], seq_before)

        # High-volume host_tool on active ThinkTank conv compacts output/args and does not add SQLite TELEMETRY_UPDATE bloat rows
        for step_idx in range(30):
            r_tool = self.client.post(
                "/api/telemetry/host_tool",
                json={
                    "id": f"bulk-{step_idx}",
                    "convId": tt_cid,
                    "tool": "read_file",
                    "status": "SUCCESS",
                    "stepIdx": step_idx,
                    "args": {"Prompt": "x" * 600, "Path": "backend/app.py"},
                    "output": "y" * 800,
                },
            )
            self.assertEqual(r_tool.status_code, 200)
        tel_after = self.client.get("/api/telemetry", params={"convId": tt_cid}).json()
        self.assertEqual(len(tel_after["toolCalls"]), 25)
        self.assertLessEqual(len(tel_after["toolCalls"][0]["output"]), 240)
        self.assertLessEqual(len(tel_after["toolCalls"][0]["args"]["Prompt"]), 160)
        self.assertEqual(backend_app.sync_store.cursor(tt_cid)["seq"], seq_before)

        # Next durable chat events advance seq contiguously over live WebSocket without gaps
        with self.client.websocket_connect(f"/ws?convId={tt_cid}&projectId=proj-shared") as ws_live:
            _ = ws_live.receive_json()  # SYNC_READY
            _ = ws_live.receive_json()  # SYNC_SNAPSHOT
            r_chat = self.client.post(
                "/api/chat/send",
                json={"convId": tt_cid, "channel": "MAIN", "senderCode": "TM", "senderName": "Manager", "senderRole": "team-manager", "content": "Contiguous seq"},
            )
            self.assertEqual(r_chat.status_code, 200)
            ev1 = ws_live.receive_json()
            ev2 = ws_live.receive_json()
            self.assertEqual([ev1["seq"], ev2["seq"]], [seq_before + 1, seq_before + 2])
            self.assertEqual(backend_app.sync_store.cursor(tt_cid)["seq"], seq_before + 2)

        # Background non-ThinkTank tab in same workspace sending host_tool + active-session cannot steal host/context
        self.assertEqual(
            self.client.post(
                "/api/telemetry/host_tool",
                json={"id": "plain-1", "convId": plain_cid, "tool": "run_command", "status": "SUCCESS", "stepIdx": 0, "args": {}, "output": "ok"},
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                "/api/host/active-session",
                json={"conversationId": plain_cid, "workspaceUri": ws_uri, "eventSource": "post-tool-use"},
            ).status_code,
            200,
        )
        self.assertFalse(backend_app.has_thinktank_activity(backend_app.conversations_store[plain_cid]))
        ctx = self.client.get("/api/host/context", params={"workspaceUri": ws_uri}).json()
        self.assertEqual(ctx["conversationId"], tt_cid)
        self.assertTrue(ctx["hasSession"])

        # Hook post-tool-use preserves existing workspace session owner and trims oversized args/output
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            sess_file = tmp / "active_antigravity_session.json"
            with patch.dict(
                os.environ,
                {"THINKTANK_SESSION_FILE": str(sess_file), "THINKTANK_ANTIGRAVITY_BRAIN_DIR": str(tmp / "brain")},
            ), patch.object(hook_bridge, "_post_active_session"):
                hook_bridge.record_active_session(tt_cid, {"workspace": ws_uri}, event_source="pre-invocation")
                hook_bridge.record_active_session(plain_cid, {"workspace": ws_uri}, event_source="post-tool-use")
                # post-tool-use with missing workspaceUri (norm_ws=None) also must NOT overwrite top-level conversationId
                hook_bridge.record_active_session(plain_cid, {}, event_source="post-tool-use")
            saved = json.loads(sess_file.read_text(encoding="utf-8"))
            self.assertEqual(saved["conversationId"], tt_cid)
            self.assertEqual(
                saved["sessionsByWorkspace"][hook_bridge._normalize_workspace_uri(ws_uri)]["conversationId"],
                tt_cid,
            )
            compact_ev = hook_bridge.build_tool_event(
                {
                    "conversationId": plain_cid,
                    "stepIdx": 5,
                    "toolCall": {"name": "edit_file", "args": {"Target": "z" * 500}},
                    "output": "o" * 700,
                }
            )
            self.assertLessEqual(len(compact_ev["args"]["Target"]), 200)
            self.assertLessEqual(len(compact_ev["output"]), 300)

        # Cross-project guard & new unassigned binding on /api/host/active-session
        proj_bound_cid = "33333333-cccc-4444-5555-666666666666"
        self.assertEqual(
            self.client.post(
                "/api/host/active-session",
                headers={"X-ThinkTank-Project-Id": "proj-alpha"},
                json={"conversationId": proj_bound_cid, "workspaceUri": "file:///c:/workspaces/proj-bound"},
            ).status_code,
            200,
        )
        self.assertEqual(backend_app.conversations_store[proj_bound_cid].get("projectId"), "proj-alpha")
        self.assertEqual(
            self.client.post(
                "/api/task/update",
                headers={"X-ThinkTank-Project-Id": "proj-alpha"},
                json={"convId": proj_bound_cid, "project": "Bound", "directive": "Safe", "status": "ACTIVE", "progress": 10},
            ).status_code,
            200,
        )
        r_hijack = self.client.post(
            "/api/host/active-session",
            headers={"X-ThinkTank-Project-Id": "proj-beta"},
            json={"conversationId": proj_bound_cid, "workspaceUri": "file:///c:/workspaces/hijack"},
        )
        self.assertEqual(r_hijack.status_code, 403)
        self.assertNotIn("55555555-eeee-6666-7777-888888888888", backend_app.conversations_store)
        r_hijack_new = self.client.post(
            "/api/host/active-session",
            headers={"X-ThinkTank-Project-Id": "proj-beta"},
            json={"conversationId": "55555555-eeee-6666-7777-888888888888", "workspaceUri": "file:///c:/workspaces/hijack2"},
        )
        self.assertEqual(r_hijack_new.status_code, 200)

        # Closing tt_cid lets a newly started ThinkTank case in the SAME workspace take over
        self.assertEqual(
            self.client.post(
                "/api/task/update",
                json={"convId": tt_cid, "status": "COMPLETED", "progress": 100, "forceClose": True, "forceReason": "Done"},
            ).status_code,
            200,
        )
        tt_next_cid = "44444444-dddd-5555-6666-777777777777"
        self.assertEqual(
            self.client.post(
                "/api/task/update",
                json={"convId": tt_next_cid, "project": "Next Tab Case", "directive": "New work", "status": "ACTIVE", "progress": 15},
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                "/api/host/active-session",
                json={"conversationId": tt_next_cid, "workspaceUri": ws_uri, "eventSource": "post-tool-use"},
            ).status_code,
            200,
        )
        ctx_next = self.client.get("/api/host/context", params={"workspaceUri": ws_uri}).json()
        self.assertEqual(ctx_next["conversationId"], tt_next_cid)

        # 3. SyncEventStore.prune_bloat removes legacy TELEMETRY_UPDATE rows & trims bloated snapshots
        with tempfile.TemporaryDirectory(prefix="tt_prune_test_") as tmp_db_dir:
            db_path = Path(tmp_db_dir) / "bloat.sqlite3"
            store = backend_app.SyncEventStore(str(db_path), retention=150)
            try:
                bloated_snap = {
                    "id": tt_cid,
                    "thinkTank": {"project": "Kept", "status": "ACTIVE"},
                    "messages": [{"id": "m1", "content": "Keep me"}],
                    "telemetry": {
                        "toolCalls": [{"id": f"c{i}", "output": "B" * 900, "args": {"Prompt": "A" * 500}} for i in range(40)],
                        "terminalLogs": [],
                        "backgroundTasks": [],
                    },
                }
                store.commit(
                    conversation_id=tt_cid,
                    event_id="ev-msg-1",
                    event_type="NEW_MESSAGE",
                    payload={"content": "Keep me"},
                    snapshot=bloated_snap,
                )
                for idx in range(5):
                    store.commit(
                        conversation_id=tt_cid,
                        event_id=f"ev-tel-{idx}",
                        event_type="TELEMETRY_UPDATE",
                        payload={"telemetry": bloated_snap["telemetry"]},
                        snapshot=bloated_snap,
                    )
                stats = store.prune_bloat(telemetry_keep=10, vacuum=True)
                self.assertEqual(stats["deletedTelemetryRows"], 5)
                self.assertEqual(stats["compactedSnapshots"], 1)
                loaded = store.load_conversations()[tt_cid]["snapshot"]
                self.assertEqual(loaded["messages"][0]["content"], "Keep me")
                self.assertEqual(len(loaded["telemetry"]["toolCalls"]), 10)
                self.assertLessEqual(len(loaded["telemetry"]["toolCalls"][0]["output"]), 240)
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
