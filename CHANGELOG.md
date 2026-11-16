# Changelog

All notable changes to `team-orchestration-director` (ThinkTank) are documented in this file.

## [3.0.0]

### Added
- **Multi-Run / Multi-Session Isolation (`backend/app.py`, `tools/thinktank_bridge.py`):**
  - Added `--new-run` (`TaskUpdateRequest.newRun`) and `_archive_conversation_run` (`copy.deepcopy`) so starting a new task or triage on a closed or switched conversation archives prior work as `convId--run-1`, `convId--run-2`, etc. (persisted in SQLite `sync_store` and JSON state) while starting a clean fresh run (`runIndex`) with zero bleed across runs.
  - Added `runIndex`, `parentConvId`, `isArchivedRun`, and `isClosed` metadata to `/api/conversations` and `conversationsList` in `/api/status` and WebSocket `STATE_UPDATE`.
- **Real Subagent Activation & Live Telemetry Routing (`backend/app.py`, `tools/thinktank_antigravity_hook.py`, `tools/install_antigravity_hook.py`):**
  - Added persisted `subagent_session_map` linking spawned child subagent UUIDs (`invoke_subagent` / `send_message`) to `(parentConvId, roleId, roleTitle)`.
  - Updated `normalize_agent_id` to strip leading `tt-`/`tt_` and `agent-`/`agent_` prefixes uniformly (`tt-backend-auditor` -> `backend-auditor`).
  - Marked active subagent profiles with `subagentConvId` and `verifiedSubagent: true`, prevented child `active-session` callbacks from overwriting the parent `active_conv_id`, and routed child tool telemetry back to the parent conversation under the mapped role.
- **Built-in `/ThinkTank` & `/thinktank` Slash Command and Auto-Hook Installer (`skills/thinktank/SKILL.md`, `commands/*.toml`, `tools/install_plugin.py`, `plugin.json`, `rules/AGENTS.md`):**
  - Added `skills/thinktank/SKILL.md`, `commands/thinktank.toml`, `displayName`, and `suggestedPrompts` in `plugin.json`.
  - Updated `install_plugin.py --install` to sync hook scripts, register `hooks.json` via `install_antigravity_hook`, deploy slash command `.toml` files, and prune legacy `_archived` / `data-evidence-pack` artifacts.
- **Case Ledger UI & Verification Polish (`sidecars/think-tank/`, `tools/verify_release.py`):**
  - Category-coded directional arrows (`INTERROGATION`, `DEFECT_RETURN`, `QA_REPORT`, `PEER_SYNC`, `REFERRAL`, `DECISION`) and bilingual hover inspection tooltips in Map & Replay.
  - Hardened `verify_release.py` with hex-escaped privacy scan patterns, emoji scanning across `agents/*.md`, `rules/*.md`, and `commands/*.toml`, and checks for new slash command and hook files.
- **ThinkTank v3 Case Ledger Data Model & Backend Gates (`backend/app.py`, `tools/thinktank_bridge.py`):**
  - First-class **Finding (`F-01`..)** lifecycle (`Open` -> `Fixing` -> `InReview` -> `Testing` -> `Verified` -> `Closed`, plus `WontFix` requiring a reason) and `POST /api/findings/action` (`ack`, `wontfix`, `mark_important`).
  - Mandatory **Evidence-backed QA** (`command`, `exitCode`, `stdoutHash`, `excerpt`, `runner: substrate|host-fallback`, `runnerReason`): `qa-report --finding F-xx --status PASS` without non-empty `--cmd` and `--exit-code 0` is rejected with HTTP 409.
  - **Origin Provenance** (`subagent`, `main-proxy`, `user`, `subagentConvId`, `originCounts`) propagated across messages, interactions, `/api/status`, and `closureReceipt`.
  - **Single-owner WBS File Locks** (`lockedFiles`, `fileLocks`, `acceptanceCriteria`) rejecting cross-assignee active lock conflicts with HTTP 409.
  - **Session Triage (`triage`)** logging (`--chosen thinktank|solo`, `--tt-reasons`, `--solo-reasons`).
  - **Hard Closure Gate & Receipt (`closureReceipt`)**: `complete` blocks (HTTP 409) while unresolved findings remain unless `--force --reason` is provided, and records honest `originCounts` and `qaAllExitZero` metrics.
