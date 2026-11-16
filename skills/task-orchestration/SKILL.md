---
name: task-orchestration
description: Decompose coding and planning projects into WBS subtasks, enforce single-owner edits, dispatch QA checks, and synchronize the 7+1 ThinkTank team.
---

# Task Orchestration & WBS Pipeline

Use this skill to split multi-file **code development** or **architectural planning** tasks across the canonical 7+1 ThinkTank roster and track live progress on the board.

## 1. Canonical Subagent Roster
Assign subtasks and messages strictly to these registered IDs:
- **Supervisors (`tier: supervisor`, `canInterrogate: true`):**
  `team-manager`, `council-critic`, `code-reviewer`
- **Subordinate Tester under `code-reviewer` (`tier: tester`, `reportsTo: code-reviewer`):**
  `qa-reviewer`
- **Specialist Workers (`tier: worker`, `canPeerSync: true`):**
  `ui-frontend-designer`, `backend-auditor`, `ecommerce_seo_operator`, `wp_technical_operator`

### Standard Delivery & Review Pipeline
`MAIN AGENT -> TEAM-MANAGER (WBS) -> SPECIALIST WORKERS (PEER_SYNC <->) -> COUNCIL-CRITIC (INTERROGATE) -> CODE-REVIEWER (LINE AUDIT) <-> QA-REVIEWER (LIVE TESTS) -> COMPLETE`

## 2. Live Subtask Lifecycle (`assign-subtask` / `update-subtask`)
1. **Create / Assign Subtask:**
   ```bash
   python tools/thinktank_bridge.py assign-subtask --conv-id <CONV_ID> --id <subtask-id> --title "<Title>" --assignee <agent-id> --from team-manager --status ASSIGNED --priority HIGH --deliverable "<Expected Code/Artifact>"
   ```
2. **Transition Status (`IN_PROGRESS` | `REVIEW` | `COMPLETED`):**
   ```bash
   python tools/thinktank_bridge.py update-subtask --conv-id <CONV_ID> --id <subtask-id> --title "<Title>" --assignee <agent-id> --status COMPLETED --deliverable "<Verified File/Test Output>"
   ```
3. **Final Completion (`complete`):**
   ```bash
   python tools/thinktank_bridge.py complete --conv-id <CONV_ID> --summary "<Final Verified Summary>"
   ```
