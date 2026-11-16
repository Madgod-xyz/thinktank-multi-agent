#!/usr/bin/env python3
"""Install the Think Tank Antigravity lifecycle hooks without replacing other hooks."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


HOOK_NAME = "thinktank-live-sync"


def _command(python_executable: str | Path, hook_script: str | Path, event: str) -> str:
    return subprocess.list2cmdline([str(python_executable), str(hook_script), event])


def hook_definition(python_executable: str | Path, hook_script: str | Path) -> dict[str, Any]:
    return {
        "enabled": True,
        "PreInvocation": [{
            "type": "command",
            "command": _command(python_executable, hook_script, "pre-invocation"),
            "timeout": 5,
        }],
        "PostToolUse": [{
            "matcher": "*",
            "hooks": [{
                "type": "command",
                "command": _command(python_executable, hook_script, "post-tool-use"),
                "timeout": 3,
            }],
        }],
    }


def install(
    config_path: str | Path | None = None,
    python_executable: str | Path | None = None,
    hook_script: str | Path | None = None,
) -> dict[str, Any]:
    target = Path(config_path).expanduser() if config_path else Path.home() / ".gemini" / "config" / "hooks.json"
    executable = python_executable or sys.executable
    script = Path(hook_script).expanduser() if hook_script else Path(__file__).with_name("thinktank_antigravity_hook.py")

    if target.exists():
        try:
            existing = json.loads(target.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"Existing hooks file is not valid JSON; left unchanged: {target}") from error
        if not isinstance(existing, dict):
            raise ValueError(f"Existing hooks file must contain a JSON object; left unchanged: {target}")
    else:
        existing = {}

    merged = dict(existing)
    merged[HOOK_NAME] = hook_definition(executable, script)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=target.parent,
            prefix=f"{target.name}.", suffix=".tmp", delete=False,
        ) as output:
            temp_name = output.name
            json.dump(merged, output, ensure_ascii=False, indent=2)
            output.write("\n")
        os.replace(temp_name, target)
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)
    return merged


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, help="Antigravity hooks.json path")
    parser.add_argument("--python", dest="python_executable", help="Python executable used by the hook")
    parser.add_argument("--hook-script", type=Path, help="Installed thinktank_antigravity_hook.py path")
    args = parser.parse_args()
    try:
        install(args.config, args.python_executable, args.hook_script)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(f"Installed {HOOK_NAME} in {args.config or (Path.home() / '.gemini' / 'config' / 'hooks.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
