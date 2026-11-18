#!/usr/bin/env python3
"""
Release & hygiene verification gate for team-orchestration-director (ThinkTank v4.0).
Checks manifest versions, canonical 7+1 agents, role_catalog & bridge_transport parity,
zero emojis, zero private leaks, py_compile, backend unittest, and sidecar ESM tests.
"""

from __future__ import annotations

import argparse
import json
import py_compile
import re
import shutil
import subprocess
import sys
from pathlib import Path

CANONICAL_ROLES = (
    "main_agent",
    "team-manager",
    "council-critic",
    "code-reviewer",
    "qa-reviewer",
    "ui-frontend-designer",
    "backend-auditor",
    "ecommerce_seo_operator",
    "wp_technical_operator",
)

CANONICAL_AGENT_FILES = tuple(f"{r}.md" for r in CANONICAL_ROLES if r != "main_agent")

EMOJI_PATTERN = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u26FF\u2700-\u27BF]")

LEAK_PATTERNS = (
    re.compile(r"C:\\\\?Users\\\\?[A-Za-z0-9_.-]+", re.IGNORECASE),
    re.compile(r"/(?:home|Users)/[A-Za-z0-9_.-]+"),
    re.compile(r"\x73aman-sa|\x6eabi-perfume|\x62ombhub|\x67erap|\x6dadgod", re.IGNORECASE),
    re.compile(r"\b(?:sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{20,}|fc-[0-9A-Za-z]{16,})\b"),
)

FORBIDDEN_ARTIFACTS = (
    "sidecars/think-tank/index.html.bak",
    "sidecars/think-tank/app.js",
    "sidecars/think-tank/i18n.js",
    "sidecars/think-tank/activity.js",
    "sidecars/think-tank/conversation-context.mjs",
    "sidecars/think-tank/ui-preferences.mjs",
    "backend/think_tank_live_state.json",
    "backend/active_antigravity_session.json",
)

SCAN_EXTENSIONS = {".py", ".js", ".mjs", ".cjs", ".html", ".css", ".json", ".md", ".toml"}
IGNORED_PARTS = {".git", "node_modules", "__pycache__", "_archived"}


