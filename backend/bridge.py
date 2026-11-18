"""Explicitly configured project tool adapters for ThinkTank."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any


def configured_adapters() -> dict[str, str]:
    try:
        val = json.loads(os.environ.get("THINKTANK_TOOL_ADAPTERS", "{}"))
    except (TypeError, json.JSONDecodeError):
        return {}
    return {str(k): str(v) for k, v in val.items() if k and v} if isinstance(val, dict) else {}


def run_python_tool(script_path: str, args: list[str], timeout: int = 25) -> dict[str, Any]:
    path = Path(script_path).expanduser()
    if not path.is_absolute():
        return {"success": False, "error": "Adapter path must be absolute.", "output": ""}
    if not path.is_file():
        return {"success": False, "error": f"Configured adapter not found: {path}", "output": ""}
    try:
        proc = subprocess.run(
            [sys.executable, str(path), *args],
            capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace", shell=False,
        )
        out, err = proc.stdout.strip(), proc.stderr.strip()
        try:
            data = json.loads(out)
        except (TypeError, json.JSONDecodeError):
            data = None
        return {"success": proc.returncode == 0, "returncode": proc.returncode, "output": out or err, "error": err, "data": data}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"Tool execution timed out after {timeout}s", "output": ""}
    except Exception as exc:
        return {"success": False, "error": str(exc), "output": ""}


def execute_subagent_command(agent_id: str, command: str) -> dict[str, Any]:
    base = {"agentId": agent_id, "command": command}
    try:
        parts = shlex.split(command, posix=(os.name != "nt"))
    except ValueError as exc:
        return {**base, "success": False, "output": "", "error": f"Could not parse adapter arguments: {exc}"}
    if len(parts) < 2 or parts[0].lower() != "adapter":
        return {**base, "success": False, "output": "", "error": "No matching configured adapter; command was not executed."}
    script_path = configured_adapters().get(parts[1])
    if not script_path:
        return {**base, "success": False, "output": "", "error": f"Adapter '{parts[1]}' is not configured; command was not executed."}
    res = run_python_tool(script_path, parts[2:])
    return {**base, "success": res["success"], "output": res["output"], "error": res["error"] if not res["success"] else None}
