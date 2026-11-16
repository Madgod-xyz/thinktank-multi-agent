# Think Tank Governance, Cohesion & Hierarchy Rules

1. **Always Include Sidecar Link:** Whenever ThinkTank is active or referenced, surface `[Live Think Tank](sidecar://team-orchestration-director/think-tank/)`.
2. **Canonical 7+1 Roster Only:** Use exclusively registered roles from `role_catalog.json`:
   - Coordinator: `main_agent`
   - Supervisors (`canInterrogate: true`): `team-manager`, `council-critic`, `code-reviewer`
   - Subordinate Tester (`reportsTo: code-reviewer`): `qa-reviewer`
   - Specialist Workers (`canPeerSync: true`): `ui-frontend-designer`, `backend-auditor`, `ecommerce_seo_operator`, `wp_technical_operator`
3. **5-Stage Closed-Loop Remediation & Hard Closure:**
   - **Critic -> Worker Fix:** Defects raised by `council-critic` return directly to the responsible worker via `RETURN_DEFECT`; the worker implements the fix and hands off to `code-reviewer` via `WORKER_FIX`.
   - **Code Review ⇄ QA ⇄ Workers & Critic:** `code-reviewer` reviews line by line and commands `qa-reviewer` (`QA_DISPATCH`). If failures or ambiguities arise, both `code-reviewer` and `qa-reviewer` consult/query workers and `council-critic` directly (`REVIEW_QUERY`, `PEER_SYNC`, `INTERROGATE`) until `QA_REPORT PASS`.
   - **Direct Worker Peer Sync:** Workers collaborate directly via `PEER_SYNC` on `#sync` to align contracts, schemas, SEO markup, and WooCommerce hooks.
5. **Dual Applicability (Code + Planning) & Balanced Triage:** ThinkTank is designed for both multi-file **code development** and **architectural planning**. On heavier tasks, the Main Agent presents balanced reasons for entering ThinkTank AND transparent reasons whether it can also handle the task solo, recommending ThinkTank when multi-perspective critique, UI anti-slop discipline, or code-reviewer + QA verification adds clear value.
6. **Hard Completion Lifecycle (`complete`):** Never leave completed work open or agent cards frozen active; execute `thinktank_bridge.py complete --conv-id <CONV_ID>` after verified completion so the session, subtasks, and defects close permanently.
