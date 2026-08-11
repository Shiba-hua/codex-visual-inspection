#!/usr/bin/env python3
"""Render a portable SVG summary card from a verified Figure Acceptance run."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path


def wrap(text: str, width: int = 70) -> list[str]:
    words = text.split()
    lines: list[str] = []
    line = ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if line and len(candidate) > width:
            lines.append(line)
            line = word
        else:
            line = candidate
    if line:
        lines.append(line)
    return lines or [""]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--lang", choices=("en", "zh"), default="en")
    args = parser.parse_args()
    run_dir = Path(args.run_dir)
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    findings = [json.loads(line) for line in (run_dir / "findings.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    status = summary["overall_status"]
    coverage = summary["coverage"]
    if args.lang == "zh":
        title = "真实 Luna 审计运行结果"
        placements_label = "图位"
        complete_label = "已完成"
        model_label = "模型锁定"
        footer = "源自公开 fixture 的可复现运行；不包含用户私有图片。"
        findings_label = "发现项"
        clean_label = "未发现阻断性问题"
    else:
        title = "Verified Luna audit run"
        placements_label = "Placements"
        complete_label = "Completed"
        model_label = "Model lock"
        footer = "Reproducible run on public fixtures; no user-private images are included."
        findings_label = "Findings"
        clean_label = "No blocking findings"
    colors = {"PASS": ("#117a4f", "#e9f8ef"), "FAIL": ("#c44545", "#fff0f0"), "NEEDS_HUMAN": ("#9a6700", "#fff8df")}
    zh_category = {
        "semantic_mismatch": "语义错配",
        "layout_collision": "版式碰撞",
        "crop_truncation": "裁断",
        "crop_excess": "过度截取",
        "legibility": "可读性",
        "role_confusion": "角色混淆",
        "duplicate_or_misaligned": "重复或错位",
        "missing_context": "上下文缺失",
    }
    zh_repair = {
        "semantic_mismatch": "用保持源决策节点、分支和结果的作者重绘替换候选图。",
        "layout_collision": "重新安排标题和图例，使它们位于彼此独立且不重叠的区域。",
    }
    accent, pale = colors[status]
    finding_items = [
        (record.get("task_id", "unknown"), item)
        for record in findings
        for item in record.get("findings", [])
        if isinstance(item, dict)
    ]
    row_count = max(1, len(finding_items))
    height = 380 + sum(54 + 20 * len(wrap(str(item.get("repair_action", "")), 76)) for _, item in finding_items)
    if not finding_items:
        # Keep the footer below the empty-state card. This guard exists because
        # the product's own documentation must pass the same collision standard.
        height = max(height, 440)
    body: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="{height}" viewBox="0 0 1200 {height}" role="img" aria-labelledby="title desc">',
        f'<title id="title">{html.escape(title)}: {status}</title>',
        f'<desc id="desc">{html.escape(title)} for {coverage["expected"]} figure placements with overall status {status}.</desc>',
        "<style>.h{font:700 31px -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;fill:#162c3b}.k{font:600 16px -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;fill:#527083}.v{font:700 28px -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;fill:#162c3b}.t{font:500 17px -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;fill:#243b4a}.s{font:500 14px -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;fill:#527083}.b{font:700 16px -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;fill:#fff}</style>",
        f'<rect width="1200" height="{height}" rx="24" fill="#ffffff"/>',
        '<rect x="1" y="1" width="1198" height="' + str(height - 2) + '" rx="23" fill="none" stroke="#d8e4ea" stroke-width="2"/>',
        f'<text x="52" y="68" class="h">{html.escape(title)}</text>',
        f'<rect x="934" y="32" width="208" height="52" rx="26" fill="{accent}"/>',
        f'<text x="1038" y="66" class="b" text-anchor="middle">{status}</text>',
        '<rect x="52" y="112" width="324" height="118" rx="16" fill="#f4f9fb"/>',
        '<rect x="408" y="112" width="324" height="118" rx="16" fill="#f4f9fb"/>',
        f'<rect x="764" y="112" width="378" height="118" rx="16" fill="{pale}"/>',
        f'<text x="76" y="150" class="k">{placements_label}</text>',
        f'<text x="76" y="198" class="v">{coverage["expected"]}</text>',
        f'<text x="432" y="150" class="k">{complete_label}</text>',
        f'<text x="432" y="198" class="v">{coverage["completed"]}/{coverage["expected"]}</text>',
        f'<text x="788" y="150" class="k">{model_label}</text>',
        f'<text x="788" y="198" class="v">gpt-5.6-luna</text>',
        f'<text x="52" y="285" class="h" style="font-size:22px">{findings_label}</text>',
    ]
    y = 325
    if not finding_items:
        body.extend(
            [
                f'<rect x="52" y="310" width="1090" height="78" rx="14" fill="#e9f8ef"/>',
                f'<circle cx="88" cy="349" r="15" fill="#117a4f"/>',
                '<path d="M81 349 l5 5 l10 -12" fill="none" stroke="#fff" stroke-width="3"/>',
                f'<text x="120" y="356" class="t">{clean_label}</text>',
            ]
        )
        y = 420
    else:
        for task_id, item in finding_items:
            category = str(item.get("category", "unknown"))
            repair = zh_repair.get(category, str(item.get("repair_action", ""))) if args.lang == "zh" else str(item.get("repair_action", ""))
            repair_lines = wrap(repair)
            box_height = 48 + 20 * len(repair_lines)
            body.append(f'<rect x="52" y="{y - 25}" width="1090" height="{box_height}" rx="14" fill="#fff6f6" stroke="#f2c9c9"/>')
            category_label = zh_category.get(category, category) if args.lang == "zh" else category
            body.append(f'<text x="76" y="{y}" class="t"><tspan font-weight="700">{html.escape(task_id)} · {html.escape(category_label)}</tspan></text>')
            for line_index, line in enumerate(repair_lines, start=1):
                body.append(f'<text x="76" y="{y + 20 * line_index}" class="s">{html.escape(line)}</text>')
            y += box_height + 16
    body.append(f'<text x="52" y="{height - 32}" class="s">{html.escape(footer)}</text>')
    body.append("</svg>")
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(body) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
