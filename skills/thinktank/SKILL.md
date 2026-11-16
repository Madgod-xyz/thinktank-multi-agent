---
name: thinktank
description: Launch an isolated ThinkTank v3 7+1 multi-agent Case Ledger session (/ThinkTank or /thinktank) with real subagent execution, WBS file locks, red-team critique, code review, and evidence-backed QA.
argument-hint: "[task or directive]"
---

# ThinkTank v3 Live Session Launcher (`/ThinkTank` & `/thinktank`)

Execute a clean, isolated ThinkTank v3 7+1 multi-agent session inside the active conversation without bleeding state from earlier runs. Both `/thinktank` and `/ThinkTank` activate through this bundled skill (`skills/thinktank/SKILL.md`) and `commands/thinktank.toml`.

## Execution Protocol

1. **Verify Backend & Bridge Runtime:**
   - Ensure the ThinkTank backend is reachable (`python tools/install_plugin.py --check --start-backend` from the plugin directory, or invoke the installed `~/.gemini/config/tools/thinktank_bridge.py`).
2. **Start an Isolated Run (`--new-run`):**
   - Log session routing with `triage --chosen thinktank --tt-reasons "..." --solo-reasons "..."`.
   - Start a fresh isolated run in the current conversation using `set-task --new-run --project "<Project>" --directive "<Directive>" --round 1 --progress 10` so any prior closed or active work archives cleanly (`--run-N`) with zero data bleed.
3. **Surface the Live Sidecar Panel:**
   - Include `[Live Think Tank](sidecar://team-orchestration-director/think-tank/)` in your response so the operator can track live progress.
4. **Execute the 5-Stage Closed-Loop Protocol with Real Subagents:**
   - Spawn real subagents from the canonical 7+1 team (`team-manager`, `council-critic`, `code-reviewer`, `qa-reviewer`, `ui-frontend-designer`, `backend-auditor`, `ecommerce_seo_operator`, `wp_technical_operator`) using `invoke_subagent`.
   - Tag every bridge event honestly with `--origin subagent --subagent-conv-id <SUBAGENT_CONV_ID>` inside real child subagent sessions (or `--origin main-proxy` when logged by the coordinator).
   - Follow WBS single-owner `--files` locks + `--acceptance` criteria, `PEER_SYNC` on `#sync`, `return-defect --repro` (`F-xx`), `worker-fix --finding F-xx`, 3-point `code-reviewer` audit + `qa-dispatch`, and evidence-backed `qa-report --finding F-xx --cmd ... --exit-code 0 --excerpt ... --runner substrate|host-fallback`.
5. **Hard Closure:**
   - Once all findings are `Verified` or `WontFix`, close the run via `thinktank_bridge.py complete --conv-id <CONV_ID> --summary "..."` to generate the read-only `closureReceipt`.
