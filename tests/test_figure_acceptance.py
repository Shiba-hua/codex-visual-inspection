from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "plugins" / "figure-acceptance" / "scripts" / "figure_acceptance.py"
POLICY = REPO_ROOT / "plugins" / "figure-acceptance" / "assets" / "auditor-policy.md"
FIXTURE_ROOT = REPO_ROOT / "fixtures" / "public"

spec = importlib.util.spec_from_file_location("figure_acceptance", SCRIPT)
assert spec and spec.loader
figure_acceptance = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = figure_acceptance
spec.loader.exec_module(figure_acceptance)


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_svg(path: Path, label: str = "fixture") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="120" height="80"><text x="10" y="40">{label}</text></svg>',
        encoding="utf-8",
    )


class FigureAcceptanceTests(unittest.TestCase):
    maxDiff = None

    def command(self, *args: str, expected: int | None = 0) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if expected is not None:
            self.assertEqual(result.returncode, expected, msg=result.stderr + result.stdout)
        return result

    def discover_image(self, root: Path) -> tuple[Path, list[dict]]:
        image_dir = root / "images"
        write_svg(image_dir / "good.svg")
        run_dir = root / "audit"
        self.command("discover", "--target", str(image_dir), "--run-dir", str(run_dir))
        return run_dir, jsonl(run_dir / "figure_inventory.jsonl")

    def test_markdown_discovers_each_logical_placement_and_marker_roles(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_svg(root / "assets" / "tree.svg", "tree")
            write_svg(root / "assets" / "redraw.svg", "redraw")
            requirements = root / "requirements.json"
            requirements.write_text(
                json.dumps({"explicit": [{"id": "caption-required", "text": "Caption must be present."}]}),
                encoding="utf-8",
            )
            markdown = root / "report.md"
            markdown.write_text(
                "<!-- figure-acceptance: role=source_figure pair_id=pair-01 -->\n"
                "![source](assets/tree.svg)\n\n"
                "<!-- figure-acceptance: role=author_redraw pair_id=pair-01 -->\n"
                "![redraw](assets/redraw.svg)\n",
                encoding="utf-8",
            )
            run_dir = root / "audit"
            self.command(
                "discover",
                "--target",
                str(markdown),
                "--requirements-file",
                str(requirements),
                "--run-dir",
                str(run_dir),
            )
            inventory = jsonl(run_dir / "figure_inventory.jsonl")
            tasks = jsonl(run_dir / "audit_tasks.jsonl")
            self.assertEqual(2, len(inventory))
            self.assertEqual(["source_figure", "author_redraw"], [item["asset_role"] for item in inventory])
            self.assertEqual(["pair-01", "pair-01"], [item["pair_id"] for item in inventory])
            self.assertEqual(2, len(tasks))
            self.assertTrue(all(task["required_model"] == "gpt-5.6-luna" for task in tasks))
            self.assertEqual(
                ["reference_only", "compare_candidate_to_source"],
                [task["relationship_review_mode"] for task in tasks],
            )
            self.assertTrue(any(item["id"] == "caption-required" for item in tasks[0]["requirements"]))

    def test_latex_extracts_graphic_caption_and_label(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_svg(root / "figures" / "tree.svg")
            tex = root / "main.tex"
            tex.write_text(
                "\\begin{figure}\n"
                "\\includegraphics[width=\\linewidth]{figures/tree.svg}\n"
                "\\caption{A \\textbf{self-drawn} tree.}\n"
                "\\label{fig:tree}\n"
                "\\end{figure}\n",
                encoding="utf-8",
            )
            run_dir = root / "audit"
            self.command("discover", "--target", str(tex), "--run-dir", str(run_dir))
            inventory = jsonl(run_dir / "figure_inventory.jsonl")
            self.assertEqual(1, len(inventory))
            self.assertTrue(inventory[0]["asset_exists"])
            self.assertEqual("fig:tree", inventory[0]["label"])
            self.assertIn("self-drawn", inventory[0]["caption"])
            manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(manifest["blocking_warnings"])

    def test_image_directory_ignores_non_image_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            image_dir = root / "images"
            write_svg(image_dir / "one.svg")
            (image_dir / "notes.txt").write_text("not an image", encoding="utf-8")
            run_dir = root / "audit"
            self.command("discover", "--target", str(image_dir), "--run-dir", str(run_dir))
            self.assertEqual(1, len(jsonl(run_dir / "figure_inventory.jsonl")))

    def test_validate_pass_writes_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir, inventory = self.discover_image(Path(temporary))
            finding = {
                "task_id": inventory[0]["figure_id"],
                "status": "PASS",
                "model": "gpt-5.6-luna",
                "confidence_note": "The complete self-drawn asset is available.",
                "findings": [],
            }
            (run_dir / "findings.jsonl").write_text(json.dumps(finding) + "\n", encoding="utf-8")
            self.command("validate", "--run-dir", str(run_dir))
            summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual("PASS", summary["overall_status"])
            self.assertEqual(1, summary["coverage"]["completed"])

    def test_validate_fail_writes_repair_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir, inventory = self.discover_image(Path(temporary))
            finding = {
                "task_id": inventory[0]["figure_id"],
                "status": "FAIL",
                "model": "gpt-5.6-luna",
                "confidence_note": "A visible mismatch is confirmed.",
                "findings": [
                    {
                        "category": "semantic_mismatch",
                        "severity": "blocking",
                        "evidence": "The claimed redraw is unrelated to the source decision tree.",
                        "violated_requirements": ["default.semantic-consistency"],
                        "repair_action": "Replace the unrelated asset with a corresponding redraw.",
                    }
                ],
            }
            (run_dir / "findings.jsonl").write_text(json.dumps(finding) + "\n", encoding="utf-8")
            self.command("validate", "--run-dir", str(run_dir))
            summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual("FAIL", summary["overall_status"])
            handoff = (run_dir / "repair_handoff.md").read_text(encoding="utf-8")
            self.assertIn("Replace the unrelated asset", handoff)

    def test_missing_result_is_needs_human(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir, _ = self.discover_image(Path(temporary))
            self.command("validate", "--run-dir", str(run_dir), expected=2)
            summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual("NEEDS_HUMAN", summary["overall_status"])
            self.assertEqual(["figure-0001"], summary["coverage"]["missing"])

    def test_non_luna_result_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir, inventory = self.discover_image(Path(temporary))
            finding = {
                "task_id": inventory[0]["figure_id"],
                "status": "PASS",
                "model": "gpt-5.6-terra",
                "findings": [],
            }
            (run_dir / "findings.jsonl").write_text(json.dumps(finding) + "\n", encoding="utf-8")
            self.command("validate", "--run-dir", str(run_dir), expected=2)
            summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual("NEEDS_HUMAN", summary["overall_status"])
            self.assertTrue(summary["coverage"]["invalid"])
            self.assertEqual(["figure-0001"], summary["coverage"]["model_violations"])

    def test_unknown_requirement_id_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir, inventory = self.discover_image(Path(temporary))
            finding = {
                "task_id": inventory[0]["figure_id"],
                "status": "FAIL",
                "model": "gpt-5.6-luna",
                "findings": [
                    {
                        "category": "crop_truncation",
                        "severity": "blocking",
                        "evidence": "The left label is cut off.",
                        "violated_requirements": ["1"],
                        "repair_action": "Expand the crop boundary.",
                    }
                ],
            }
            (run_dir / "findings.jsonl").write_text(json.dumps(finding) + "\n", encoding="utf-8")
            self.command("validate", "--run-dir", str(run_dir), expected=2)
            summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual("NEEDS_HUMAN", summary["overall_status"])
            self.assertIn("unknown requirement ids: 1", summary["finding_errors"]["figure-0001"][0])

    def test_conflicting_requirements_force_human_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_svg(root / "images" / "good.svg")
            requirements = root / "requirements.json"
            requirements.write_text(
                json.dumps(
                    {
                        "conflicts": [
                            {"requirement_a": "include full caption", "requirement_b": "exclude all captions"}
                        ]
                    }
                ),
                encoding="utf-8",
            )
            run_dir = root / "audit"
            self.command(
                "discover",
                "--target",
                str(root / "images"),
                "--requirements-file",
                str(requirements),
                "--run-dir",
                str(run_dir),
            )
            inventory = jsonl(run_dir / "figure_inventory.jsonl")
            (run_dir / "findings.jsonl").write_text(
                json.dumps(
                    {
                        "task_id": inventory[0]["figure_id"],
                        "status": "PASS",
                        "model": "gpt-5.6-luna",
                        "findings": [],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            self.command("validate", "--run-dir", str(run_dir), expected=2)
            summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual("NEEDS_HUMAN", summary["overall_status"])
            self.assertTrue(summary["coverage"]["requirement_conflicts"])

    def test_discovery_does_not_modify_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "images" / "source.svg"
            write_svg(source, "immutable")
            before = sha256(source)
            run_dir = root / "audit"
            self.command("discover", "--target", str(root / "images"), "--run-dir", str(run_dir))
            self.assertEqual(before, sha256(source))

    def test_concurrency_cap(self) -> None:
        self.assertEqual(30, figure_acceptance.calculate_max_concurrency(None))
        self.assertEqual(8, figure_acceptance.calculate_max_concurrency(8))
        self.assertEqual(30, figure_acceptance.calculate_max_concurrency(100))
        with self.assertRaises(ValueError):
            figure_acceptance.calculate_max_concurrency(0)

    def test_public_fixture_manifest_is_complete(self) -> None:
        manifest = json.loads((FIXTURE_ROOT / "fixture_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual("MIT", manifest["license"])
        for case in manifest["cases"]:
            self.assertTrue((FIXTURE_ROOT / case["input"]).exists(), msg=case["id"])
            if "requirements_file" in case:
                self.assertTrue((FIXTURE_ROOT / case["requirements_file"]).exists(), msg=case["id"])
        for asset_name in (
            "source-decision-tree.svg",
            "correct-chinese-redraw.svg",
            "unrelated-overlap-bar-chart.svg",
            "cropped-left-labels.svg",
            "body-heavy-crop.svg",
        ):
            self.assertTrue((FIXTURE_ROOT / "assets" / asset_name).exists())

    def test_auditor_policy_has_required_constraints(self) -> None:
        policy = POLICY.read_text(encoding="utf-8")
        self.assertIn("gpt-5.6-luna", policy)
        self.assertIn("semantic_mismatch", policy)
        self.assertIn("layout_collision", policy)
        self.assertIn("page_coverage_sentinel", policy)
        self.assertIn("Do not edit", policy)
        self.assertIn("user's explicit visual requirements", policy)

    def test_pdf_keeps_page_sentinel_when_raster_object_exists(self) -> None:
        """A raster object must not hide a vector figure elsewhere on the same page."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "mixed.pdf"
            target.write_bytes(b"%PDF-1.4 public test placeholder")
            run_dir = root / "audit"
            page = run_dir / "evidence" / "page-1.png"
            page.parent.mkdir(parents=True)
            page.write_bytes(b"public test page evidence")
            with (
                mock.patch.object(figure_acceptance, "render_pdf", return_value=([page], None)),
                mock.patch.object(
                    figure_acceptance,
                    "list_pdf_image_objects",
                    return_value=([{"page": 1, "image_index": 0, "raw": "1 0 image"}], None),
                ),
            ):
                placements, warnings = figure_acceptance.discover_pdf(target, root, run_dir)
            self.assertEqual([], warnings)
            self.assertEqual(2, len(placements))
            self.assertEqual(
                ["raster_image_object", "page_coverage_sentinel"],
                [placement["placement_kind"] for placement in placements],
            )
            self.assertEqual([1, 1], [placement["page"] for placement in placements])
            self.assertTrue(all(placement["evidence"]["page_render"] for placement in placements))

    @unittest.skipUnless(all(shutil.which(name) for name in ("xelatex", "pdftoppm", "pdfimages")), "PDF tools unavailable")
    def test_vector_pdf_uses_page_candidate_and_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tex = root / "sample.tex"
            tex.write_text(
                "\\documentclass{article}\n\\begin{document}Vector-only PDF fixture.\\end{document}\n",
                encoding="utf-8",
            )
            compilation = subprocess.run(
                ["xelatex", "-interaction=nonstopmode", "-halt-on-error", "sample.tex"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(0, compilation.returncode, compilation.stdout + compilation.stderr)
            run_dir = root / "audit"
            self.command("discover", "--target", str(root / "sample.pdf"), "--run-dir", str(run_dir))
            inventory = jsonl(run_dir / "figure_inventory.jsonl")
            self.assertTrue(inventory)
            self.assertEqual("pdf_page_candidate", inventory[0]["input_kind"])
            self.assertTrue((run_dir / inventory[0]["evidence"]["page_render"]).exists())


if __name__ == "__main__":
    unittest.main()