def check_file_clean(path: Path) -> list[str]:
    issues: list[str] = []
    text = path.read_text(encoding="utf-8", errors="ignore")
    for pat in LEAK_PATTERNS:
        match = pat.search(text)
        if match:
            issues.append(f"Privacy/portability pattern {pat.pattern!r} matched {match.group(0)!r} in {path}")
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify ThinkTank v4.0 plugin release readiness")
    parser.add_argument("--skip-node-tests", action="store_true", help="Skip node --test ESM suite execution")
    parser.add_argument("--skip-backend-tests", action="store_true", help="Skip python unittest backend suite execution")
    args = parser.parse_args()

    plugin_root = Path(__file__).resolve().parent.parent
    errors: list[str] = []

    # 1. Manifest version parity
    for rel, expected in (
        ("plugin.json", "4.0.0"),
        ("package.json", "4.0.0"),
        ("sidecars/think-tank/package.json", "4.0.0"),
    ):
        p = plugin_root / rel
        if not p.is_file():
            errors.append(f"Missing manifest: {rel}")
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        if data.get("version") != expected:
            errors.append(f"Expected version {expected} in {rel}, got {data.get('version')!r}")

    sidecar_json = plugin_root / "sidecars/think-tank/sidecar.json"
    if not sidecar_json.is_file():
        errors.append("Missing sidecars/think-tank/sidecar.json")

    # 2. Canonical 8 agent profiles
    agents_dir = plugin_root / "agents"
    if not agents_dir.is_dir():
        errors.append("Missing agents/ directory")
    else:
        found_agents = sorted(p.name for p in agents_dir.iterdir() if p.is_file() and p.suffix == ".md")
        expected_agents = sorted(CANONICAL_AGENT_FILES)
        if found_agents != expected_agents:
            errors.append(f"Agent roster mismatch: expected {expected_agents}, found {found_agents}")
        ui_agent_path = agents_dir / "ui-frontend-designer.md"
        if ui_agent_path.is_file():
            ui_agent_text = ui_agent_path.read_text(encoding="utf-8")
            fm_match = re.match(r"^---\r?\n(.*?)\r?\n---", ui_agent_text, re.DOTALL)
            fm_text = fm_match.group(1) if fm_match else ""
            for req_skill in ("hallmark", "design-tokens", "responsive-layout", "accessibility-qa"):
                if not re.search(rf"^\s*-\s*{re.escape(req_skill)}\s*$", fm_text, re.MULTILINE):
                    errors.append(f"agents/ui-frontend-designer.md frontmatter missing required skill: {req_skill}")

    # 3. Role catalog byte parity + 9 roles + zero emojis
    sidecar_roles = plugin_root / "sidecars/think-tank/role_catalog.json"
    backend_roles = plugin_root / "backend/role_catalog.json"
    if not sidecar_roles.is_file() or not backend_roles.is_file():
        errors.append("Missing role_catalog.json in backend/ or sidecars/think-tank/")
    else:
        if sidecar_roles.read_bytes() != backend_roles.read_bytes():
            errors.append("Drift detected: backend/role_catalog.json does not match sidecars/think-tank/role_catalog.json")
        roles = json.loads(sidecar_roles.read_text(encoding="utf-8"))
        role_ids = {r.get("id") for r in roles}
        if len(roles) != 9 or role_ids != set(CANONICAL_ROLES):
            errors.append(f"role_catalog.json must have exact 9 canonical roles; got {sorted(role_ids)}")
        for r in roles:
            if EMOJI_PATTERN.search(json.dumps(r, ensure_ascii=False)):
                errors.append(f"Emoji detected in role_catalog.json entry {r.get('id')}")

    # 3b. Bridge transport byte parity
    be_transport = plugin_root / "backend/bridge_transport.py"
    tools_transport = plugin_root / "tools/bridge_transport.py"
    if not be_transport.is_file() or not tools_transport.is_file():
        errors.append("Missing bridge_transport.py in backend/ or tools/")
    elif be_transport.read_bytes() != tools_transport.read_bytes():
        errors.append("Drift detected: backend/bridge_transport.py does not match tools/bridge_transport.py")

    # 4. Required v4 files + zero emojis
    required_v4 = [
        "sidecars/think-tank/index.html",
        "sidecars/think-tank/tokens.css",
        "sidecars/think-tank/app.css",
        "sidecars/think-tank/main.mjs",
        "backend/app.py",
        "backend/ledger_domain.py",
        "backend/store.py",
        "backend/ws_hub.py",
        "backend/session_resolver.py",
        "tools/thinktank_bridge.py",
        "tools/thinktank_antigravity_hook.py",
        "tools/install_antigravity_hook.py",
        "tools/install_plugin.py",
        "skills/thinktank/SKILL.md",
        "commands/thinktank.toml",
        "README.md",
        "CHANGELOG.md",
        "CONTRIBUTING.md",
    ]
    for rel in required_v4:
        p = plugin_root / rel
        if not p.is_file():
            errors.append(f"Missing required v4 file: {rel}")
        elif EMOJI_PATTERN.search(p.read_text(encoding="utf-8")):
            errors.append(f"Unicode emoji detected in {rel}")

    for folder_rel, glob_pat in (
        ("sidecars/think-tank/src", "*.mjs"),
        ("backend", "*.py"),
        ("tools", "*.py"),
        ("skills", "*.md"),
        ("agents", "*.md"),
        ("rules", "*.md"),
        ("commands", "*.toml"),
    ):
        target_dir = plugin_root / folder_rel
        if target_dir.is_dir():
            for doc_path in sorted(target_dir.rglob(glob_pat)):
                if any(part in IGNORED_PARTS for part in doc_path.parts):
                    continue
                if EMOJI_PATTERN.search(doc_path.read_text(encoding="utf-8")):
                    errors.append(f"Unicode emoji detected in {doc_path.relative_to(plugin_root).as_posix()}")

    # 5. Forbidden runtime/legacy artifacts + sqlite/tmp scan
    for rel in FORBIDDEN_ARTIFACTS:
        if (plugin_root / rel).exists():
            errors.append(f"Stale/runtime artifact must be removed before release: {rel}")
    for pat in ("*.sqlite3*", "*.tmp"):
        for p in plugin_root.rglob(pat):
            if not any(part in IGNORED_PARTS for part in p.parts):
                errors.append(f"Runtime artifact should not be committed: {p.relative_to(plugin_root)}")

    # 6. Privacy/portability scan
    for p in plugin_root.rglob("*"):
        if not p.is_file() or (p.suffix.lower() not in SCAN_EXTENSIONS and p.name != "LICENSE"):
            continue
        if any(part in IGNORED_PARTS for part in p.parts):
            continue
        errors.extend(check_file_clean(p))

    # 7. Python py_compile across backend & tools
    for folder in ("backend", "tools"):
        for py_file in (plugin_root / folder).rglob("*.py"):
            if "__pycache__" in py_file.parts:
                continue
            try:
                py_compile.compile(str(py_file), doraise=True)
            except py_compile.PyCompileError as exc:
                errors.append(f"Python syntax check failed in {py_file.relative_to(plugin_root)}: {exc}")

    # 8. Backend unit tests
    if not args.skip_backend_tests:
        be_proc = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "backend", "-p", "test_*.py"],
            cwd=str(plugin_root),
            capture_output=True,
            text=True,
            check=False,
        )
        if be_proc.returncode != 0:
            errors.append(f"Backend unittest suite failed:\n{be_proc.stdout}\n{be_proc.stderr}".strip())

    # 9. Node syntax & ESM test suite
    node_bin = shutil.which("node")
    if not node_bin:
        errors.append("Node.js binary not found for JS verification")
    else:
        sidecar_dir = plugin_root / "sidecars/think-tank"
        js_targets = [sidecar_dir / "main.mjs"] + sorted((sidecar_dir / "src").rglob("*.mjs"))
        for js_file in js_targets:
            if js_file.is_file():
                proc = subprocess.run([node_bin, "--check", str(js_file)], capture_output=True, text=True, check=False)
                if proc.returncode != 0:
                    errors.append(f"Node syntax check failed for {js_file.relative_to(plugin_root)}: {proc.stderr.strip()}")
        if not args.skip_node_tests:
            test_files = sorted((sidecar_dir / "tests").glob("*.test.mjs"))
            if not test_files:
                errors.append("No ESM test files found under sidecars/think-tank/tests/*.test.mjs")
            else:
                test_proc = subprocess.run(
                    [node_bin, "--test", *[str(p.relative_to(sidecar_dir)) for p in test_files]],
                    cwd=str(sidecar_dir),
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if test_proc.returncode != 0:
                    errors.append(f"Sidecar ESM test suite failed:\n{test_proc.stdout}\n{test_proc.stderr}".strip())

    result = {
        "ok": len(errors) == 0,
        "pluginRoot": str(plugin_root),
        "errorCount": len(errors),
        "errors": errors,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
