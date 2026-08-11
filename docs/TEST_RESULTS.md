# Test and QA record

**Date:** 2026-08-11  
**Product version:** `0.1.0`  
**Scope:** public fixtures and product assets only; no user-private report images were used.

## Deterministic validation

| Check | Result |
| --- | --- |
| `python3 -m unittest discover -s tests -v` | 17/17 passed |
| `python3 scripts/validate_package.py` | passed |
| Plugin Creator `validate_plugin.py` | passed |
| Local Marketplace add, plugin install/list, then remove | passed; local Codex configuration restored |
| LaTeX, Markdown, image directory, vector-PDF and mixed raster/vector-PDF page coverage | passed |
| Requirements conflict / missing result / non-Luna result fail-closed paths | passed |
| Input immutability | passed |

## Real Luna smoke tests

All workers used `gpt-5.6-luna` with `medium` reasoning effort and were given the versioned auditor policy, complete task requirements, and both paired public images.

| Run | Logical placements | Result | Verified behavior |
| --- | ---: | --- | --- |
| `luna-smoke-mismatch-retry` | 2 | `FAIL` | Source decision tree passed; wrong bar-chart redraw failed for `semantic_mismatch` and `layout_collision`; all task IDs, requirement IDs, coverage, and model records validated. |
| `luna-smoke-correct-pair` | 2 | `PASS` | Source figure and independent corresponding Chinese redraw both passed; coverage 2/2 with no model violation. |

The first mismatch smoke run revealed two product defects: paired-redraw failure was incorrectly attributable to the source task, and workers could return ordinal requirement references. The Main agent corrected the policy, task contract, validator, and regression tests before the documented retry runs.

## Visual acceptance of public graphics

The following assets were rendered with `rsvg-convert` and visually reviewed:

- all five public fixture SVGs;
- English and Chinese architecture diagrams;
- English and Chinese requirement-precedence diagrams;
- English and Chinese `FAIL`/`PASS` audit-result cards.

The first `PASS` result card had a footer collision with its empty-state panel. The renderer was corrected, all cards were regenerated, and the final images were rechecked. No remaining crop loss, unrelated content, text collision, or image mismatch was accepted in the public product assets.
