#!/usr/bin/env python3
"""Dependency-free CI checks for the distributable Figure Acceptance package."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = ROOT / "plugins" / "figure-acceptance"
MANIFEST = PLUGIN_ROOT / ".codex-plugin" / "plugin.json"
MARKETPLACE = ROOT / ".agents" / "plugins" / "marketplace.json"


def fail(message: str) -> None:
    print(f"package validation: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"cannot read {path.relative_to(ROOT)}: {exc}")
    if not isinstance(value, dict):
        fail(f"{path.relative_to(ROOT)} must contain a JSON object")
    return value


def main() -> int:
    manifest = load_json(MANIFEST)
    for key in ("name", "version", "description", "author", "skills", "interface"):
        if key not in manifest:
            fail(f"manifest missing {key}")
    if manifest["name"] != "figure-acceptance":
        fail("manifest name must be figure-acceptance")
    if re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?", manifest["version"]) is None:
        fail("manifest version is not strict semver")
    if not isinstance(manifest["author"], dict) or not manifest["author"].get("name"):
        fail("manifest author.name is required")
    interface = manifest["interface"]
    for key in ("displayName", "shortDescription", "longDescription", "developerName", "category", "defaultPrompt"):
        if not interface.get(key):
            fail(f"manifest interface.{key} is required")
    if not (PLUGIN_ROOT / "skills" / "figure-acceptance" / "SKILL.md").is_file():
        fail("plugin skill is missing")
    if not (PLUGIN_ROOT / "assets" / "auditor-policy.md").is_file():
        fail("auditor policy is missing")
    marketplace = load_json(MARKETPLACE)
    if marketplace.get("name") != "figure-acceptance":
        fail("marketplace name must be figure-acceptance")
    entries = marketplace.get("plugins", [])
    entry = next((item for item in entries if item.get("name") == "figure-acceptance"), None)
    if not entry:
        fail("marketplace does not include figure-acceptance")
    if entry.get("source", {}).get("path") != "./plugins/figure-acceptance":
        fail("marketplace path must be ./plugins/figure-acceptance")
    policy = entry.get("policy", {})
    if policy.get("installation") != "AVAILABLE" or policy.get("authentication") != "ON_INSTALL":
        fail("marketplace install/authentication policy is invalid")
    print("package validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
