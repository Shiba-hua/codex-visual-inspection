---
name: figure-acceptance
description: Audit every logical figure placement in a LaTeX report, Markdown document, PDF, or image directory before publication. Use when the user asks to check figures, screenshots, diagrams, charts, captions, crops, readability, image mismatch, redraws, or visual acceptance.
---

# Figure Acceptance

Use this skill to perform a **read-only visual acceptance audit**. It discovers every logical figure placement, sends exactly one narrowly scoped `gpt-5.6-luna` subagent to inspect each placement, then produces a traceable audit ledger and repair handoff.

Do not edit the audited document, image, caption, or source asset. If the user also asks for a repair, first finish and report the audit; hand the repair instructions to the appropriate upstream writing or drawing workflow, then rerun this skill after repair.

## Mandatory workflow

### 1. Establish the audit contract

Before discovery, state the target and extract the user's requirements into these groups:

1. **Explicit:** requirements the user directly gave in this request or earlier active context.
2. **Inferred:** requirements supported by the current task context; record the basis.
3. **Defaults:** the general policy only.

Use this order when requirements conflict: platform safety constraints, explicit user requirements, inferred requirements, task-mode requirements, defaults. Do not silently discard an explicit user requirement because it differs from a default.

Examples of **conditional**, not universal, requirements:

- include the full figure caption in a crop;
- use only a genuine paper Figure rather than a screenshot of surrounding prose;
- provide a separate Chinese redraw in addition to an original figure;
- allow only a self-drawn figure and never an original screenshot.

If requirements conflict or cannot be established, record the conflict and make the affected figure `NEEDS_HUMAN`.

Write a JSON requirements file with `explicit`, `inferred`, `defaults`, and `conflicts`, then pass it to the deterministic discovery command.

### 2. Discover every logical figure placement

Run:

```sh
python3 <plugin-root>/scripts/figure_acceptance.py discover \
  --target <latex|markdown|pdf|image-directory> \
  --requirements-file <requirements.json> \
  --run-dir <target-parent>/.figure-acceptance/runs/<run-id>
```

For a LaTeX source, add `--render-tex` when a safe, local XeLaTeX build is appropriate. The helper uses a separate build directory and disables shell escape. If rendering is unavailable or fails, preserve the warning and do not claim complete page-layout coverage.

Read `figure_inventory.jsonl`, `audit_tasks.jsonl`, `resolved_requirements.json`, and `run_manifest.json`. Confirm that every discovered figure placement will receive one task. The same source image can legitimately produce multiple tasks if it appears in multiple document locations or crops.

For PDFs, also retain one explicit page-coverage sentinel per rendered page. It catches vector figures that `pdfimages` cannot enumerate; its job is page-level coverage, not duplicate reporting of a clean raster-object task.

### 3. Prepare full visual context

For each task, provide the Luna worker with as much of the following as exists:

- the full rendered page, not merely a tight crop;
- the candidate figure asset;
- the source figure and claimed redraw/translation when there is a pair;
- the caption, label, source path, page/line location, asset role, and pair identifier;
- the task's `relationship_review_mode`: `reference_only`, `compare_candidate_to_source`, or `independent_or_ambiguous`;
- the complete effective requirements and any conflicts.

The worker must see both full context and the candidate. Never ask it to approve a crop while hiding the cropped-off edge or the linked original/redraw asset.

### 4. Dispatch exactly one Luna worker per figure placement

Spawn one independent native Codex subagent for every task in `audit_tasks.jsonl`:

- set `model` to exactly `gpt-5.6-luna`;
- use `medium` reasoning effort unless the user explicitly requests another Luna effort;
- cap active workers at `min(30, agents.max_concurrent_threads_per_session)`;
- never fall back to Terra, Sol, or another model;
- if Luna is unavailable, do not substitute another worker—write `NEEDS_HUMAN`.

Include the entire contents of `<plugin-root>/assets/auditor-policy.md` verbatim in every worker task, followed by the individual task payload and user requirements. This is the versioned auditor instruction bundle. It does **not** replace the platform system prompt; do not claim that it does.

Each worker must inspect exactly one figure placement, make no edits, and return the JSON response contract from the policy. If the worker response is invalid, retry once with the same Luna model. If it remains invalid, record a valid `NEEDS_HUMAN` result explaining the failure.

Require every finding's `violated_requirements` field to contain the **exact ID** from the supplied requirements list, never ordinal shorthand such as `1` or `2`. The Main agent must reject unknown IDs and use the single same-model retry to correct them.

### 5. Validate and merge the audit

Write one valid JSON object per worker into `findings.jsonl` in the run directory. Preserve each worker's model record. Then run:

```sh
python3 <plugin-root>/scripts/figure_acceptance.py validate \
  --run-dir <target-parent>/.figure-acceptance/runs/<run-id>
```

The validator writes:

- `summary.md` and `summary.json`;
- `coverage.json`;
- `repair_handoff.md`.

Only report `PASS` when every discovered placement has a valid Luna result, the task/inventory IDs match, there are no model violations, no blocking findings, and no unresolved requirement conflict. A confirmed defect is `FAIL`; missing evidence, invalid results, unavailable Luna, rendering failure, or unresolved conflict is `NEEDS_HUMAN`.

### 6. Report the result and hand off repair

Lead with the overall status, number of audited figure placements, and blocking findings. Link the user to `summary.md` and `repair_handoff.md`. Do not modify the audited inputs yourself. If the user asks to repair, use the repair handoff as the specification for a separate edit workflow and rerun the audit afterward.

## Required visual checks

The auditor policy is authoritative, but ensure the task covers at least these failure types when applicable:

- a crop cuts off axes, labels, model names, title, legend, source note, or a user-required caption;
- a crop includes irrelevant English body prose, page furniture, tables, or adjacent figures;
- title, chart, legend, labels, annotations, or Chinese text collide, overflow, overlap, or become occluded;
- text is blurry, too small, missing glyphs, low-contrast, or otherwise unreadable;
- a figure, caption, source, original screenshot, or claimed redraw refers to different content;
- an original Figure is confused with a custom redraw, or a translated redraw does not correspond to the original;
- duplicate, stale, or misaligned assets are placed in the report.

The “image fight” case is always blocking: if the source is a decision tree and the claimed redraw is an unrelated bar chart, report `semantic_mismatch`; report `layout_collision` separately if that wrong chart also has overlapping text.

When roles are explicit, attribute this mismatch to the redraw task (`compare_candidate_to_source`), not to an otherwise intact source-figure task (`reference_only`).

## Privacy and contribution boundaries

- Never put the user's images, report pages, absolute user paths, or subagent payloads into the public repository.
- Public fixtures must be hand-drawn, self-owned, or clearly redistributable.
- Public documentation may show only generated assets from public fixtures and self-drawn diagrams.
