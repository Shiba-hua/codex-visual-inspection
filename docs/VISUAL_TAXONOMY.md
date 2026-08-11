# Visual Inspection taxonomy

Version 2.0 keeps the original visual categories and adds evidence-aware categories.

| Category | Typical source in automated papers/research reports | Default disposition |
|---|---|---|
| `crop_truncation` | axes, model names, legends, footnotes, or required caption cut off | defect |
| `crop_excess` | a Figure crop includes unrelated body prose or neighboring material | defect |
| `layout_collision` | title, labels, annotations, legend, or Chinese redraw text collide | defect |
| `legibility` | low resolution, tiny text, missing glyphs, or low contrast | defect |
| `semantic_mismatch` | an unrelated redraw or stale asset is paired with a figure | defect |
| `figure_text_metric_mismatch` | loss is plotted but the caption/body says accuracy | defect |
| `figure_text_trend_mismatch` | bars/curves move in the opposite direction from the prose claim | defect |
| `figure_caption_body_mismatch` | caption, body, and plot make different conclusions | defect |
| `source_residue` | LaTeX commands, source markup, or malformed glyphs remain visible | defect unless explicit template context |
| `evidence_low_resolution` | evidence cannot support a reliable visual decision | human review |
| `precise_region_evidence` | user-specified red-box/problem region must be isolated and recorded | evidence requirement |

The only approved exemption in the current public regression set is a visibly marked
template placeholder in its template context. It is represented as finding-level
`disposition: exempt`, not as a global `EXEMPT` status.
