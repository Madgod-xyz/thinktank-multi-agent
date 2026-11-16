---
name: quality-gate
description: Enforce line-by-line code review, subordinate qa-reviewer verification, anti-slop checks, and confidence gating before accepting or completing multi-agent work.
---

# Quality Gate & QA Verification

Use this skill before accepting any implementation diff, approving a plan, or calling `complete` on a ThinkTank session.

## 1. Mandatory Quality Gates (Closed-Loop Flow)
1. **Critic Red-Team Clearance -> Worker Remediation (`council-critic` -> `workers`):**
   - Every bug or flaw detected by `council-critic` is returned to the worker (`return-defect`) and fixed by that worker (`worker-fix`) before handoff to `code-reviewer`. Zero unresolved `CRITICAL` or `HIGH` defects may remain.
2. **Line-by-Line Audit (`code-reviewer`) + Live Testing (`qa-reviewer`) + Cross-Team Querying:**
   - `code-reviewer` reads modified files line by line and sends `QA_DISPATCH` to `qa-reviewer`.
   - If any check fails or edge cases need clarification, `code-reviewer` and `qa-reviewer` troubleshoot directly with the responsible **worker** and **`council-critic`** (`review-query` / `interrogate` / `peer-sync`) until fixed and `QA_REPORT PASS` is recorded.
3. **Anti-AI-Slop Verification (`ui-frontend-designer`):**
   - Frontend diffs contain zero banned slop patterns (no purple-indigo gradients, no `transition: all`, no animating layout properties, token-only styling, verified RTL/LTR responsiveness and keyboard focus).
4. **Confidence Gate & Hard Closure (`>= 95%`):**
   - Execute `thinktank_bridge.py complete --conv-id <CONV_ID>` once verified so the session, subtasks, defects, and all agents permanently transition to `COMPLETED` / closed state.
   - If confidence < 95%, escalate via `submit-review` rather than silently completing.
