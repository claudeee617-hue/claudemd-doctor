# Contributing

Thanks for helping make `CLAUDE.md` files better.

## Setup

```bash
git clone https://github.com/claudeee617-hue/claudemd-doctor
cd claudemd-doctor
pip install -e .
python -m unittest discover -s tests
```

## Adding a lint rule

1. Add the check inside `lint_text` in `claudemd_doctor/linter.py`.
2. Add a test in `tests/test_claudemd_doctor.py` (one that fires, one that stays quiet).
3. Add a row to the rule table in `README.md` and an entry in `CHANGELOG.md`.

## Ground rules

- No runtime dependencies. The tool must install with bare `pip`.
- Output must be deterministic (sorted, no timestamps).
- Prefer few, high-signal rules over many noisy ones. A rule that cries wolf gets the tool uninstalled.
- Run `claudemd-doctor lint . --fail-under 90` before opening a PR.
