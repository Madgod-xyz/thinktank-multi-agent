#!/usr/bin/env python3
"""
ThinkTank v2.0 — Live Swarm-Style Bridge CLI
Streams tasks, WBS subtasks, supervisor interrogations, code-reviewer -> qa-reviewer
testing dispatches/reports, worker peer-to-peer syncs, proposals, and tool telemetry.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

TOOLS_DIR = str(Path(__file__).resolve().parent)
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

from bridge_transport import api_get, api_post  # noqa: E402

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def report_result(label: str, result: dict):
    status = result.get("status")
    if status == "queued_offline":
        print(f"[ThinkTank] Queued while backend is offline: {label} (event {result.get('eventId')})")
    elif status in {"error", "offline"} or result.get("success") is False:
        print(f"[ThinkTank] Not confirmed: {label} — {result.get('error', status)}")
    elif status == "duplicate":
        print(f"[ThinkTank] Duplicate retry ignored: {label}")
    else:
        print(f"[ThinkTank] {label}")
    return result


def _resolve_origin_fields(origin: str = None, subagent_conv_id: str = None) -> dict:
    sub_cid = (subagent_conv_id or os.environ.get("ANTIGRAVITY_SUBAGENT_CONV_ID") or "").strip() or None
    resolved = (origin or "").strip().lower() or ("subagent" if sub_cid else "main-proxy")
    if resolved == "subagent" and not sub_cid:
        print(
            "[ThinkTank] Warning: --origin subagent passed without --subagent-conv-id or ANTIGRAVITY_SUBAGENT_CONV_ID; backend will downgrade origin to main-proxy.",
            file=sys.stderr,
        )
    fields = {"origin": resolved}
    if sub_cid:
        fields["subagentConvId"] = sub_cid
    return fields


def _split_csv_args(values: list = None) -> list:
    if values is None:
        return []
    out = []
    for item in values:
        for part in str(item).split(","):
            clean = part.strip()
            if clean:
                out.append(clean)
    return out


def _clean_reason_args(values: list = None) -> list:
    if not values:
        return []
    return [str(item).strip() for item in values if str(item).strip()]


def set_triage(chosen: str, tt_reasons: list = None, solo_reasons: list = None, conv_id: str = None):
    payload = {
        "triageDecision": {
            "chosen": chosen,
            "thinktankReasons": _clean_reason_args(tt_reasons),
            "soloReasons": _clean_reason_args(solo_reasons),
            "timestamp": time.strftime("%H:%M:%S"),
        }
    }
    res = api_post("task/update", payload, conv_id)
    return report_result(f"Triage recorded: {chosen}", res)


def set_task(project: str, directive: str, phase: str = "Active Deliberation", progress: int = 50, round: int = None, max_rounds: int = None, conv_id: str = None, new_run: bool = False):
    payload = {
        "project": project,
        "directive": directive,
        "status": "ACTIVE",
        "phase": phase,
        "progress": progress,
    }
    if new_run:
        payload["newRun"] = True
    if round is not None:
        payload["round"] = round
    if max_rounds is not None:
        payload["maxRounds"] = max_rounds
    res = api_post("task/update", payload, conv_id)
    return report_result(f"Task updated: [{project}] {directive}", res)


def set_proposal(proposal_id: str, project: str, title: str, author: str, summary: str, options: list = None, votes: list = None, conv_id: str = None):
    payload = {
        "id": proposal_id,
        "project": project,
        "title": title,
        "author": author,
        "summary": summary,
        "decisionOptions": options or [],
        "votes": votes or [],
    }
    res = api_post("proposal/update", payload, conv_id)
    return report_result(f"Proposal submitted: «{title}»", res)


def post_message(
    channel: str,
    sender_code: str,
    sender_name: str,
    sender_role: str,
    content: str,
    is_btw: bool = False,
    conv_id: str = None,
    is_review: bool = False,
    review_id: str = None,
    *,
    recipient_code: str = None,
    recipient_name: str = None,
    recipient_role: str = None,
    recipient: str = None,
    thoughts: str = None,
    critique: str = None,
    question: str = None,
    report: str = None,
    action_type: str = None,
    request_type: str = None,
    severity: str = None,
    origin: str = None,
    subagent_conv_id: str = None,
):
    if is_review and not review_id:
        raise ValueError("--review-id is required for current review messages")
    payload = {
        "id": f"msg-{int(time.time() * 1000)}-{os.getpid() % 1000}",
        "channel": channel.upper(),
        "senderCode": sender_code,
        "senderName": sender_name,
        "senderRole": sender_role,
        "timestamp": time.strftime("%H:%M:%S"),
        "content": content,
        "isBtw": is_btw,
        "isOperator": False,
        "isReview": is_review,
        **_resolve_origin_fields(origin, subagent_conv_id),
    }
    if is_review:
        payload["reviewId"] = review_id
    if recipient_code:
        payload["recipientCode"] = recipient_code
    if recipient_name:
        payload["recipientName"] = recipient_name
    if recipient_role:
        payload["recipientRole"] = recipient_role
    if recipient:
        payload["recipient"] = recipient
    if thoughts:
        payload["thoughts"] = thoughts
    if critique:
        payload["critique"] = critique
    if question:
        payload["question"] = question
    if report:
        payload["report"] = report
    if action_type:
        payload["actionType"] = action_type
    if request_type:
        payload["requestType"] = request_type
    if severity:
        payload["severity"] = severity
    res = api_post("chat/send", payload, conv_id)
    return report_result(f"Message posted ({payload['channel']}) by {sender_name}", res)


def update_agent(
    agent_id: str,
    task: str = None,
    tool: str = None,
    thought: str = None,
    demo: str = None,
    status: str = None,
    latency: int = None,
    conv_id: str = None,
    *,
    name: str = None,
    role: str = None,
    code: str = None,
    icon: str = None,
    progress: int = None,
):
    clean_id = agent_id.replace("agent-", "").lower()
    payload = {"id": clean_id}
    if task:
        payload["task"] = task
    if tool:
        payload["tool"] = tool
    if thought:
        payload["thought"] = thought
    if demo:
        payload["demo"] = demo
    if status:
        payload["status"] = status
    if latency is not None:
        payload["latency"] = latency
    if name:
        payload["name"] = name
    if role:
        payload["role"] = role
    if code:
        payload["code"] = code
    if icon:
        payload["icon"] = icon
    if progress is not None:
        payload["progress"] = progress
    res = api_post("agent/update", payload, conv_id)
    return report_result(f"Agent [{clean_id}] updated", res)


def collaborate(
    from_agent: str,
    to_agent: str,
    label: str = "همکاری و مباحثه فعال",
    message: str = None,
    conv_id: str = None,
    *,
    action: str = "PEER_SYNC",
    request_type: str = None,
    channel: str = None,
    severity: str = None,
    thoughts: str = None,
    critique: str = None,
    question: str = None,
    report: str = None,
    result: str = None,
    origin: str = None,
    subagent_conv_id: str = None,
    finding_id: str = None,
    work_item_id: str = None,
    repro_steps: str = None,
    evidence_command: str = None,
    exit_code: int = None,
    evidence_excerpt: str = None,
    runner: str = None,
    runner_reason: str = None,
):
    from_clean = from_agent.replace("agent-", "").lower().strip()
    to_clean = to_agent.replace("agent-", "").lower().strip()
    action_upper = (action or "PEER_SYNC").upper().strip()
    inferred_channel = (channel or {
        "RETURN_DEFECT": "INTERROGATION",
        "INTERROGATE": "INTERROGATION",
        "INTERROGATE_REPLY": "INTERROGATION",
        "CRITIQUE": "INTERROGATION",
        "WORKER_FIX": "QA",
        "REVIEW_QUERY": "QA",
        "QA_DISPATCH": "QA",
        "QA_REPORT": "QA",
        "PEER_SYNC": "SYNC",
        "DELEGATE": "SUBAGENTS",
        "APPROVE": "COUNCIL",
    }.get(action_upper, "SYNC")).upper()

    payload = {
        "fromAgent": from_clean,
        "toAgent": to_clean,
        "action": action_upper,
        "requestType": request_type,
        "channel": inferred_channel,
        "severity": severity,
        "label": label,
        "crosstalkMessage": message,
        "thoughts": thoughts,
        "critique": critique,
        "question": question,
        "report": report,
        "result": result.upper() if result else None,
        **_resolve_origin_fields(origin, subagent_conv_id),
    }
    if finding_id:
        payload["findingId"] = finding_id
    if work_item_id:
        payload["workItemId"] = work_item_id
    if repro_steps:
        payload["reproSteps"] = repro_steps
    if evidence_command is not None:
        payload["evidenceCommand"] = evidence_command
    if exit_code is not None:
        payload["exitCode"] = exit_code
    if evidence_excerpt is not None:
        payload["evidenceExcerpt"] = evidence_excerpt
    if runner:
        payload["runner"] = runner
    if runner_reason:
        payload["runnerReason"] = runner_reason
    res = api_post("agent/collaborate", payload, conv_id)
    return report_result(f"[{action_upper}] {from_clean} -> {to_clean} ({label})", res)


def return_defect(from_agent: str, to_agent: str, bug: str, severity: str = "HIGH", critique: str = None, conv_id: str = None, *, finding_id: str = None, work_item_id: str = None, repro_steps: str = None, request_type: str = None, origin: str = None, subagent_conv_id: str = None):
    sev = (severity or "HIGH").upper()
    fid_tag = f" ({finding_id})" if finding_id else ""
    msg = f"[ایراد برگشتی برای اصلاح{fid_tag} · {sev}] @{to_agent}\n{bug}"
    return collaborate(
        from_agent=from_agent or "council-critic",
        to_agent=to_agent,
        label=f"ایراد برگشتی ({sev})",
        message=msg,
        action="RETURN_DEFECT",
        request_type=request_type,
        channel="INTERROGATION",
        severity=sev,
        question=bug,
        critique=critique or bug,
        finding_id=finding_id,
        work_item_id=work_item_id,
        repro_steps=repro_steps,
        origin=origin,
        subagent_conv_id=subagent_conv_id,
        conv_id=conv_id,
    )


def worker_fix(from_agent: str, to_agent: str, fix: str, files: str = None, conv_id: str = None, *, finding_id: str = None, request_type: str = None, origin: str = None, subagent_conv_id: str = None):
    file_line = f"\nفایل‌ها: {files}" if files else ""
    fid_tag = f" ({finding_id})" if finding_id else ""
    msg = f"[اصلاحیه تکمیل و ارسال شد{fid_tag}] @{to_agent or 'code-reviewer'}\n{fix}{file_line}"
    return collaborate(
        from_agent=from_agent,
        to_agent=to_agent or "code-reviewer",
        label="تحویل اصلاحیه کارگر",
        message=msg,
        action="WORKER_FIX",
        request_type=request_type,
        channel="QA",
        thoughts=fix,
        report=files or fix,
        finding_id=finding_id,
        origin=origin,
        subagent_conv_id=subagent_conv_id,
        conv_id=conv_id,
    )


def review_query(from_agent: str, to_agent: str, question: str, conv_id: str = None, *, finding_id: str = None, result: str = None, severity: str = None, request_type: str = None, origin: str = None, subagent_conv_id: str = None):
    fid_tag = f" ({finding_id})" if finding_id else ""
    msg = f"[پرسش بررسی و رفع ابهام{fid_tag}] @{to_agent}\n{question}"
    return collaborate(
        from_agent=from_agent or "code-reviewer",
        to_agent=to_agent,
        label="پرسش بررسی و QA",
        message=msg,
        action="REVIEW_QUERY",
        request_type=request_type,
        channel="QA",
        severity=severity,
        question=question,
        thoughts=question,
        result=result,
        finding_id=finding_id,
        origin=origin,
        subagent_conv_id=subagent_conv_id,
        conv_id=conv_id,
    )


def interrogate(from_agent: str, to_agent: str, question: str, severity: str = "HIGH", critique: str = None, conv_id: str = None, *, request_type: str = None, origin: str = None, subagent_conv_id: str = None):
    msg = f"[بازخواست سرگروه · {severity.upper()}] @{to_agent}\n{question}"
    return collaborate(
        from_agent=from_agent,
        to_agent=to_agent,
        label=f"بازخواست سرگروه ({severity.upper()})",
        message=msg,
        action="INTERROGATE",
        request_type=request_type,
        channel="INTERROGATION",
        severity=severity.upper(),
        question=question,
        critique=critique or question,
        origin=origin,
        subagent_conv_id=subagent_conv_id,
        conv_id=conv_id,
    )


def peer_sync(from_agent: str, to_agent: str, topic: str, summary: str, question: str = None, conv_id: str = None, *, request_type: str = None, origin: str = None, subagent_conv_id: str = None):
    msg = f"[سینک همتا · {topic}] @{to_agent}\n{summary}"
    return collaborate(
        from_agent=from_agent,
        to_agent=to_agent,
        label=topic,
        message=msg,
        action="PEER_SYNC",
        request_type=request_type,
        channel="SYNC",
        question=question,
        thoughts=summary,
        origin=origin,
        subagent_conv_id=subagent_conv_id,
        conv_id=conv_id,
    )


def qa_dispatch(from_agent: str, to_agent: str, scope: str, checks: str, conv_id: str = None, *, finding_id: str = None, request_type: str = None, origin: str = None, subagent_conv_id: str = None):
    fid_tag = f" ({finding_id})" if finding_id else ""
    msg = f"[دستور اجرای تست از کد ریویور{fid_tag}] @{to_agent}\nدامنه: {scope}\nچک‌لیست آزمون: {checks}"
    return collaborate(
        from_agent=from_agent or "code-reviewer",
        to_agent=to_agent or "qa-reviewer",
        label=f"دستور تست: {scope[:48]}",
        message=msg,
        action="QA_DISPATCH",
        request_type=request_type,
        channel="QA",
        thoughts=checks,
        finding_id=finding_id,
        origin=origin,
        subagent_conv_id=subagent_conv_id,
        conv_id=conv_id,
    )


def qa_report(status: str, summary: str, details: str = None, to_agent: str = "code-reviewer", conv_id: str = None, *, finding_id: str = None, evidence_command: str = None, exit_code: int = None, evidence_excerpt: str = None, runner: str = None, runner_reason: str = None, request_type: str = None, origin: str = None, subagent_conv_id: str = None):
    status_upper = status.upper().strip()
    badge = "PASS" if status_upper == "PASS" else "FAIL"
    fid_tag = f" ({finding_id})" if finding_id else ""
    msg = f"[گزارش تستر QA{fid_tag} · {badge}] @{to_agent}\n{summary}"
    return collaborate(
        from_agent="qa-reviewer",
        to_agent=to_agent or "code-reviewer",
        label=f"نتیجه تست: {badge}",
        message=msg,
        action="QA_REPORT",
        request_type=request_type,
        channel="QA",
        critique=details if status_upper != "PASS" else None,
        report=details or summary,
        severity="LOW" if status_upper == "PASS" else "CRITICAL",
        result=status_upper,
        finding_id=finding_id,
        evidence_command=evidence_command,
        exit_code=exit_code,
        evidence_excerpt=evidence_excerpt,
        runner=runner,
        runner_reason=runner_reason,
        origin=origin,
        subagent_conv_id=subagent_conv_id,
        conv_id=conv_id,
    )


def log_tool(agent_id: str, tool: str, status: str = "SUCCESS", args_json: str = None, output: str = "", latency_ms: int = None, conv_id: str = None, *, agent_name: str = None):
    parsed_args = {}
    if args_json:
        try:
            parsed_args = json.loads(args_json)
        except Exception:
            parsed_args = {"raw": args_json}
    payload = {
        "agentId": agent_id,
        "agentName": agent_name or agent_id,
        "tool": tool,
        "args": parsed_args,
        "output": output,
        "status": status,
        "latencyMs": latency_ms,
    }
    res = api_post("telemetry/tool_call", payload, conv_id)
    return report_result(f"Tool call logged: {agent_id} -> {tool} ({status})", res)


def set_round(round_num: int, max_rounds: int = None, conv_id: str = None):
    payload = {"round": round_num}
    if max_rounds is not None:
        payload["maxRounds"] = max_rounds
    res = api_post("task/update", payload, conv_id)
    label = f"Round updated: {round_num}" + (f"/{max_rounds}" if max_rounds is not None else "")
    return report_result(label, res)


def set_role_caps(main: int = 50, manager: int = 50, subagents: int = 50, conv_id: str = None):
    res = api_post("task/update", {"roleCaps": {"main": main, "manager": manager, "subagents": subagents}}, conv_id)
    return report_result("Role conversation caps updated", res)


def submit_review(review_id: str, manager_summary: str, main_summary: str, confidence: int, recommendation: str, continue_reasons: list, completion_reasons: list, evidence: list, conv_id: str = None):
    payload = {
        "reviewId": review_id,
        "managerSummary": manager_summary,
        "mainSummary": main_summary,
        "confidence": confidence,
        "recommendation": recommendation,
        "continueReasons": continue_reasons,
        "completionReasons": completion_reasons,
        "evidence": evidence,
    }
    return report_result("Evidence-backed manager review submitted", api_post("governance/submit_review", payload, conv_id))


def request_round_extension(additional_rounds: int = 3, conv_id: str = None):
    res = api_post("governance/extend_rounds", {"additionalRounds": additional_rounds}, conv_id)
    return report_result(f"Round extension (+{additional_rounds}) submitted", res)


def compress_final_round(conv_id: str = None):
    res = api_post("governance/compress_final", {}, conv_id)
    return report_result("Final-round review requested", res)


def wait_user_action(timeout_seconds: int = 300, poll_interval: float = 2.0, conv_id: str = None):
    print(f"[ThinkTank] Waiting for user approval or option selection in the UI (timeout: {timeout_seconds}s)...")
    start = time.time()
    while time.time() - start < timeout_seconds:
        state = api_get("status", conv_id)
        if state and state.get("status") == "offline":
            print("[ThinkTank] Backend disconnected; no live user decision can be read.")
            return None
        rev = state.get("review") if state else None
        if isinstance(rev, dict) and rev.get("humanDecision"):
            decision = state["review"]["humanDecision"]
            print(f"[ThinkTank] Human review decision received: {decision.get('decision')}")
            return decision
        if state and state.get("proposal"):
            prop = state["proposal"]
            decision = prop.get("userDecision")
            status = prop.get("status")
            if decision or status in ["APPROVED", "REVISION_REQUESTED", "HALTED"]:
                print(f"[ThinkTank] User action received: status={status}, decision={decision}")
                return decision or {"status": status}
        time.sleep(poll_interval)
    print("[ThinkTank] User action wait timed out.")
    return None


def complete_task(summary: str = "تمامی تسک‌ها، اصلاحیه‌ها و تست‌های QA تکمیل و نشست بسته شد.", conv_id: str = None, *, force: bool = False, reason: str = None, origin: str = None, subagent_conv_id: str = None):
    payload = {
        "status": "COMPLETED",
        "progress": 100,
        "phase": "تکمیل‌شده و بسته — پس از بازبینی و تایید QA",
        "forceClose": bool(force),
        "summary": summary,
        **_resolve_origin_fields(origin, subagent_conv_id),
    }
    if reason is not None:
        payload["forceReason"] = reason
    update = api_post("task/update", payload, conv_id)
    return report_result("Completion state submitted", update)


def assign_subtask(
    title: str,
    assignee: str,
    subtask_id: str = None,
    assignee_name: str = None,
    delegated_by: str = "team-manager",
    delegated_by_name: str = "مدیر تیم",
    status: str = "ASSIGNED",
    priority: str = "HIGH",
    deliverable: str = "",
    thoughts: str = None,
    report: str = None,
    dependencies: list = None,
    locked_files: list = None,
    acceptance_criteria: str = None,
    conv_id: str = None,
    *,
    origin: str = None,
    subagent_conv_id: str = None,
):
    payload = {
        "id": subtask_id,
        "title": title,
        "assignee": assignee,
        "assigneeName": assignee_name,
        "delegatedBy": delegated_by,
        "delegatedByName": delegated_by_name,
        "status": status,
        "priority": priority,
        "deliverable": deliverable or "",
        "thoughts": thoughts,
        "report": report,
        "dependencies": dependencies or [],
        **_resolve_origin_fields(origin, subagent_conv_id),
    }
    if locked_files is not None:
        payload["lockedFiles"] = _split_csv_args(locked_files)
    if acceptance_criteria is not None:
        payload["acceptanceCriteria"] = acceptance_criteria
    res = api_post("subtasks/upsert", payload, conv_id)
    report_result(f"Subtask [{title}] -> {assignee} ({status})", res)
    return res


def finding_action(finding_id: str, action: str, reason: str = None, conv_id: str = None):
    payload = {
        "findingId": finding_id,
        "action": action,
    }
    if reason is not None:
        payload["reason"] = reason
    res = api_post("findings/action", payload, conv_id)
    return report_result(f"Finding {finding_id} action [{action}]", res)


def vote_proposal(
    voter: str,
    comment: str,
    voter_name: str = None,
    voter_role: str = None,
    stance: str = "APPROVE",
    confidence: int = 90,
    counter_argument: str = None,
    conv_id: str = None,
    *,
    origin: str = None,
    subagent_conv_id: str = None,
):
    payload = {
        "voter": voter,
        "voterName": voter_name,
        "voterRole": voter_role,
        "stance": stance,
        "confidence": confidence,
        "comment": comment,
        "counterArgument": counter_argument,
        **_resolve_origin_fields(origin, subagent_conv_id),
    }
    res = api_post("proposal/vote", payload, conv_id)
    report_result(f"Proposal vote [{voter}: {stance} ({confidence}%)]", res)
    return res


def halt_task(reason: str, conv_id: str = None):
    update = api_post("task/update", {"status": "HALTED", "phase": f"Session Halted: {reason}"}, conv_id)
    action = api_post("proposal/action", {"action": "halt", "comment": reason}, conv_id)
    report_result("Stop state submitted", update)
    report_result("Stop action submitted", action)
    return post_message("MAIN", "TEAM-MANAGER", "مدیر تیم", "team-manager", f"[توقف نشست]: {reason}", conv_id=conv_id, is_review=False)


def main():
    parser = argparse.ArgumentParser(description="ThinkTank v3.0 Swarm-Style Bridge CLI")
    default_conv_id = os.environ.get("THINKTANK_CONVERSATION_ID") or os.environ.get("ANTIGRAVITY_CONVERSATION_ID")
    parser.add_argument("--conv-id", default=default_conv_id, help="Explicit Antigravity conversation ID")
    parser.add_argument("--origin", choices=["subagent", "main-proxy", "user"], default=None, help="Event origin provenance")
    parser.add_argument("--subagent-conv-id", default=None, help="Child subagent conversation ID")
    subparsers = parser.add_subparsers(dest="command")

    def add_conv_id_option(subparser):
        subparser.add_argument("--conv-id", dest="conv_id", default=argparse.SUPPRESS, help=argparse.SUPPRESS)

    def add_origin_options(subparser):
        subparser.add_argument("--origin", choices=["subagent", "main-proxy", "user"], default=argparse.SUPPRESS, help=argparse.SUPPRESS)
        subparser.add_argument("--subagent-conv-id", default=argparse.SUPPRESS, help=argparse.SUPPRESS)

    def add_request_type_option(subparser):
        subparser.add_argument(
            "--request-type",
            dest="request_type",
            help="REWRITE, REFERRAL, QUESTION, INTERROGATION, DEFECT_RETURN, QA_REPORT, PEER_SYNC, CRITIQUE, DECISION, MESSAGE",
        )

    p_triage = subparsers.add_parser("triage")
    p_triage.add_argument("--chosen", required=True, choices=["thinktank", "solo"])
    p_triage.add_argument("--tt-reasons", nargs="*", default=[])
    p_triage.add_argument("--solo-reasons", nargs="*", default=[])
    add_conv_id_option(p_triage)
    add_origin_options(p_triage)

    p_task = subparsers.add_parser("set-task")
    p_task.add_argument("--project", required=True)
    p_task.add_argument("--directive", required=True)
    p_task.add_argument("--phase", default="Active Deliberation & Engineering")
    p_task.add_argument("--progress", type=int, default=30)
    p_task.add_argument("--round", type=int)
    p_task.add_argument("--max-rounds", type=int)
    p_task.add_argument("--new-run", action="store_true", help="Archive prior work as a completed run and start a fresh isolated run")
    add_conv_id_option(p_task)
    add_origin_options(p_task)

    p_prop = subparsers.add_parser("set-proposal")
    p_prop.add_argument("--id", default="prop-" + str(int(time.time())))
    p_prop.add_argument("--project", required=True)
    p_prop.add_argument("--title", required=True)
    p_prop.add_argument("--author", default="Team Manager")
    p_prop.add_argument("--summary", required=True)
    p_prop.add_argument("--options", help="Comma-separated options list")
    add_conv_id_option(p_prop)

    p_msg = subparsers.add_parser("post-message")
    p_msg.add_argument("--channel", default="MAIN", choices=["MAIN", "SUBAGENTS", "INTERROGATION", "QA", "SYNC", "COUNCIL"])
    p_msg.add_argument("--code", default="TEAM-MANAGER")
    p_msg.add_argument("--name", "--sender", "--sender-name", dest="name", default="مدیر تیم")
    p_msg.add_argument("--role", "--sender-role", dest="role", default="team-manager")
    p_msg.add_argument("--to", "--recipient", dest="recipient", help="Recipient subagent ID or name")
    p_msg.add_argument("--recipient-code")
    p_msg.add_argument("--recipient-name")
    p_msg.add_argument("--recipient-role")
    p_msg.add_argument("--thoughts", help="Internal reasoning")
    p_msg.add_argument("--critique", help="Critical challenge or flaw analysis")
    p_msg.add_argument("--question", help="Question / interrogation prompt")
    p_msg.add_argument("--report", help="Full verification or technical report")
    p_msg.add_argument("--action-type", dest="action_type", help="MESSAGE, INTERROGATE, PEER_SYNC, QA_DISPATCH, QA_REPORT, DELEGATE")
    p_msg.add_argument("--request-type", dest="request_type", help="REWRITE, REFERRAL, QUESTION, INTERROGATION, DEFECT_RETURN, QA_REPORT, PEER_SYNC, CRITIQUE, DECISION, MESSAGE")
    p_msg.add_argument("--severity", choices=["CRITICAL", "HIGH", "MEDIUM", "LOW"])
    p_msg.add_argument("--content", "--message", dest="content", required=True)
    p_msg.add_argument("--is-btw", action="store_true")
    p_msg.add_argument("--review", action="store_true")
    p_msg.add_argument("--review-id")
    add_conv_id_option(p_msg)
    add_origin_options(p_msg)

    p_ag = subparsers.add_parser("update-agent")
    p_ag.add_argument("--id", required=True)
    p_ag.add_argument("--task")
    p_ag.add_argument("--tool")
    p_ag.add_argument("--thought")
    p_ag.add_argument("--demo")
    p_ag.add_argument("--name")
    p_ag.add_argument("--role")
    p_ag.add_argument("--code")
    p_ag.add_argument("--icon")
    p_ag.add_argument("--progress", type=int)
    p_ag.add_argument("--status")
    p_ag.add_argument("--latency", type=int)
    add_conv_id_option(p_ag)

    p_coll = subparsers.add_parser("collaborate")
    p_coll.add_argument("--from", "--from-agent", dest="from_agent", required=True)
    p_coll.add_argument("--to", "--to-agent", dest="to_agent", required=True)
    p_coll.add_argument("--action", default="PEER_SYNC", choices=["PEER_SYNC", "INTERROGATE", "INTERROGATE_REPLY", "RETURN_DEFECT", "WORKER_FIX", "REVIEW_QUERY", "QA_DISPATCH", "QA_REPORT", "CRITIQUE", "DELEGATE", "APPROVE", "MESSAGE"])
    p_coll.add_argument("--request-type", dest="request_type", help="REWRITE, REFERRAL, QUESTION, INTERROGATION, DEFECT_RETURN, QA_REPORT, PEER_SYNC, CRITIQUE, DECISION, MESSAGE")
    p_coll.add_argument("--channel", choices=["MAIN", "SUBAGENTS", "INTERROGATION", "QA", "SYNC", "COUNCIL"])
    p_coll.add_argument("--severity", choices=["CRITICAL", "HIGH", "MEDIUM", "LOW"])
    p_coll.add_argument("--label", "--topic", dest="label", default="همکاری و مباحثه فعال")
    p_coll.add_argument("--message", "--content", dest="message")
    p_coll.add_argument("--thoughts")
    p_coll.add_argument("--critique")
    p_coll.add_argument("--question")
    p_coll.add_argument("--report")
    p_coll.add_argument("--finding", dest="finding_id")
    p_coll.add_argument("--result")
    add_conv_id_option(p_coll)
    add_origin_options(p_coll)

    p_int = subparsers.add_parser("interrogate")
    p_int.add_argument("--from", "--from-agent", dest="from_agent", required=True, help="Supervisor ID (team-manager, council-critic, code-reviewer)")
    p_int.add_argument("--to", "--to-agent", dest="to_agent", required=True, help="Worker ID being interrogated")
    p_int.add_argument("--question", required=True)
    p_int.add_argument("--severity", default="HIGH", choices=["CRITICAL", "HIGH", "MEDIUM"])
    p_int.add_argument("--critique")
    add_request_type_option(p_int)
    add_conv_id_option(p_int)
    add_origin_options(p_int)

    p_ret = subparsers.add_parser("return-defect")
    p_ret.add_argument("--from", "--from-agent", dest="from_agent", default="council-critic")
    p_ret.add_argument("--to", "--to-agent", dest="to_agent", required=True, help="Responsible worker ID")
    p_ret.add_argument("--bug", "--question", dest="bug", required=True)
    p_ret.add_argument("--severity", default="HIGH", choices=["CRITICAL", "HIGH", "MEDIUM", "LOW"])
    p_ret.add_argument("--critique")
    p_ret.add_argument("--finding", dest="finding_id")
    p_ret.add_argument("--work-item", dest="work_item_id")
    p_ret.add_argument("--repro", dest="repro_steps")
    add_request_type_option(p_ret)
    add_conv_id_option(p_ret)
    add_origin_options(p_ret)

    p_fix = subparsers.add_parser("worker-fix")
    p_fix.add_argument("--from", "--from-agent", dest="from_agent", required=True, help="Worker ID submitting fix")
    p_fix.add_argument("--to", "--to-agent", dest="to_agent", default="code-reviewer")
    p_fix.add_argument("--fix", "--summary", dest="fix", required=True)
    p_fix.add_argument("--files")
    p_fix.add_argument("--finding", dest="finding_id", required=True)
    add_request_type_option(p_fix)
    add_conv_id_option(p_fix)
    add_origin_options(p_fix)

    p_rq = subparsers.add_parser("review-query")
    p_rq.add_argument("--from", "--from-agent", dest="from_agent", default="code-reviewer")
    p_rq.add_argument("--to", "--to-agent", dest="to_agent", required=True, help="Worker or council-critic ID")
    p_rq.add_argument("--question", "--summary", dest="question", required=True)
    p_rq.add_argument("--finding", dest="finding_id")
    p_rq.add_argument("--result")
    p_rq.add_argument("--severity", choices=["CRITICAL", "HIGH", "MEDIUM", "LOW"])
    add_request_type_option(p_rq)
    add_conv_id_option(p_rq)
    add_origin_options(p_rq)

    p_sync = subparsers.add_parser("peer-sync")
    p_sync.add_argument("--from", "--from-agent", dest="from_agent", required=True)
    p_sync.add_argument("--to", "--to-agent", dest="to_agent", required=True)
    p_sync.add_argument("--topic", required=True)
    p_sync.add_argument("--summary", required=True)
    p_sync.add_argument("--question")
    add_request_type_option(p_sync)
    add_conv_id_option(p_sync)
    add_origin_options(p_sync)

    p_qad = subparsers.add_parser("qa-dispatch")
    p_qad.add_argument("--from", "--from-agent", dest="from_agent", default="code-reviewer")
    p_qad.add_argument("--to", "--to-agent", dest="to_agent", default="qa-reviewer")
    p_qad.add_argument("--scope", required=True)
    p_qad.add_argument("--checks", required=True)
    p_qad.add_argument("--finding", dest="finding_id", required=True)
    add_request_type_option(p_qad)
    add_conv_id_option(p_qad)
    add_origin_options(p_qad)

    p_qar = subparsers.add_parser("qa-report")
    p_qar.add_argument("--status", required=True, choices=["PASS", "FAIL"])
    p_qar.add_argument("--summary", required=True)
    p_qar.add_argument("--details")
    p_qar.add_argument("--to", "--to-agent", dest="to_agent", default="code-reviewer")
    p_qar.add_argument("--finding", dest="finding_id", required=True)
    p_qar.add_argument("--cmd", dest="evidence_command")
    p_qar.add_argument("--exit-code", dest="exit_code", type=int)
    p_qar.add_argument("--excerpt", dest="evidence_excerpt")
    p_qar.add_argument("--runner", default="substrate")
    p_qar.add_argument("--runner-reason", dest="runner_reason")
    add_request_type_option(p_qar)
    add_conv_id_option(p_qar)
    add_origin_options(p_qar)

    p_tool = subparsers.add_parser("log-tool")
    p_tool.add_argument("--agent", required=True)
    p_tool.add_argument("--name")
    p_tool.add_argument("--tool", required=True)
    p_tool.add_argument("--status", choices=["SUCCESS", "ERROR"], default="SUCCESS")
    p_tool.add_argument("--args")
    p_tool.add_argument("--output", default="")
    p_tool.add_argument("--latency", type=int)
    add_conv_id_option(p_tool)

    p_round = subparsers.add_parser("set-round")
    p_round.add_argument("--round", type=int, required=True)
    p_round.add_argument("--max-rounds", type=int)
    add_conv_id_option(p_round)

    p_caps = subparsers.add_parser("set-caps")
    p_caps.add_argument("--main", type=int, default=50)
    p_caps.add_argument("--manager", type=int, default=50)
    p_caps.add_argument("--subagents", type=int, default=50)
    add_conv_id_option(p_caps)

    p_review = subparsers.add_parser("submit-review")
    p_review.add_argument("--review-id", required=True)
    p_review.add_argument("--manager-summary", required=True)
    p_review.add_argument("--main-summary", required=True)
    p_review.add_argument("--confidence", type=int, required=True)
    p_review.add_argument("--recommendation", choices=["continue", "complete"], required=True)
    p_review.add_argument("--continue-reasons", nargs="+", required=True)
    p_review.add_argument("--completion-reasons", nargs="+", required=True)
    p_review.add_argument("--evidence", nargs="+", required=True)
    add_conv_id_option(p_review)

    p_ext = subparsers.add_parser("request-round-extension")
    p_ext.add_argument("--requested", type=int, default=3)
    add_conv_id_option(p_ext)

    p_comp_final = subparsers.add_parser("compress-final")
    add_conv_id_option(p_comp_final)

    p_wait = subparsers.add_parser("wait-action")
    p_wait.add_argument("--timeout", type=int, default=300)
    add_conv_id_option(p_wait)

    p_comp = subparsers.add_parser("complete")
    p_comp.add_argument("--summary", default="تمامی تسک‌ها، اصلاحیه‌ها و تست‌های QA تکمیل و نشست بسته شد.")
    p_comp.add_argument("--force", action="store_true")
    p_comp.add_argument("--reason", dest="force_reason")
    add_conv_id_option(p_comp)
    add_origin_options(p_comp)

    p_halt = subparsers.add_parser("halt")
    p_halt.add_argument("--reason", required=True)
    add_conv_id_option(p_halt)

    for sub_cmd in ("assign-subtask", "update-subtask"):
        p_sub = subparsers.add_parser(sub_cmd)
        p_sub.add_argument("--id", dest="subtask_id")
        p_sub.add_argument("--title", required=True)
        p_sub.add_argument("--assignee", required=True)
        p_sub.add_argument("--assignee-name")
        p_sub.add_argument("--from", "--delegated-by", dest="delegated_by", default="team-manager")
        p_sub.add_argument("--delegated-by-name", default="مدیر تیم")
        p_sub.add_argument("--status", default="ASSIGNED", choices=["ASSIGNED", "IN_PROGRESS", "REVIEW", "IN_REVIEW", "COMPLETED", "DONE", "BLOCKED"])
        p_sub.add_argument("--priority", default="HIGH", choices=["CRITICAL", "HIGH", "NORMAL", "MEDIUM", "LOW"])
        p_sub.add_argument("--deliverable", default="")
        p_sub.add_argument("--thoughts", default=None)
        p_sub.add_argument("--report", default=None)
        p_sub.add_argument("--dependencies", nargs="*")
        p_sub.add_argument("--files", nargs="*", dest="locked_files", default=None)
        p_sub.add_argument("--acceptance", dest="acceptance_criteria", default=None)
        add_conv_id_option(p_sub)
        add_origin_options(p_sub)

    p_vote = subparsers.add_parser("vote-proposal")
    p_vote.add_argument("--voter", "--voter-id", dest="voter", required=True)
    p_vote.add_argument("--name", "--voter-name", dest="voter_name")
    p_vote.add_argument("--role", "--voter-role", dest="voter_role")
    p_vote.add_argument("--stance", default="APPROVE", choices=["APPROVE", "CONDITIONAL", "CRITIQUE", "REJECT"])
    p_vote.add_argument("--confidence", type=int, default=90)
    p_vote.add_argument("--comment", required=True)
    p_vote.add_argument("--counter-argument")
    add_conv_id_option(p_vote)
    add_origin_options(p_vote)

    p_fact = subparsers.add_parser("finding-action")
    p_fact.add_argument("--finding", dest="finding_id", required=True)
    p_fact.add_argument("--action", required=True, choices=["ack", "wontfix", "mark_important"])
    p_fact.add_argument("--reason", default=None)
    add_conv_id_option(p_fact)

    args = parser.parse_args()
    if args.command and (not args.conv_id or args.conv_id == "default"):
        parser.error("an explicit Antigravity conversation ID is required; pass --conv-id or set ANTIGRAVITY_CONVERSATION_ID")

    res = None
    if args.command == "triage":
        res = set_triage(args.chosen, args.tt_reasons, args.solo_reasons, conv_id=args.conv_id)
    elif args.command == "set-task":
        res = set_task(args.project, args.directive, args.phase, args.progress, args.round, args.max_rounds, args.conv_id, new_run=args.new_run)
    elif args.command == "set-proposal":
        opts = [{"id": f"opt-{i+1}", "label": opt.strip()} for i, opt in enumerate(args.options.split(","))] if args.options else []
        res = set_proposal(args.id, args.project, args.title, args.author, args.summary, opts, conv_id=args.conv_id)
    elif args.command == "post-message":
        if args.review and not args.review_id:
            parser.error("--review-id is required when --review is used")
        res = post_message(
            args.channel, args.code, args.name, args.role, args.content, args.is_btw,
            conv_id=args.conv_id, is_review=args.review, review_id=args.review_id,
            recipient_code=getattr(args, "recipient_code", None),
            recipient_name=getattr(args, "recipient_name", None),
            recipient_role=getattr(args, "recipient_role", None),
            recipient=getattr(args, "recipient", None),
            thoughts=getattr(args, "thoughts", None),
            critique=getattr(args, "critique", None),
            question=getattr(args, "question", None),
            report=getattr(args, "report", None),
            action_type=getattr(args, "action_type", None),
            request_type=getattr(args, "request_type", None),
            severity=getattr(args, "severity", None),
            origin=args.origin,
            subagent_conv_id=args.subagent_conv_id,
        )
    elif args.command == "update-agent":
        res = update_agent(
            args.id, args.task, args.tool, args.thought, args.demo, args.status,
            args.latency, conv_id=args.conv_id, name=args.name, role=args.role,
            code=args.code, icon=args.icon, progress=args.progress,
        )
    elif args.command == "collaborate":
        res = collaborate(
            args.from_agent, args.to_agent, args.label, args.message, conv_id=args.conv_id,
            action=args.action, request_type=getattr(args, "request_type", None), channel=args.channel, severity=args.severity,
            thoughts=getattr(args, "thoughts", None),
            critique=getattr(args, "critique", None),
            question=getattr(args, "question", None),
            report=getattr(args, "report", None),
            result=getattr(args, "result", None),
            finding_id=getattr(args, "finding_id", None),
            origin=args.origin,
            subagent_conv_id=args.subagent_conv_id,
        )
    elif args.command == "interrogate":
        res = interrogate(
            args.from_agent, args.to_agent, args.question, args.severity, args.critique,
            conv_id=args.conv_id, request_type=getattr(args, "request_type", None),
            origin=args.origin, subagent_conv_id=args.subagent_conv_id,
        )
    elif args.command == "return-defect":
        res = return_defect(
            args.from_agent, args.to_agent, args.bug, args.severity, args.critique,
            conv_id=args.conv_id, finding_id=args.finding_id, work_item_id=args.work_item_id,
            repro_steps=args.repro_steps, request_type=getattr(args, "request_type", None),
            origin=args.origin, subagent_conv_id=args.subagent_conv_id,
        )
    elif args.command == "worker-fix":
        res = worker_fix(
            args.from_agent, args.to_agent, args.fix, args.files,
            conv_id=args.conv_id, finding_id=args.finding_id,
            request_type=getattr(args, "request_type", None),
            origin=args.origin, subagent_conv_id=args.subagent_conv_id,
        )
    elif args.command == "review-query":
        res = review_query(
            args.from_agent, args.to_agent, args.question,
            conv_id=args.conv_id, finding_id=args.finding_id,
            result=args.result, severity=args.severity,
            request_type=getattr(args, "request_type", None),
            origin=args.origin, subagent_conv_id=args.subagent_conv_id,
        )
    elif args.command == "peer-sync":
        res = peer_sync(
            args.from_agent, args.to_agent, args.topic, args.summary, args.question,
            conv_id=args.conv_id, request_type=getattr(args, "request_type", None),
            origin=args.origin, subagent_conv_id=args.subagent_conv_id,
        )
    elif args.command == "qa-dispatch":
        res = qa_dispatch(
            args.from_agent, args.to_agent, args.scope, args.checks,
            conv_id=args.conv_id, finding_id=args.finding_id,
            request_type=getattr(args, "request_type", None),
            origin=args.origin, subagent_conv_id=args.subagent_conv_id,
        )
    elif args.command == "qa-report":
        res = qa_report(
            args.status, args.summary, args.details, args.to_agent,
            conv_id=args.conv_id, finding_id=args.finding_id,
            evidence_command=args.evidence_command, exit_code=args.exit_code,
            evidence_excerpt=args.evidence_excerpt, runner=args.runner,
            runner_reason=args.runner_reason,
            request_type=getattr(args, "request_type", None),
            origin=args.origin, subagent_conv_id=args.subagent_conv_id,
        )
    elif args.command == "log-tool":
        res = log_tool(args.agent, args.tool, args.status, args.args, args.output, args.latency, args.conv_id, agent_name=args.name)
    elif args.command == "set-round":
        res = set_round(args.round, args.max_rounds, conv_id=args.conv_id)
    elif args.command == "set-caps":
        res = set_role_caps(args.main, args.manager, args.subagents, conv_id=args.conv_id)
    elif args.command == "submit-review":
        res = submit_review(args.review_id, args.manager_summary, args.main_summary, args.confidence, args.recommendation,
                            args.continue_reasons, args.completion_reasons, args.evidence, conv_id=args.conv_id)
    elif args.command == "request-round-extension":
        res = request_round_extension(args.requested, conv_id=args.conv_id)
    elif args.command == "compress-final":
        res = compress_final_round(conv_id=args.conv_id)
    elif args.command == "wait-action":
        print(json.dumps(wait_user_action(args.timeout, conv_id=args.conv_id), ensure_ascii=False))
    elif args.command == "complete":
        res = complete_task(
            args.summary, conv_id=args.conv_id, force=args.force, reason=args.force_reason,
            origin=args.origin, subagent_conv_id=args.subagent_conv_id,
        )
    elif args.command == "halt":
        res = halt_task(args.reason, conv_id=args.conv_id)
    elif args.command in ("assign-subtask", "update-subtask"):
        res = assign_subtask(
            title=args.title, assignee=args.assignee, subtask_id=args.subtask_id,
            assignee_name=args.assignee_name, delegated_by=args.delegated_by,
            delegated_by_name=args.delegated_by_name, status=args.status,
            priority=args.priority, deliverable=args.deliverable,
            thoughts=getattr(args, "thoughts", None), report=getattr(args, "report", None),
            dependencies=args.dependencies, locked_files=args.locked_files,
            acceptance_criteria=args.acceptance_criteria, conv_id=args.conv_id,
            origin=args.origin, subagent_conv_id=args.subagent_conv_id,
        )
    elif args.command == "vote-proposal":
        res = vote_proposal(
            voter=args.voter, comment=args.comment, voter_name=args.voter_name,
            voter_role=args.voter_role, stance=args.stance, confidence=args.confidence,
            counter_argument=args.counter_argument, conv_id=args.conv_id,
            origin=args.origin, subagent_conv_id=args.subagent_conv_id,
        )
    elif args.command == "finding-action":
        res = finding_action(
            finding_id=args.finding_id, action=args.action,
            reason=args.reason, conv_id=args.conv_id,
        )
    else:
        parser.print_help()
    if isinstance(res, dict) and res.get("status") == "error":
        sys.exit(1)


if __name__ == "__main__":
    main()
