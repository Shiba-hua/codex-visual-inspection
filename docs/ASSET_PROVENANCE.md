# Fixture asset provenance

Public fixtures are source-first. An image must be copied from a LaTeX/source project
or generated from repository-owned LaTeX; it must never be cropped from an error report,
PDF compendium, user attachment, or Codex clipboard image. `fixtures/public/asset_provenance.json`
is the machine-readable ledger and records source location, page/crop, SHA-256, expected
finding, disposition, and release status.

The four source-derived fixtures in this release come from the local LaTeX project
`research/figure-error-exemptions-2026`. The two AI Scientist fixtures deliberately keep
the graph and caption/body evidence together so a model can explain the contradiction;
the Terminal-Bench fixture is a precise issue-region crop; the template fixture is the
negative/exempt example. The validator rejects forbidden compendium and attachment paths.
