#!/usr/bin/env python3
"""Dependency-free CI checks for the distributable Visual Inspection package."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = ROOT / "plugins" / "visual-inspection"
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
    if manifest["name"] != "visual-inspection":
        fail("manifest name must be visual-inspection")
    if re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?", manifest["version"]) is None:
        fail("manifest version is not strict semver")
    if not isinstance(manifest["author"], dict) or not manifest["author"].get("name"):
        fail("manifest author.name is required")
    interface = manifest["interface"]
    for key in ("displayName", "shortDescription", "longDescription", "developerName", "category", "defaultPrompt"):
        if not interface.get(key):
            fail(f"manifest interface.{key} is required")
    if not (PLUGIN_ROOT / "skills" / "visual-inspection" / "SKILL.md").is_file():
        fail("plugin skill is missing")
    if not (PLUGIN_ROOT / "assets" / "auditor-policy.md").is_file():
        fail("auditor policy is missing")
    marketplace = load_json(MARKETPLACE)
    if marketplace.get("name") != "visual-inspection":
        fail("marketplace name must be visual-inspection")
    entries = marketplace.get("plugins", [])
    entry = next((item for item in entries if item.get("name") == "visual-inspection"), None)
    if not entry:
        fail("marketplace does not include visual-inspection")
    if entry.get("source", {}).get("path") != "./plugins/visual-inspection":
        fail("marketplace path must be ./plugins/visual-inspection")
    policy = entry.get("policy", {})
    if policy.get("installation") != "AVAILABLE" or policy.get("authentication") != "ON_INSTALL":
        fail("marketplace install/authentication policy is invalid")
    provenance = ROOT / "fixtures" / "public" / "asset_provenance.json"
    data = json.loads(provenance.read_text(encoding="utf-8"))
    banned = ("figure_error_exemptions_2026.pdf", "figure-error-compendium", "codex-clipboard")
    for asset in data.get("assets", []):
        source = asset.get("source", "")
        if not asset.get("sha256") or not asset.get("source_project"):
            fail("every source-derived asset needs source_project and sha256")
        if any(token in source for token in banned):
            fail(f"fixture source is a forbidden report or attachment: {source}")
    print("package validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
