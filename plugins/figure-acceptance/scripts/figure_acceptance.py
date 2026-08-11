#!/usr/bin/env python3
"""Deterministic support tooling for the Figure Acceptance Codex skill.

The script discovers logical figure placements, prepares local visual evidence,
and validates structured Luna audit results. It never edits the audited input.
Visual judgement and subagent orchestration intentionally remain in the Skill.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


TOOL_VERSION = "0.1.0"
POLICY_VERSION = "1.0.0"
REQUIRED_MODEL = "gpt-5.6-luna"
ALLOWED_STATUSES = {"PASS", "FAIL", "NEEDS_HUMAN"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif", ".bmp", ".tif", ".tiff"}


def calculate_max_concurrency(system_cap: int | None) -> int:
    """Return the product cap without exceeding Codex's session cap.

    When the platform does not expose a numeric cap, this returns the product
    maximum (30); the native scheduler remains the final enforcement point.
    """
    if system_cap is None:
        return 30
    if system_cap < 1:
        raise ValueError("system concurrency cap must be positive")
    return min(30, system_cap)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.exists():
        return records
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            records.append({"_invalid_json_line": line_no, "_error": str(exc)})
            continue
        if not isinstance(record, dict):
            records.append({"_invalid_json_line": line_no, "_error": "record is not an object"})
            continue
        records.append(record)
    return records


def relative_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.name


def supported_image(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS


def default_requirements() -> list[dict[str, str]]:
    return [
        {
            "id": "default.no-truncation",
            "source": "default",
            "text": "Do not crop away information necessary to read the figure, such as axes, labels, legends, data marks, or explicitly required captions.",
        },
        {
            "id": "default.no-unrelated-content",
            "source": "default",
            "text": "Do not include unrelated body text, page furniture, tables, or neighboring figures when they do not help explain the figure.",
        },
        {
            "id": "default.readability",
            "source": "default",
            "text": "Text, symbols, charts, and graphical marks must remain legible at the intended report scale.",
        },
        {
            "id": "default.semantic-consistency",
            "source": "default",
            "text": "The displayed figure, caption, stated role, and any paired redraw must describe the same task and content.",
        },
    ]


def normalize_requirement_items(value: Any, source: str) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, str]] = []
    for index, item in enumerate(value, start=1):
        if isinstance(item, str):
            text = item.strip()
            item_id = f"{source}-{index:02d}"
        elif isinstance(item, dict):
            text = str(item.get("text", item.get("requirement", ""))).strip()
            item_id = str(item.get("id", f"{source}-{index:02d}"))
        else:
            continue
        if text:
            normalized.append({"id": item_id, "source": source, "text": text})
    return normalized


def load_requirements(path: Path | None) -> dict[str, Any]:
    supplied: dict[str, Any] = {}
    if path:
        supplied = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(supplied, dict):
            raise ValueError("requirements file must contain a JSON object")
    explicit = normalize_requirement_items(supplied.get("explicit", []), "explicit")
    inferred = normalize_requirement_items(supplied.get("inferred", []), "inferred")
    defaults = normalize_requirement_items(supplied.get("defaults", default_requirements()), "default")
    if not defaults:
        defaults = default_requirements()
    conflicts = supplied.get("conflicts", [])
    if not isinstance(conflicts, list):
        raise ValueError("requirements conflicts must be a JSON array")
    return {
        "schema_version": "1.0.0",
        "generated_at": utc_now(),
        "precedence": ["explicit", "inferred", "default"],
        "explicit": explicit,
        "inferred": inferred,
        "defaults": defaults,
        "conflicts": conflicts,
        "effective": explicit + inferred + defaults,
    }


def parse_marker(line: str) -> dict[str, str]:
    """Read a lightweight Markdown marker placed immediately above an image.

    Example: <!-- figure-acceptance: role=source_figure pair_id=tree-01 -->
    """
    match = re.search(r"<!--\s*figure-acceptance:\s*(.*?)\s*-->", line, flags=re.IGNORECASE)
    if not match:
        return {}
    return {key: value for key, value in re.findall(r"([A-Za-z_][\w-]*)=([^\s>]+)", match.group(1))}


def clean_latex(text: str) -> str:
    text = re.sub(r"\\[A-Za-z]+(?:\[[^\]]*\])?", "", text)
    text = text.replace("{", "").replace("}", "")
    return re.sub(r"\s+", " ", text).strip()


def resolve_graphic(raw: str, tex_dir: Path) -> Path | None:
    candidate_text = raw.strip().strip('"').strip("'")
    candidate_text = re.sub(r"^\\detokenize\{(.*)\}$", r"\1", candidate_text)
    candidate = (tex_dir / candidate_text).resolve()
    options = [candidate]
    if not candidate.suffix:
        options.extend(candidate.with_suffix(ext) for ext in (".pdf", ".png", ".jpg", ".jpeg", ".svg"))
    for option in options:
        if option.exists() and option.is_file():
            return option
    return None


def discover_tex(target: Path, root: Path) -> list[dict[str, Any]]:
    text = target.read_text(encoding="utf-8", errors="replace")
    figure_blocks = list(re.finditer(r"\\begin\{(?:figure|figure\*)\}.*?\\end\{(?:figure|figure\*)\}", text, flags=re.DOTALL))
    placements: list[dict[str, Any]] = []
    for block_index, block in enumerate(figure_blocks, start=1):
        block_text = block.group(0)
        caption_match = re.search(r"\\caption(?:\[[^\]]*\])?\s*\{([^}]*)\}", block_text, flags=re.DOTALL)
        caption = clean_latex(caption_match.group(1)) if caption_match else ""
        label_match = re.search(r"\\label\{([^}]*)\}", block_text)
        label = label_match.group(1).strip() if label_match else ""
        start_line = text.count("\n", 0, block.start()) + 1
        graphics = list(re.finditer(r"\\includegraphics(?:\[[^\]]*\])?\s*\{([^}]*)\}", block_text))
        for graphic_index, graphic in enumerate(graphics, start=1):
            asset = resolve_graphic(graphic.group(1), target.parent)
            placements.append(
                {
                    "input_kind": "latex",
                    "source_path": relative_path(target, root),
                    "line_start": start_line,
                    "figure_block": block_index,
                    "graphic_index": graphic_index,
                    "caption": caption,
                    "label": label,
                    "asset_path": relative_path(asset, root) if asset else graphic.group(1).strip(),
                    "asset_exists": bool(asset),
                    "asset_sha256": sha256_file(asset) if asset else None,
                    "asset_role": "unknown",
                    "pair_id": None,
                    "evidence": {},
                }
            )
    return placements


def discover_markdown(target: Path, root: Path) -> list[dict[str, Any]]:
    lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    placements: list[dict[str, Any]] = []
    image_pattern = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+['\"][^)]*['\"])?\)")
    pending_marker: dict[str, str] = {}
    for index, line in enumerate(lines, start=1):
        marker = parse_marker(line)
        if marker:
            pending_marker = marker
            continue
        for match in image_pattern.finditer(line):
            raw_path = match.group(2).strip("<>")
            asset = (target.parent / raw_path).resolve()
            caption = match.group(1).strip()
            if not caption and index < len(lines):
                following = lines[index].strip()
                if re.match(r"^(Figure|Fig\.|图)\s*\d", following, flags=re.IGNORECASE):
                    caption = following
            placements.append(
                {
                    "input_kind": "markdown",
                    "source_path": relative_path(target, root),
                    "line_start": index,
                    "caption": caption,
                    "label": "",
                    "asset_path": relative_path(asset, root) if asset.exists() else raw_path,
                    "asset_exists": asset.exists() and asset.is_file(),
                    "asset_sha256": sha256_file(asset) if asset.exists() and asset.is_file() else None,
                    "asset_role": pending_marker.get("role", "unknown"),
                    "pair_id": pending_marker.get("pair_id"),
                    "evidence": {},
                }
            )
            pending_marker = {}
    return placements


def render_pdf(pdf_path: Path, run_dir: Path) -> tuple[list[Path], str | None]:
    evidence_dir = run_dir / "evidence" / "pages"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    if not shutil.which("pdftoppm"):
        return [], "pdftoppm is unavailable; full-page visual evidence was not rendered"
    prefix = evidence_dir / "page"
    result = subprocess.run(
        ["pdftoppm", "-png", "-r", "144", str(pdf_path), str(prefix)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        return [], f"pdftoppm failed: {result.stderr.strip() or result.returncode}"
    pages = sorted(evidence_dir.glob("page-*.png"))
    return pages, None


def list_pdf_image_objects(pdf_path: Path) -> tuple[list[dict[str, Any]], str | None]:
    if not shutil.which("pdfimages"):
        return [], "pdfimages is unavailable; raster image-object discovery was skipped"
    result = subprocess.run(
        ["pdfimages", "-list", str(pdf_path)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        return [], f"pdfimages -list failed: {result.stderr.strip() or result.returncode}"
    objects: list[dict[str, Any]] = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 3 or not parts[0].isdigit() or not parts[1].isdigit():
            continue
        if parts[2].lower() != "image":
            continue
        objects.append({"page": int(parts[0]), "image_index": int(parts[1]), "raw": line.strip()})
    return objects, None


def discover_pdf(target: Path, root: Path, run_dir: Path) -> tuple[list[dict[str, Any]], list[str]]:
    pages, render_warning = render_pdf(target, run_dir)
    objects, object_warning = list_pdf_image_objects(target)
    warnings = [warning for warning in (render_warning, object_warning) if warning]
    placements: list[dict[str, Any]] = []
    page_rel = {index: relative_path(page, run_dir) for index, page in enumerate(pages, start=1)}
    for obj in objects:
        placements.append(
            {
                "input_kind": "pdf",
                "placement_kind": "raster_image_object",
                "source_path": relative_path(target, root),
                "line_start": None,
                "page": obj["page"],
                "caption": "",
                "label": "",
                "asset_path": relative_path(target, root),
                "asset_exists": True,
                "asset_sha256": sha256_file(target),
                "asset_role": "unknown",
                "pair_id": None,
                "pdf_image_object": obj,
                "evidence": {"page_render": page_rel.get(obj["page"])},
            }
        )
    # Every PDF page also receives a page-coverage sentinel. Raster object lists
    # cannot see vector figures, and a page can contain both. The sentinel is
    # explicit extra coverage, not a replacement for object-level tasks.
    for page_number, page in enumerate(pages, start=1):
        placements.append(
            {
                "input_kind": "pdf_page_candidate",
                "placement_kind": "page_coverage_sentinel",
                "source_path": relative_path(target, root),
                "line_start": None,
                "page": page_number,
                "caption": "",
                "label": "",
                "asset_path": relative_path(target, root),
                "asset_exists": True,
                "asset_sha256": sha256_file(target),
                "asset_role": "unknown",
                "pair_id": None,
                "evidence": {"page_render": relative_path(page, run_dir)},
            }
        )
    return placements, warnings


def discover_image_target(target: Path, root: Path) -> list[dict[str, Any]]:
    assets = [target] if target.is_file() else sorted(path for path in target.rglob("*") if supported_image(path))
    return [
        {
            "input_kind": "image" if target.is_file() else "image_directory",
            "source_path": relative_path(asset, root),
            "line_start": None,
            "caption": "",
            "label": "",
            "asset_path": relative_path(asset, root),
            "asset_exists": True,
            "asset_sha256": sha256_file(asset),
            "asset_role": "unknown",
            "pair_id": None,
            "evidence": {},
        }
        for asset in assets
    ]


def render_tex(target: Path, run_dir: Path) -> tuple[Path | None, str | None]:
    if not shutil.which("xelatex"):
        return None, "xelatex is unavailable; LaTeX page rendering was skipped"
    build_dir = run_dir / "evidence" / "tex-build"
    build_dir.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            "xelatex",
            "-no-shell-escape",
            "-interaction=nonstopmode",
            "-halt-on-error",
            f"-output-directory={build_dir}",
            target.name,
        ],
        cwd=target.parent,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    pdf_path = build_dir / f"{target.stem}.pdf"
    if result.returncode != 0 or not pdf_path.exists():
        return None, f"xelatex failed: {result.stderr.strip() or result.returncode}"
    return pdf_path, None


def determine_root(target: Path) -> Path:
    return target.resolve() if target.is_dir() else target.resolve().parent


def default_run_dir(target: Path) -> Path:
    base = target.resolve() if target.is_dir() else target.resolve().parent
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return base / ".figure-acceptance" / "runs" / stamp


def ensure_safe_run_dir(target: Path, run_dir: Path) -> None:
    if run_dir.resolve() == target.resolve():
        raise ValueError("run directory cannot be the audited target")
    if run_dir.exists() and not run_dir.is_dir():
        raise ValueError("run directory exists but is not a directory")


def make_ids(placements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(
        placements,
        key=lambda item: (
            item.get("source_path", ""),
            item.get("page") or 0,
            item.get("line_start") or 0,
            item.get("asset_path", ""),
            item.get("graphic_index") or 0,
        ),
    )
    for index, placement in enumerate(ordered, start=1):
        placement["figure_id"] = f"figure-{index:04d}"
    return ordered


def relationship_review_mode(asset_role: str | None) -> str:
    """Assign semantic-mismatch ownership when source/redraw roles are explicit."""
    if asset_role in {"author_redraw", "translated_redraw", "redraw", "candidate"}:
        return "compare_candidate_to_source"
    if asset_role in {"source_figure", "original_figure", "source"}:
        return "reference_only"
    return "independent_or_ambiguous"


def build_tasks(placements: list[dict[str, Any]], requirements: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "task_id": placement["figure_id"],
            "figure_id": placement["figure_id"],
            "required_model": REQUIRED_MODEL,
            "reasoning_effort": "medium",
            "auditor_policy_version": POLICY_VERSION,
            "auditor_policy_ref": "plugins/figure-acceptance/assets/auditor-policy.md",
            "retry_policy": {"max_attempts": 2, "same_model_only": True},
            "placement": placement,
            "requirements": requirements["effective"],
            "conflicts": requirements["conflicts"],
            "relationship_review_mode": relationship_review_mode(placement.get("asset_role")),
            "status": "pending",
        }
        for placement in placements
    ]


def discover(args: argparse.Namespace) -> int:
    target = Path(args.target).expanduser().resolve()
    if not target.exists():
        raise ValueError(f"target does not exist: {target}")
    run_dir = Path(args.run_dir).expanduser().resolve() if args.run_dir else default_run_dir(target)
    ensure_safe_run_dir(target, run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    root = determine_root(target)
    requirements = load_requirements(Path(args.requirements_file).expanduser() if args.requirements_file else None)
    warnings: list[str] = []
    blocking_warnings: list[str] = []
    suffix = target.suffix.lower() if target.is_file() else ""
    if suffix == ".tex":
        placements = discover_tex(target, root)
        if args.render_tex:
            rendered_pdf, warning = render_tex(target, run_dir)
            if warning:
                warnings.append(warning)
                blocking_warnings.append(warning)
            elif rendered_pdf:
                pages, render_warning = render_pdf(rendered_pdf, run_dir)
                if render_warning:
                    warnings.append(render_warning)
                    blocking_warnings.append(render_warning)
                page_refs = [relative_path(page, run_dir) for page in pages]
                for placement in placements:
                    placement["evidence"]["rendered_pages"] = page_refs
        else:
            warning = "LaTeX source was not rendered; page-level layout evidence is unavailable"
            warnings.append(warning)
            blocking_warnings.append(warning)
    elif suffix == ".md":
        placements = discover_markdown(target, root)
    elif suffix == ".pdf":
        placements, pdf_warnings = discover_pdf(target, root, run_dir)
        warnings.extend(pdf_warnings)
        if any(warning.startswith("pdftoppm") for warning in pdf_warnings):
            blocking_warnings.extend(warning for warning in pdf_warnings if warning.startswith("pdftoppm"))
    elif supported_image(target) or target.is_dir():
        placements = discover_image_target(target, root)
    else:
        raise ValueError("target must be a .tex, .md, .pdf, supported image file, or directory")

    placements = make_ids(placements)
    tasks = build_tasks(placements, requirements)
    run_manifest = {
        "schema_version": "1.0.0",
        "tool_version": TOOL_VERSION,
        "generated_at": utc_now(),
        "target_name": target.name,
        "target_kind": suffix.lstrip(".") if suffix else "image_directory",
        "target_sha256": sha256_file(target) if target.is_file() else None,
        "warnings": warnings,
        "blocking_warnings": blocking_warnings,
        "required_model": REQUIRED_MODEL,
        "auditor_policy_version": POLICY_VERSION,
    }
    json_dump(run_dir / "run_manifest.json", run_manifest)
    json_dump(run_dir / "resolved_requirements.json", requirements)
    write_jsonl(run_dir / "figure_inventory.jsonl", placements)
    write_jsonl(run_dir / "audit_tasks.jsonl", tasks)
    print(json.dumps({"run_dir": str(run_dir), "figure_count": len(placements), "warnings": warnings}, ensure_ascii=False))
    return 0


def validate_finding(record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if "_invalid_json_line" in record:
        return [f"invalid JSON at line {record['_invalid_json_line']}"]
    task_id = record.get("task_id")
    if not isinstance(task_id, str) or not task_id:
        errors.append("missing task_id")
    if record.get("status") not in ALLOWED_STATUSES:
        errors.append("invalid status")
    if record.get("model") != REQUIRED_MODEL:
        errors.append(f"model must be {REQUIRED_MODEL}")
    findings = record.get("findings")
    if not isinstance(findings, list):
        errors.append("findings must be an array")
        findings = []
    for index, finding in enumerate(findings, start=1):
        if not isinstance(finding, dict):
            errors.append(f"finding {index} is not an object")
            continue
        for field in ("category", "severity", "evidence", "repair_action"):
            if not isinstance(finding.get(field), str) or not finding[field].strip():
                errors.append(f"finding {index} missing {field}")
        if finding.get("severity") not in {"blocking", "advisory"}:
            errors.append(f"finding {index} has invalid severity")
        violated = finding.get("violated_requirements")
        if not isinstance(violated, list) or not violated or not all(isinstance(item, str) and item.strip() for item in violated):
            errors.append(f"finding {index} must list one or more violated_requirements ids")
    if record.get("status") == "FAIL" and not any(
        isinstance(item, dict) and item.get("severity") == "blocking" for item in findings
    ):
        errors.append("FAIL result must include a blocking finding")
    if record.get("status") == "PASS" and any(
        isinstance(item, dict) and item.get("severity") == "blocking" for item in findings
    ):
        errors.append("PASS result cannot include a blocking finding")
    return errors


def write_summary(run_dir: Path, summary: dict[str, Any], findings: list[dict[str, Any]]) -> None:
    json_dump(run_dir / "summary.json", summary)
    coverage = summary["coverage"]
    json_dump(run_dir / "coverage.json", coverage)
    lines = [
        "# Figure Acceptance summary",
        "",
        f"- Overall status: **{summary['overall_status']}**",
        f"- Expected figure placements: {coverage['expected']}",
        f"- Completed audits: {coverage['completed']}",
        f"- Missing audits: {coverage['missing']}",
        f"- Invalid audit results: {coverage['invalid']}",
        f"- Model violations: {coverage['model_violations']}",
        "",
        "## Findings",
        "",
    ]
    for record in findings:
        if "_invalid_json_line" in record:
            continue
        for finding in record.get("findings", []):
            if not isinstance(finding, dict):
                continue
            lines.append(
                f"- `{record.get('task_id', 'unknown')}` · **{finding.get('severity', 'unknown')}** "
                f"`{finding.get('category', 'unknown')}` — {finding.get('repair_action', '')}"
            )
    if len(lines) == 11:
        lines.append("- No findings were supplied.")
    (run_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    handoff_lines = ["# Repair handoff", ""]
    blocking_count = 0
    for record in findings:
        if "_invalid_json_line" in record:
            continue
        for finding in record.get("findings", []):
            if not isinstance(finding, dict) or finding.get("severity") != "blocking":
                continue
            blocking_count += 1
            handoff_lines.extend(
                [
                    f"## {record.get('task_id', 'unknown')} — {finding.get('category', 'unknown')}",
                    "",
                    f"- Evidence: {finding.get('evidence', '')}",
                    f"- Violated requirement: {', '.join(finding.get('violated_requirements', [])) or 'not specified'}",
                    f"- Repair: {finding.get('repair_action', '')}",
                    "",
                ]
            )
    if not blocking_count:
        handoff_lines.append("No blocking repair action is available. Review NEEDS_HUMAN items if present.")
    (run_dir / "repair_handoff.md").write_text("\n".join(handoff_lines) + "\n", encoding="utf-8")


def validate(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).expanduser().resolve()
    inventory = read_jsonl(run_dir / "figure_inventory.jsonl")
    tasks = read_jsonl(run_dir / "audit_tasks.jsonl")
    findings = read_jsonl(run_dir / "findings.jsonl")
    run_manifest_path = run_dir / "run_manifest.json"
    requirements_path = run_dir / "resolved_requirements.json"
    run_manifest = json.loads(run_manifest_path.read_text(encoding="utf-8")) if run_manifest_path.exists() else {}
    resolved_requirements = json.loads(requirements_path.read_text(encoding="utf-8")) if requirements_path.exists() else {}
    expected_ids = {record.get("figure_id") for record in inventory if isinstance(record.get("figure_id"), str)}
    task_ids = {record.get("task_id") for record in tasks if isinstance(record.get("task_id"), str)}
    tasks_by_id = {record["task_id"]: record for record in tasks if isinstance(record.get("task_id"), str)}
    task_model_violations = [record.get("task_id", "unknown") for record in tasks if record.get("required_model") != REQUIRED_MODEL]
    finding_errors: dict[str, list[str]] = {}
    by_task: dict[str, dict[str, Any]] = {}
    duplicate_ids: set[str] = set()
    for record in findings:
        record_errors = validate_finding(record)
        task_id = record.get("task_id") if isinstance(record, dict) else None
        if isinstance(task_id, str):
            if task_id in by_task:
                duplicate_ids.add(task_id)
            by_task[task_id] = record
            if record_errors:
                finding_errors[task_id] = record_errors
        else:
            finding_errors[f"line-{record.get('_invalid_json_line', 'unknown')}"] = record_errors
    missing = sorted(task_ids - set(by_task))
    unexpected = sorted(set(by_task) - task_ids)
    result_model_violations: list[str] = []
    for task_id, record in by_task.items():
        if record.get("model") != REQUIRED_MODEL:
            result_model_violations.append(task_id)
        task = tasks_by_id.get(task_id)
        if not task:
            continue
        allowed_requirement_ids = {
            requirement.get("id")
            for requirement in task.get("requirements", [])
            if isinstance(requirement, dict) and isinstance(requirement.get("id"), str)
        }
        for index, finding in enumerate(record.get("findings", []), start=1):
            if not isinstance(finding, dict):
                continue
            violated = finding.get("violated_requirements", [])
            if isinstance(violated, list):
                unknown = sorted(item for item in violated if item not in allowed_requirement_ids)
                if unknown:
                    finding_errors.setdefault(task_id, []).append(
                        f"finding {index} references unknown requirement ids: {', '.join(unknown)}"
                    )
    invalid = sorted(set(finding_errors) | duplicate_ids | set(unexpected))
    statuses = [record.get("status") for record in by_task.values()]
    has_blocking = any(
        isinstance(finding, dict) and finding.get("severity") == "blocking"
        for record in by_task.values()
        for finding in record.get("findings", [])
        if isinstance(record.get("findings"), list)
    )
    blocking_warnings = run_manifest.get("blocking_warnings", [])
    requirement_conflicts = resolved_requirements.get("conflicts", [])
    if (
        missing
        or invalid
        or task_model_violations
        or result_model_violations
        or expected_ids != task_ids
        or "NEEDS_HUMAN" in statuses
        or blocking_warnings
        or requirement_conflicts
    ):
        overall = "NEEDS_HUMAN"
    elif "FAIL" in statuses or has_blocking:
        overall = "FAIL"
    elif expected_ids and set(statuses) == {"PASS"}:
        overall = "PASS"
    else:
        overall = "NEEDS_HUMAN"
    coverage = {
        "expected": len(expected_ids),
        "tasks": len(task_ids),
        "completed": len(by_task),
        "missing": missing,
        "unexpected": unexpected,
        "invalid": invalid,
        "model_violations": sorted(task_model_violations + result_model_violations),
        "inventory_task_mismatch": sorted((expected_ids ^ task_ids)),
        "blocking_warnings": blocking_warnings,
        "requirement_conflicts": requirement_conflicts,
    }
    summary = {
        "schema_version": "1.0.0",
        "generated_at": utc_now(),
        "overall_status": overall,
        "coverage": coverage,
        "finding_errors": finding_errors,
        "required_model": REQUIRED_MODEL,
    }
    write_summary(run_dir, summary, findings)
    print(json.dumps({"run_dir": str(run_dir), "overall_status": overall, "coverage": coverage}, ensure_ascii=False))
    return 0 if overall in {"PASS", "FAIL"} else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    discover_parser = subparsers.add_parser("discover", help="discover figure placements and create an audit run")
    discover_parser.add_argument("--target", required=True, help="LaTeX, Markdown, PDF, image file, or image directory")
    discover_parser.add_argument("--run-dir", help="separate directory for generated audit artifacts")
    discover_parser.add_argument("--requirements-file", help="JSON file containing explicit/inferred/default requirements")
    discover_parser.add_argument("--render-tex", action="store_true", help="render a LaTeX source in an isolated, no-shell-escape directory")
    discover_parser.set_defaults(func=discover)
    validate_parser = subparsers.add_parser("validate", help="validate Luna audit results and write final run artifacts")
    validate_parser.add_argument("--run-dir", required=True, help="existing audit run directory")
    validate_parser.set_defaults(func=validate)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"figure-acceptance: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
