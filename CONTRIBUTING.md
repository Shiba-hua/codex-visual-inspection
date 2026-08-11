# Contributing

Thank you for helping make visual acceptance more dependable.

## Development checks

```sh
python3 scripts/validate_package.py
python3 -m unittest discover -s tests -v
python3 /path/to/plugin-creator/scripts/validate_plugin.py plugins/figure-acceptance
```

Keep source changes, tests, and documentation in the same pull request. Do not change a generated audit run or a rendered README image without updating the source that generated it.

## Adding a public fixture

1. Use only hand-drawn, self-owned, or clearly redistributable material.
2. Add its origin and license to `fixtures/public/fixture_manifest.json`.
3. State the intended error category and whether it is blocking.
4. Add a deterministic regression test where possible.
5. Render and visually inspect the fixture before opening a pull request.

Never submit a private report page, a user attachment, or a copyrighted paper figure without explicit redistributable permission.

## Audit-policy changes

Changes to `auditor-policy.md` must update its policy version, relevant tests, and both product READMEs. Preserve the precedence rule: explicit user requirements override predefined visual defaults unless platform safety prohibits them.
