from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as etree
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = REPO_ROOT / "docs" / "assets"
RENDER_SCRIPT = REPO_ROOT / "scripts" / "render_readme_report.py"


class DocumentationTests(unittest.TestCase):
    def test_public_docs_have_parseable_visual_assets_and_no_private_path(self) -> None:
        required_assets = {
            "architecture-en.svg",
            "architecture-zh-CN.svg",
            "requirements-precedence-en.svg",
            "requirements-precedence-zh-CN.svg",
            "audit-fail-en.svg",
            "audit-fail-zh-CN.svg",
            "audit-pass-en.svg",
            "audit-pass-zh-CN.svg",
        }
        self.assertTrue(required_assets.issubset({path.name for path in ASSET_DIR.glob("*.svg")}))
        for path in ASSET_DIR.glob("*.svg"):
            etree.parse(path)
        for path in (REPO_ROOT / "README.md", REPO_ROOT / "README.zh-CN.md", REPO_ROOT / "docs" / "TEST_RESULTS.md"):
            content = path.read_text(encoding="utf-8")
            self.assertNotIn("/Users/lazychild", content)
            self.assertNotIn("codex-clipboard-", content)

    def test_report_renderer_leaves_room_for_empty_state_footer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "run"
            run_dir.mkdir()
            (run_dir / "summary.json").write_text(
                json.dumps(
                    {
                        "overall_status": "PASS",
                        "coverage": {"expected": 2, "completed": 2},
                    }
                ),
                encoding="utf-8",
            )
            (run_dir / "findings.jsonl").write_text("", encoding="utf-8")
            output = Path(temporary) / "result.svg"
            result = subprocess.run(
                [sys.executable, str(RENDER_SCRIPT), "--run-dir", str(run_dir), "--output", str(output), "--lang", "en"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            root = etree.parse(output).getroot()
            self.assertGreaterEqual(int(root.attrib["height"]), 440)
            self.assertIn("No blocking findings", output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