- **Case Ledger Sidecar UI (`sidecars/think-tank/`):**
  - Replaced 5-tab dashboard with **3 ARIA views** (`Flow`, `Map & Replay`, `Team`) plus a separate **Settings sheet** (`#settings-sheet`) and Dev Mode toggle (`#dev-mode-toggle`).
  - Case Ledger dark & light status-only palette (`--paper`, `--sheet`, `--sheet-2`, `--ink`, `--ink-muted`, `--rule`, `--open`, `--working`, `--review`, `--verified`, `--focus`) with programmatic WCAG AA contrast parity; zero `--violet`, `#38bdf8`, gradients, cards-in-cards, or `transition: all`.
  - Geometric SVG role monograms (`MA` hexagon; `TM`/`CC`/`CR` square; `QA` diamond; `UI`/`BE`/`SE`/`WP` circle) across all 9 canonical roles with zero Unicode emojis.
  - `@container` responsive sidecar layout (`<480px` compact sticky bottom nav + communication table, `480-839px` regular, `>=840px` 2-column with sticky `320px` `#case-inspector`).
  - Flow view features: `#now-strip`, clickable `#findings-progress-bar` and `#wbs-progress-bar`, `.finding-card` with 5-node `.lifecycle-rail`, read-only `.wbs-row`, single-line `#event-ledger-section`, user-only `#user-composer-form`, and read-only `#closure-receipt`.
  - Map & Replay view: active-role vertical `#sequence-diagram-wrap` with screen-reader table fallback, 3-row dynamic `#network-graph-wrap`, and sticky `.replay-bar` (`Space`/`Arrow`/`L` shortcuts).
  - Structured key-based `locales.fa` / `locales.en` in `i18n.js` with full key parity and `lastSeenSeq` WebSocket synchronization (eliminating dual 2s polling).
- **Subagent Calibration (`agents/*.md`, `rules/AGENTS.md`):**
  - Added `hallmark`, `design-tokens`, `responsive-layout`, `microinteractions`, `accessibility-qa`, `dark-mode-visuals`, `design-handoff`, and `design-to-code` skills plus Case Ledger specs to `agents/ui-frontend-designer.md`.
  - Added fixed Severity Rubric (`CRITICAL`/`HIGH`/`MEDIUM`), max 7 ranked findings per round, mandatory `--repro`, and diff-scoped audits to `agents/council-critic.md`.
  - Mandated session `triage` + `--files`/`--acceptance` on `assign-subtask` in `agents/team-manager.md`, 3-point finding checklist in `agents/code-reviewer.md`, and Evidence-only QA (banning "should work") in `agents/qa-reviewer.md`.

### Changed
- Removed agent impersonation composer controls so users send messages strictly as `user`.
- Removed fake `0` telemetry badges when `turnsUsed` or `activeTool` are unreported.
- Updated `README.md` and `rules/AGENTS.md` for ThinkTank v3 Case Ledger workflows and strict zero-emoji hygiene.

## [2.0.0]

### Added
- Canonical 7+1 multi-agent hierarchy: `team-manager`, `council-critic`, `code-reviewer` (supervisors), `qa-reviewer` (subordinate QA tester), `ui-frontend-designer`, `backend-auditor`, `ecommerce_seo_operator`, and `wp_technical_operator` (workers).
- Complete v2 ThinkTank Matrix UI (`sidecars/think-tank/`):
  - Swarm-style empty state when no ThinkTank session exists for the active conversation.
  - Strict per-conversation isolation (`convId` scoping on backend queries and WebSocket snapshots).
  - Interactive 5-stage closed-loop stepper with keyboard navigation (`overview`, `conversations`, `graph`, `team`, `settings`).
  - Quick WBS subtask assignment form (`#overview-subtask-form`) directly in Overview.
  - Directed SVG interaction graph with edge-color legend, active node/edge selection highlight (`#graph-clear-selection`), live recording indicator, and timeline scrubber (`prev`, `play/pause`, `next`, `0.5x/1x/2x`, `live`).
  - Team cards with localized role names, turn-usage and active-tool telemetry badges, and skill badges.
  - Governance role-cap form (`#caps-form`) persisted via `/api/task/update`.
- Full bilingual `FA <-> EN` switcher (`i18n.js`) with RTL/LTR flipping and Persian numeral formatting.
- Portable open-source kit: root `package.json`, `CONTRIBUTING.md`, `tools/install_plugin.py`, and `tools/verify_release.py`.

### Changed
- Replaced all UI and role Unicode emojis with custom inline vector SVGs (Hallmark-compliant styling, `:focus-visible`, `prefers-reduced-motion`, multi-breakpoint responsiveness down to `420px`).
- Updated `README.md` with accurate v2.0 architecture, CLI bridge flags (`--conv-id`, `--from-agent`, `--to-agent`, `--status PASS`), and release verification workflows.

## [1.0.0]

### Added
- Initial ThinkTank multi-agent orchestrator plugin, FastAPI SQLite-backed backend (`backend/app.py`), WebSocket snapshot synchronization, and Node sidecar proxy (`sidecars/think-tank/main.mjs`).
