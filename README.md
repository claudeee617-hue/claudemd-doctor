# claudemd-doctor

**Your `CLAUDE.md` is probably hurting Claude Code more than helping it. This finds out why.**

A zero-dependency CLI that **generates** a lean `CLAUDE.md` from your repo and **lints** an existing one for the mistakes that make Claude ignore it: stale paths, dead commands, vague rules, bloat and leaked secrets.

![CI](https://github.com/claudeee617-hue/my-project/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Dependencies](https://img.shields.io/badge/dependencies-0-brightgreen)

## The problem

`CLAUDE.md` is the one file Claude reads at the start of every session. But most of them:

- grow to 500 lines until nothing in them has weight,
- say things like *"write clean code"* (Claude already does),
- point at files and scripts that were renamed months ago,
- repeat what the formatter already enforces,
- sometimes even contain an API key.

Nobody notices, because nothing checks the file. Until now.

## See it work

```console
$ claudemd-doctor lint

CLAUDE.md  (12 lines)
     L8  error    stale-command       `deploy-everything` is not a script in package.json.
    L12  error    secret              Possible hard-coded credential. Never commit secrets to CLAUDE.md.
     L3  warning  vague-rule          "write clean code" says nothing Claude doesn't already do. Replace it with a concrete, checkable rule.
     L4  warning  vague-rule          "be careful" says nothing Claude doesn't already do. Replace it with a concrete, checkable rule.
     L7  warning  stale-path          `src/utils/helpers.ts` does not exist in the repo. Update or remove it.
    L10  info     duplicate           Same line as line 9.

Score: 47/100
```

It checks your `CLAUDE.md` against the **actual repo**, so a rule that points at something that no longer exists gets caught.

## Install

```bash
pip install git+https://github.com/claudeee617-hue/my-project
```

## Usage

```bash
# Starting from scratch? Scan the repo and write a starter CLAUDE.md
claudemd-doctor generate

# Preview without writing
claudemd-doctor generate --stdout

# Lint the CLAUDE.md in the current repo (also finds .claude/CLAUDE.md)
claudemd-doctor lint

# CI-friendly: fail below a score, machine-readable output
claudemd-doctor lint --fail-under 80 --format json
```

Exit code is `1` when there are errors or the score is under `--fail-under`, so it drops straight into CI.

### What `generate` detects

| Ecosystem | What it picks up |
|---|---|
| Node | `package.json` scripts, npm / pnpm / yarn / bun (from the lockfile) |
| Python | pip / poetry / uv, pytest vs unittest, ruff, mypy, black |
| Make | real targets from your `Makefile` |
| Rust / Go | cargo and go toolchain commands |
| Embedded | PlatformIO build and upload |

It also lists your top-level directories, formatter configs and CI workflows. The result is short on purpose: you add the 2-3 things only you know.

## Lint rules

| Rule | Severity | What it catches |
|---|---|---|
| `secret` | error | API keys, tokens, private keys, hard-coded passwords |
| `stale-command` | error | `npm run x` / `make x` where `x` doesn't exist |
| `too-long` | warning / error | Over 200 / 400 lines |
| `stale-path` | warning | Backticked file paths that no longer exist |
| `vague-rule` | warning | "Write clean code", "follow best practices"... |
| `no-commands` | warning | No build/test commands, so Claude can't verify its work |
| `no-headings` | warning | A wall of text with no structure |
| `shouting` | warning | Overuse of IMPORTANT / NEVER / MUST |
| `style-in-claude-md` | info | Indent/quote rules a formatter config already enforces |
| `duplicate` | info | The same line repeated |
| `placeholder` | info | Leftover TODO / TBD text |

Score starts at 100: each error costs 15, warning 7, info 2.

## Use it in CI (GitHub Action)

```yaml
- uses: actions/checkout@v4
- uses: claudeee617-hue/my-project@main
  with:
    fail-under: 80
```

## Development

```bash
pip install -e .
python -m unittest discover -s tests
```

Add a rule: write the check in `claudemd_doctor/linter.py`, add a test, add a row to the table above. PRs welcome.

## License

MIT
