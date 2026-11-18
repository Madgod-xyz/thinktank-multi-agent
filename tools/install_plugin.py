#!/usr/bin/env python3
"""
Portable installer & environment readiness verifier for team-orchestration-director (ThinkTank v4.0).
Resolves paths dynamically via Path(__file__) and Path.home(); contains zero hardcoded user paths.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

CANONICAL_AGENTS = (
    "team-manager.md",
    "council-critic.md",
    "code-reviewer.md",
    "qa-reviewer.md",
    "ui-frontend-designer.md",
    "backend-auditor.md",
    "ecommerce_seo_operator.md",
    "wp_technical_operator.md",
)

IGNORED_COPY_NAMES = {
    "__pycache__",
    "node_modules",
    ".git",
    "index.html.bak",
    "think_tank_live_state.json",
    "active_antigravity_session.json",
}

IGNORED_COPY_SUFFIXES = (".pyc", ".pyo", ".bak", ".tmp", ".sqlite3", ".sqlite3-wal", ".sqlite3-shm")

STALE_V3_SIDECAR_FILES = (
    "roles.css",
    "tailwind.js",
    "app.js",
    "i18n.js",
    "activity.js",
    "conversation-context.mjs",
    "ui-preferences.mjs",
)


def get_plugin_root() -> Path:
    return Path(__file__).resolve().parent.parent


def get_default_target_dir() -> Path:
    env_dir = os.environ.get("GEMINI_CONFIG_DIR", "").strip()
    if env_dir:
        return Path(env_dir).expanduser().resolve()
    return (Path.home() / ".gemini" / "config").resolve()


def check_backend_health(host: str, port: int, timeout: float = 1.5) -> tuple[bool, str]:
    url = f"http://{host}:{port}/api/health"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            if 200 <= resp.status < 300:
                return True, f"healthy ({resp.status})"
            return False, f"unexpected HTTP {resp.status}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return False, str(exc)


def run_checks(plugin_root: Path, host: str, port: int, require_backend: bool = False) -> dict:
    errors: list[str] = []
    warnings: list[str] = []

    if sys.version_info < (3, 10):
        errors.append(f"Python >= 3.10 required; found {sys.version.split()[0]}")

    node_path = shutil.which("node")
    node_version = None
    if node_path:
        proc = subprocess.run([node_path, "--version"], capture_output=True, text=True, check=False)
        node_version = proc.stdout.strip() if proc.returncode == 0 else None
    else:
        errors.append("Node.js binary ('node') not found in PATH")

    required_files = [
        "plugin.json",
        "package.json",
        "backend/app.py",
        "backend/catalog.py",
        "backend/governance.py",
        "backend/ledger_domain.py",
        "backend/store.py",
        "backend/sync_store.py",
        "backend/session_resolver.py",
        "backend/ws_hub.py",
        "backend/requirements.txt",
        "backend/role_catalog.json",
        "sidecars/think-tank/sidecar.json",
        "sidecars/think-tank/main.mjs",
        "sidecars/think-tank/index.html",
        "sidecars/think-tank/tokens.css",
        "sidecars/think-tank/app.css",
        "sidecars/think-tank/role_catalog.json",
        "sidecars/think-tank/src/store.mjs",
        "sidecars/think-tank/src/sync.mjs",
        "tools/thinktank_bridge.py",
        "tools/bridge_transport.py",
        "tools/thinktank_antigravity_hook.py",
        "tools/install_antigravity_hook.py",
        "skills/thinktank/SKILL.md",
        "commands/thinktank.toml",
        "rules/AGENTS.md",
    ]
    for rel in required_files:
        if not (plugin_root / rel).is_file():
            errors.append(f"Missing required plugin file: {rel}")

    agents_dir = plugin_root / "agents"
    for agent_file in CANONICAL_AGENTS:
        if not (agents_dir / agent_file).is_file():
            errors.append(f"Missing canonical agent profile: agents/{agent_file}")

    missing_py_deps = [
        pkg for pkg in ("fastapi", "uvicorn", "pydantic", "httpx")
        if importlib.util.find_spec(pkg) is None
    ]
    if missing_py_deps:
        errors.append(
            f"Missing Python packages for backend: {', '.join(missing_py_deps)} "
            f"(install with: {sys.executable} -m pip install -r backend/requirements.txt)"
        )

    backend_up, backend_msg = check_backend_health(host, port)
    if not backend_up:
        if require_backend:
            errors.append(f"Backend not reachable at http://{host}:{port}: {backend_msg}")
        else:
            warnings.append(f"Backend not currently running on http://{host}:{port} ({backend_msg})")

    return {
        "ok": len(errors) == 0,
        "pluginRoot": str(plugin_root),
        "python": sys.version.split()[0],
        "node": node_version,
        "backendReachable": backend_up,
        "errors": errors,
        "warnings": warnings,
    }


def _ignore_copy(_src: str, names: list[str]) -> list[str]:
    return [n for n in names if n in IGNORED_COPY_NAMES or n.endswith(IGNORED_COPY_SUFFIXES)]


def _prune_stale_sidecar_assets(src_sidecar: Path, dst_sidecar: Path) -> list[str]:
    removed: list[str] = []
    if not dst_sidecar.is_dir() or src_sidecar.resolve() == dst_sidecar.resolve():
        return removed
    for stale_rel in STALE_V3_SIDECAR_FILES:
        stale_file = dst_sidecar / stale_rel
        if stale_file.is_file() or stale_file.is_symlink():
            stale_file.unlink()
            removed.append(str(stale_file))
    dst_tests = dst_sidecar / "tests"
    if dst_tests.is_dir():
        for cjs_test in dst_tests.glob("*.cjs"):
            cjs_test.unlink()
            removed.append(str(cjs_test))
        src_tests = src_sidecar / "tests"
        valid_mjs_tests = {p.name for p in src_tests.glob("*.mjs")} if src_tests.is_dir() else set()
        for mjs_test in dst_tests.glob("*.mjs"):
            if mjs_test.name not in valid_mjs_tests:
                mjs_test.unlink()
                removed.append(str(mjs_test))
    stale_fonts_dir = dst_sidecar / "assets" / "fonts"
    if stale_fonts_dir.exists():
        shutil.rmtree(stale_fonts_dir, ignore_errors=True)
        removed.append(str(stale_fonts_dir))
    src_avatars_dir = src_sidecar / "assets" / "avatars"
    dst_avatars_dir = dst_sidecar / "assets" / "avatars"
    if dst_avatars_dir.is_dir():
        valid_svgs = {p.name for p in src_avatars_dir.glob("*.svg")} if src_avatars_dir.is_dir() else set()
        for candidate in dst_avatars_dir.glob("*.svg"):
            if candidate.name not in valid_svgs:
                candidate.unlink()
                removed.append(str(candidate))
    return removed


def _prune_stale_backend_files(src_backend: Path, dst_backend: Path) -> list[str]:
    removed: list[str] = []
    if not dst_backend.is_dir() or src_backend.resolve() == dst_backend.resolve():
        return removed
    valid_tests = {p.name for p in src_backend.glob("test_*.py")} if src_backend.is_dir() else set()
    for stale_test in dst_backend.glob("test_*.py"):
        if stale_test.name not in valid_tests:
            stale_test.unlink()
            removed.append(str(stale_test))
    return removed


def _prune_orphaned_session_tmps(target_dir: Path) -> int:
    count = 0
    if not target_dir.is_dir():
        return 0
    for tmp_file in target_dir.glob("active_antigravity_session*.tmp"):
        try:
            tmp_file.unlink()
            count += 1
        except OSError:
            pass
    return count


def install_plugin(plugin_root: Path, target_dir: Path, *, install_hook: bool = True) -> dict:
    tools_dest = target_dir / "tools"
    tools_dest.mkdir(parents=True, exist_ok=True)
    copied_tools: list[str] = []
    for filename in (
        "thinktank_bridge.py",
        "bridge_transport.py",
        "thinktank_antigravity_hook.py",
        "install_antigravity_hook.py",
    ):
        src = plugin_root / "tools" / filename
        dst = tools_dest / filename
        if src.resolve() != dst.resolve():
            shutil.copy2(src, dst)
        copied_tools.append(str(dst))

    commands_src = plugin_root / "commands"
    copied_commands: list[str] = []
    if commands_src.is_dir():
        cmd_targets = [target_dir / "commands"]
        if target_dir.name == "config":
            cmd_targets.append(target_dir.parent / "commands")
        for cmd_dest in cmd_targets:
            cmd_dest.mkdir(parents=True, exist_ok=True)
            for src_toml in sorted(commands_src.glob("*.toml")):
                dst_toml = cmd_dest / src_toml.name
                if src_toml.resolve() != dst_toml.resolve():
                    shutil.copy2(src_toml, dst_toml)
                copied_commands.append(str(dst_toml))

    runtime_sidecar_src = plugin_root / "sidecars" / "think-tank"
    plugin_dest = target_dir / "plugins" / "team-orchestration-director"
    copied_plugin = False
    pruned_files: list[str] = []
    if plugin_root.resolve() != plugin_dest.resolve():
        plugin_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(plugin_root, plugin_dest, dirs_exist_ok=True, ignore=_ignore_copy)
        pruned_files.extend(_prune_stale_sidecar_assets(runtime_sidecar_src, plugin_dest / "sidecars" / "think-tank"))
        pruned_files.extend(_prune_stale_backend_files(plugin_root / "backend", plugin_dest / "backend"))
        for stale_rel in ("agents/_archived", "data-evidence-pack"):
            stale_path = plugin_dest / stale_rel
            if stale_path.exists():
                shutil.rmtree(stale_path, ignore_errors=True)
                pruned_files.append(str(stale_path))
        src_agents_dir = plugin_root / "agents"
        dst_agents_dir = plugin_dest / "agents"
        if src_agents_dir.is_dir() and dst_agents_dir.is_dir():
            valid_agents = {p.name for p in src_agents_dir.glob("*.md")}
            for stale_agent in dst_agents_dir.glob("*.md"):
                if stale_agent.name not in valid_agents:
                    stale_agent.unlink()
                    pruned_files.append(str(stale_agent))
        dst_commands_dir = plugin_dest / "commands"
        if dst_commands_dir.is_dir():
            valid_commands = {p.name for p in commands_src.glob("*.toml")} if commands_src.is_dir() else set()
            for stale_cmd in dst_commands_dir.glob("*.toml"):
                if stale_cmd.name not in valid_commands:
                    stale_cmd.unlink()
                    pruned_files.append(str(stale_cmd))
        copied_plugin = True

    src_agents_dir = plugin_root / "agents"
    global_agents_dir = target_dir / "agents"
    if src_agents_dir.is_dir() and global_agents_dir.is_dir():
        for src_agent in sorted(src_agents_dir.glob("*.md")):
            dst_agent = global_agents_dir / src_agent.name
            if src_agent.resolve() != dst_agent.resolve():
                shutil.copy2(src_agent, dst_agent)

    runtime_root = target_dir / "thinktank"
    runtime_backend_src = plugin_root / "backend"
    runtime_backend_dst = runtime_root / "backend"
    if runtime_backend_src.is_dir() and runtime_backend_src.resolve() != runtime_backend_dst.resolve():
        runtime_backend_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(runtime_backend_src, runtime_backend_dst, dirs_exist_ok=True, ignore=_ignore_copy)
        pruned_files.extend(_prune_stale_backend_files(runtime_backend_src, runtime_backend_dst))

    runtime_sidecar_dst = runtime_root / "sidecars" / "think-tank"
    if runtime_sidecar_src.is_dir() and runtime_sidecar_src.resolve() != runtime_sidecar_dst.resolve():
        runtime_sidecar_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(runtime_sidecar_src, runtime_sidecar_dst, dirs_exist_ok=True, ignore=_ignore_copy)
        pruned_files.extend(_prune_stale_sidecar_assets(runtime_sidecar_src, runtime_sidecar_dst))

    runtime_root.mkdir(parents=True, exist_ok=True)
    runtime_meta_path = runtime_root / "runtime.json"
    runtime_meta_path.write_text(
        json.dumps({"pythonExecutable": str(Path(sys.executable))}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    pruned_tmp_count = _prune_orphaned_session_tmps(target_dir)

    hooks_installed = False
    hooks_error = None
    hooks_config = target_dir / "hooks.json"
    if install_hook:
        try:
            tools_dir_str = str((plugin_root / "tools").resolve())
            if tools_dir_str not in sys.path:
                sys.path.insert(0, tools_dir_str)
            import install_antigravity_hook

            install_antigravity_hook.install(
                config_path=hooks_config,
                python_executable=sys.executable,
                hook_script=tools_dest / "thinktank_antigravity_hook.py",
            )
            hooks_installed = True
        except (ImportError, OSError, ValueError) as exc:
            hooks_error = str(exc)

    db_compacted = None
    sync_db = target_dir / "think_tank_sync.sqlite3"
    wal_db = Path(f"{sync_db}-wal")
    total_db_bytes = (sync_db.stat().st_size if sync_db.is_file() else 0) + (wal_db.stat().st_size if wal_db.is_file() else 0)
    if sync_db.is_file() and total_db_bytes > 20 * 1024 * 1024:
        live_up, _ = check_backend_health("127.0.0.1", 8780, timeout=0.5)
        if live_up:
            db_compacted = {"skipped": "backend_running"}
        else:
            try:
                backend_dir_str = str((plugin_root / "backend").resolve())
                if backend_dir_str not in sys.path:
                    sys.path.insert(0, backend_dir_str)
                from store import SyncEventStore

                store = SyncEventStore(str(sync_db))
                try:
                    db_compacted = store.prune_bloat(telemetry_keep=20, vacuum=True)
                finally:
                    store.close()
            except Exception as exc:
                db_compacted = {"error": str(exc)}

    result: dict = {
        "targetDir": str(target_dir),
        "pluginInstallPath": str(plugin_dest),
        "runtimeBackendPath": str(runtime_backend_dst),
        "runtimeSidecarPath": str(runtime_sidecar_dst),
        "runtimeConfigPath": str(runtime_meta_path),
        "copiedPluginTree": copied_plugin,
        "bridgeTools": copied_tools,
        "copiedCommands": copied_commands,
        "hooksInstalled": hooks_installed,
        "hooksSkipped": not install_hook,
        "hooksConfigPath": str(hooks_config),
        "prunedFilesCount": len(pruned_files),
        "prunedTmpFiles": pruned_tmp_count,
    }
    if db_compacted is not None:
        result["dbCompacted"] = db_compacted
    if hooks_error:
        result["hooksError"] = hooks_error
    return result


def stop_backend(host: str, port: int) -> dict:
    up, _ = check_backend_health(host, port, timeout=0.8)
    if not up:
        return {"stopped": False, "wasRunning": False, "url": f"http://{host}:{port}"}
    killed_pids: list[int] = []
    if os.name == "nt":
        ps_cmd = (
            f"Get-CimInstance Win32_Process | Where-Object {{ $_.CommandLine -match 'uvicorn' -and $_.CommandLine -match 'app:app' -and $_.CommandLine -match '{port}' }} | "
            "Select-Object -ExpandProperty ProcessId"
        )
        proc = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True, check=False)
        for line in proc.stdout.splitlines():
            if line.strip().isdigit():
                pid = int(line.strip())
                subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, check=False)
                killed_pids.append(pid)
    else:
        proc = subprocess.run(["lsof", "-ti", f"tcp:{port}"], capture_output=True, text=True, check=False)
        for line in proc.stdout.splitlines():
            if line.strip().isdigit():
                pid = int(line.strip())
                try:
                    os.kill(pid, signal.SIGTERM)
                    killed_pids.append(pid)
                except OSError:
                    pass
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        still_up, _ = check_backend_health(host, port, timeout=0.3)
        if not still_up:
            return {"stopped": True, "wasRunning": True, "pids": killed_pids, "url": f"http://{host}:{port}"}
        time.sleep(0.15)
    still_up, _ = check_backend_health(host, port, timeout=0.3)
    return {"stopped": not still_up, "wasRunning": True, "pids": killed_pids, "url": f"http://{host}:{port}"}


def start_backend(plugin_root: Path, host: str, port: int) -> dict:
    already_up, _ = check_backend_health(host, port)
    if already_up:
        return {"started": False, "alreadyRunning": True, "url": f"http://{host}:{port}"}

    backend_dir = plugin_root / "backend"
    creation_flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    kwargs: dict = {
        "cwd": str(backend_dir),
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
    }
    if os.name == "nt":
        kwargs["creationflags"] = creation_flags
    else:
        kwargs["start_new_session"] = True

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", host, "--port", str(port)],
        **kwargs,
    )
    return {"started": True, "pid": proc.pid, "url": f"http://{host}:{port}"}


def main() -> int:
    parser = argparse.ArgumentParser(description="ThinkTank v4.0 Plugin Installer & Readiness Checker")
    parser.add_argument("--check", action="store_true", help="Verify runtime dependencies, canonical agents, and files")
    parser.add_argument("--install", action="store_true", help="Sync bridge tools and plugin tree to Antigravity config dir")
    parser.add_argument("--no-hook", action="store_true", help="Skip installing hooks.json entries during --install")
    parser.add_argument("--target-dir", default="", help="Override Antigravity config root (defaults to ~/.gemini/config)")
    parser.add_argument("--stop-backend", action="store_true", help="Stop running ThinkTank backend on host:port")
    parser.add_argument("--start-backend", action="store_true", help="Start FastAPI backend if not already listening")
    parser.add_argument("--require-backend", action="store_true", help="Fail check if backend health endpoint is unreachable")
    parser.add_argument("--host", default="127.0.0.1", help="Backend bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8780, help="Backend bind port (default: 8780)")
    args = parser.parse_args()

    if not (args.check or args.install or args.start_backend or args.stop_backend):
        args.check = True

    plugin_root = get_plugin_root()
    report: dict = {}

    if args.stop_backend:
        report["stopBackend"] = stop_backend(args.host, args.port)

    if args.check or args.install:
        check_res = run_checks(plugin_root, args.host, args.port, require_backend=args.require_backend)
        report["check"] = check_res
        if not check_res["ok"]:
            print(json.dumps(report, indent=2, ensure_ascii=False))
            return 1

    if args.install:
        target_dir = Path(args.target_dir).expanduser().resolve() if args.target_dir else get_default_target_dir()
        report["install"] = install_plugin(plugin_root, target_dir, install_hook=not args.no_hook)

    if args.start_backend:
        report["backend"] = start_backend(plugin_root, args.host, args.port)

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
