# Contributing to Team Orchestration Director (ThinkTank)

Thank you for helping improve ThinkTank. Keep every change minimal, portable, and verified before opening a pull request.

## Canonical 7+1 Team Structure

Do not add extra top-level active agent profiles under `agents/` unless intentionally expanding the architecture. The canonical roster consists of:

- **Supervisors (`canInterrogate: true`)**: `team-manager`, `council-critic`, `code-reviewer`
- **Subordinate QA (`reportsTo: code-reviewer`)**: `qa-reviewer`
- **Specialist Workers (`canPeerSync: true`)**: `ui-frontend-designer`, `backend-auditor`, `ecommerce_seo_operator`, `wp_technical_operator`

## Engineering Standards

1. **Minimal Diffs (Ponytail)**: Solve the task with the smallest complete change. Reuse existing endpoints (`/api/task/update`, `/api/subtasks/upsert`, `/api/agent/collaborate`) and existing UI helpers before adding new ones.
2. **Hallmark UI Discipline**:
   - Never introduce Unicode emojis in `index.html`, `app.js`, `role_catalog.json`, or documentation headings. Use clean text or inline SVG icons.
   - Maintain `:focus-visible`, `prefers-reduced-motion: reduce`, `overflow-x: clip`, and responsive breakpoints (`1180px`, `860px`, `620px`, `420px`). Never use `transition: all`.
   - Preserve both Persian (`fa`, RTL) and English (`en`, LTR) support in `sidecars/think-tank/i18n.js`.
3. **Portability & Privacy**:
   - Never commit hardcoded user home directories, private domains, API tokens, `.bak` files, or `.sqlite3` runtime databases.

## Local Verification Gate

Run the sidecar unit/contract suite and full release verifier before submitting:

```bash
python tools/install_plugin.py --check
python tools/verify_release.py
```

Or run the Node UI test suite directly inside `sidecars/think-tank/`:

```bash
node --test tests/ui-contract.test.mjs tests/ui_activity.test.cjs tests/ui_i18n.test.cjs
```
