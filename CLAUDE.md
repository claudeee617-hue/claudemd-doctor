# claudemd-doctor

Generate and lint CLAUDE.md files so Claude Code actually follows them. Zero dependencies, Python 3.9+.

## Commands

- Install (editable): `pip install -e .`
- Run tests: `python -m unittest discover -s tests`
- Lint our own CLAUDE.md: `claudemd-doctor lint . --fail-under 90`
- Try the generator without writing: `claudemd-doctor generate . --stdout`

## Project structure

- `claudemd_doctor/scanner.py` - reads a repo and collects facts (commands, dirs, configs)
- `claudemd_doctor/generator.py` - turns scan results into a CLAUDE.md
- `claudemd_doctor/linter.py` - all lint rules, one block per rule inside `lint_text`
- `claudemd_doctor/cli.py` - argparse entry point
- `tests/` - unittest suite, builds throwaway repos in temp dirs
- `action.yml` - reusable GitHub Action wrapping `lint`

## Working agreements

- Never add runtime dependencies. The tool must install with bare `pip`.
- Every new lint rule needs a test in `tests/test_claudemd_doctor.py` and a row in the README rule table.
- Linter output must stay deterministic: sort issues, no timestamps.
- CI is defined in `.github/workflows/ci.yml`. Keep it green.
