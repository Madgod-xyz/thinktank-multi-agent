# ThinkTank Plugin Agent Rules (`AGENTS.md`)

## Team Structure (7 Core Roles + 1 Subordinate QA Tester)
- **Supervisors (`canInterrogate: true`):**
  - `team-manager` — WBS task breakdown, orchestration, and progress accountability.
  - `council-critic` — Exclusively discovers flaws, edge cases, regressions, security gaps, and AI slop.
  - `code-reviewer` — Audits diffs line by line and commands `qa-reviewer`.
- **Subordinate Tester (`reportsTo: code-reviewer`):**
  - `qa-reviewer` — Executes concrete tests and reports verified results to `code-reviewer`.
- **Specialist Workers (`canPeerSync: true`):**
  - `ui-frontend-designer` — Sole frontend & design architect; enforces Hallmark anti-AI-slop rules and accessibility.
  - `backend-auditor` — Sole backend, core logic, API, database, cloud, and security engineer.
  - `ecommerce_seo_operator` — Product SEO, technical SEO, schema, and high-CTR e-commerce copywriting.
  - `wp_technical_operator` — WordPress & WooCommerce SRE, database/Redis tuning, and store operations.

## Proactive Triage Rule & Provenance (Code Development & Architecture/Planning)
Whenever a user requests a non-trivial or heavy task—whether **code development** (building features, full-stack work, UI redesign, complex debugging) or **planning/architecture**:
- Evaluate honestly whether entering ThinkTank adds concrete value.
- Present **both perspectives clearly** before starting:
  1. Why **ThinkTank** is helpful here (e.g., WBS split with single-owner file locks, `council-critic` flaw hunting, `code-reviewer` + `qa-reviewer` 3-point review & Evidence-backed live tests, `ui-frontend-designer` Case Ledger craft, parallel backend/UI/SEO/WP sync).
  2. Why the **Main Agent alone** can also complete it directly with lower latency/token cost—explicitly stating if ThinkTank isn't strictly necessary, OR clearly recommending ThinkTank when multi-stage review/design/coding rigor makes it worthwhile—then let the user choose (unless the user explicitly tagged `@agent` or already requested ThinkTank/Direct execution).
- **Mandatory Triage & Origin Logging:** At session start, log the chosen path via `thinktank_bridge.py --conv-id <CONV_ID> triage --chosen thinktank|solo --tt-reasons "..." --solo-reasons "..."`. Tag every event honestly with `--origin subagent` (only inside real subagent conversations), `--origin main-proxy` (when recorded by the main agent), or `user`.

## Direct `@agent` Tagging
When the user tags `@<agent-name>` directly, invoke that canonical subagent immediately without extra triage ceremony.

## Built-in `/ThinkTank`, `/thinktank`, and `/ ThinkTank` Launch Commands
When the user invokes `/ThinkTank`, `/thinktank`, or `/ ThinkTank` (both `/thinktank` and `/ThinkTank` resolve through the bundled `skills/thinktank/SKILL.md` skill and `commands/thinktank.toml`):
- Start an isolated ThinkTank v4.0 run via `thinktank_bridge.py set-task --new-run` (and log `triage --chosen thinktank`), archiving any prior closed or active work cleanly (`--run-N`) with zero cross-run bleed.
- Spawn real subagents from the canonical 7+1 roster via `invoke_subagent` and surface `[Live Think Tank](sidecar://team-orchestration-director/think-tank/)`.

## ThinkTank v4.0 Case Ledger & 5-Stage Closed-Loop Finding Lifecycle
The sidecar UI renders a **Case Ledger** across **4 specialized boards** (`Command & WBS`, `Topology & Flow`, `Sequence & Chronicle`, `Squad & Telemetry`) plus a **Contextual Dossier Drawer**, **Settings sheet**, and read-only **Closure Receipt** when completed. Every defect is tracked as a numbered **Finding (`F-01`..)** through strict backend-enforced gates:
1. **WBS & File Locks (`team-manager`):** Decompose work via `assign-subtask` with single-owner `--files` locks (HTTP 409 on cross-assignee conflict) and explicit `--acceptance` criteria.
2. **Implementation (`workers`):** Specialists implement and run `PEER_SYNC` on `#sync`; user composer remains strictly user-only (never impersonate agents).
3. **Critic -> Worker Finding Fix (`council-critic` -> `workers`):** Under the fixed Severity Rubric (`CRITICAL`, `HIGH`, `MEDIUM`), max **7 ranked findings** per round, and audit scope restricted to touched diff + connected files, every defect is returned via `return-defect --repro "..."` (creating/reopening `F-xx`). The worker fixes the root cause and hands off via `worker-fix --finding F-xx` (`InReview`). Withdrawing a finding requires `WontFix` with a non-empty reason (`/api/findings/action`).
4. **Code Review + Evidence QA (`code-reviewer` <-> `qa-reviewer`):** `code-reviewer` completes the 3-point checklist (root cause fixed, callers/tests updated, minimal diff) before `qa-dispatch --finding F-xx`. `qa-reviewer` bans "should work" claims and attaches executed **Evidence** (`--cmd --exit-code --excerpt --runner substrate|host-fallback --runner-reason`) to `qa-report --finding F-xx` (PASS without command + exit code 0 is rejected with HTTP 409).
5. **Hard Closure & Receipt (`complete`):** `complete` transitions `Verified` findings to `Closed` and generates `closureReceipt` (with `originCounts` and `qaAllExitZero`). It is blocked (HTTP 409) while `Open`/`Fixing`/`InReview`/`Testing` findings remain unless `--force --reason "..."` is provided.
