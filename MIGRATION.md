# Migration to Visual Inspection 0.2.0

This is a breaking pre-1.0 package rename. The old `figure-acceptance` marketplace
entry and `$figure-acceptance` command are intentionally not retained.

1. Remove the old local installation if present.
2. Install `visual-inspection` from the updated marketplace/repository.
3. Replace invocations with `$visual-inspection` and paths with `plugins/visual-inspection`.
4. Existing audit JSON remains valid for legacy categories. New figure-text findings
   must include figure evidence, text evidence, and a contradiction object.

The top-level statuses remain `PASS`, `FAIL`, and `NEEDS_HUMAN`; exemptions are local to
a finding through `disposition: exempt`.
