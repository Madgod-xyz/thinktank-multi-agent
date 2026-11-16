---
name: think-room
description: Coordinate evidence-based coding, architectural design, red-team critique, supervisor interrogation, QA testing, and peer-to-peer worker sync in the Antigravity ThinkTank.
---

# ThinkTank Room Protocol

Use ThinkTank for **both heavier code development** (multi-file features, full-stack builds, complex refactors, UI/UX systems, WordPress/WooCommerce/SEO engineering) **and architectural/roadmap planning**.

## 1. Canonical 7+1 Team Architecture
- **Supervisors (Interrogation & Audit Authority):**
  - `team-manager` — WBS decomposition, ownership routing, progress interrogation, confidence gate.
  - `council-critic` — Ruthless flaw/regression/AI-slop hunter across plans, code, and workflows.
  - `code-reviewer` — Line-by-line code auditor who directly commands subordinate tester `qa-reviewer`.
- **Subordinate Tester under `code-reviewer`:**
  - `qa-reviewer` — Executes automated unit, integration, contract, UI/a11y tests and reports pass/fail evidence to `code-reviewer`.
- **Specialist Workers (`canPeerSync: true`):**
  - `ui-frontend-designer` — Sole frontend & design owner; enforces anti-AI-slop rules and design tokens.
  - `backend-auditor` — Sole backend, core logic, DB, API, cloud & security owner.
  - `ecommerce_seo_operator` — Product SEO, technical SEO, schema & high-CTR copywriting.
  - `wp_technical_operator` — WordPress & WooCommerce technical SRE, DB/Redis cache & catalog health.

## 2. Closed-Loop Remediation & Live Protocols (`#seq`, Findings & Channels)
0. **Triage & WBS Setup (`triage`, `assign-subtask` with single-owner file locks & acceptance criteria):**
   ```bash
   python tools/thinktank_bridge.py triage --conv-id <CONV_ID> --chosen thinktank --tt-reasons "<Reason 1>" "<Reason 2>" --solo-reasons "<Solo alternative>"
   python tools/thinktank_bridge.py assign-subtask --conv-id <CONV_ID> --title "<Task>" --assignee <worker> --files "<path/a>" "<path/b>" --acceptance "<Measurable pass condition>" --origin main-proxy
   ```
1. **Protocol A — Critic Defect Return -> Worker Fix (`RETURN_DEFECT` -> `WORKER_FIX` / `finding-action`):**
   Every bug/flaw uncovered by `council-critic` creates a tracked Finding (`F-01`..) and goes directly back to the responsible worker to fix before entering final code review:
   ```bash
   python tools/thinktank_bridge.py return-defect --conv-id <CONV_ID> --from council-critic --to <worker> --finding F-01 --severity HIGH --bug "<Exact defect>" --repro "<Exact reproduction steps>" --origin subagent
   python tools/thinktank_bridge.py finding-action --conv-id <CONV_ID> --finding F-01 --action ack|wontfix --reason "<Non-empty reason when wontfix>"
   python tools/thinktank_bridge.py worker-fix --conv-id <CONV_ID> --from <worker> --to code-reviewer --finding F-01 --fix "<Exact root-cause fix + modified files>" --origin subagent
   ```
2. **Protocol B — Code-Reviewer -> QA-Reviewer <-> Workers & Critic Troubleshooting (`QA_DISPATCH`, `REVIEW_QUERY`, `QA_REPORT`):**
   `code-reviewer` orders `qa-reviewer` to run concrete tests. `qa-reviewer` MUST attach executed command evidence (`--cmd`, `--exit-code`, `--runner`) for `PASS`:
   ```bash
   python tools/thinktank_bridge.py qa-dispatch --conv-id <CONV_ID> --to qa-reviewer --finding F-01 --scope "<Files/UI>" --checks "<Unit, API, Syntax, A11y>" --origin subagent
   python tools/thinktank_bridge.py review-query --conv-id <CONV_ID> --from qa-reviewer --to <worker|council-critic> --finding F-01 --question "<Specific failing check or edge case>" --origin subagent
   python tools/thinktank_bridge.py qa-report --conv-id <CONV_ID> --finding F-01 --status PASS|FAIL --summary "<Counts & outcome>" --cmd "<Executed command>" --exit-code 0 --excerpt "<Trimmed output>" --runner substrate --origin subagent
   ```
3. **Protocol C — Worker Peer-to-Peer Sync & Supervisor Interrogation (`PEER_SYNC` / `INTERROGATE`):**
   Workers synchronize schemas directly (`peer-sync`), and supervisors challenge weak spots anytime (`interrogate`).

## 3. Proactive Triage Rule on Heavier Tasks
Whenever a request involves substantial coding or complex planning:
- Explain **both sides** clearly to the user before launching the full team:
  1. **Reasons to Enter ThinkTank:** Explain specifically how WBS ownership, `council-critic` flaw hunting, line-by-line `code-reviewer` + `qa-reviewer` live testing, or dedicated UI/Backend/SEO/WP specialization raise output quality (for both **code development** and **planning/architecture**).
  2. **Reasons to Run Solo:** State honestly when the main agent alone can handle the task cohesively with lower latency and token overhead; recommend ThinkTank explicitly when multi-stage review is worthwhile, and let the user decide.

## 4. Consensus, Decision Card & Completion
- Record council stances via `vote-proposal` (`APPROVE`, `CONDITIONAL`, `CRITIQUE`, `REJECT`) with confidence `%`.
- Surface in-UI decision cards via `set-proposal` when user choices are needed.
- Always run `complete --conv-id <CONV_ID>` after final verification so all agents return to `IDLE` and progress reaches `100%`.
