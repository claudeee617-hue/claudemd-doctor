"""Command line interface."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .generator import generate
from .linter import ERROR, INFO, WARN, lint_file
from .scanner import scan

COLORS = {ERROR: "\033[31m", WARN: "\033[33m", INFO: "\033[36m", "dim": "\033[2m",
          "bold": "\033[1m", "ok": "\033[32m", "end": "\033[0m"}


def _c(key: str, text: str, use_color: bool) -> str:
    return f"{COLORS[key]}{text}{COLORS['end']}" if use_color else text


def find_claude_md(root: Path) -> Path | None:
    for candidate in (root / "CLAUDE.md", root / ".claude" / "CLAUDE.md"):
        if candidate.is_file():
            return candidate
    return None


def cmd_generate(args: argparse.Namespace) -> int:
    root = Path(args.path).resolve()
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 2
    text = generate(scan(root))
    if args.stdout:
        sys.stdout.write(text)
        return 0
    target = root / args.output
    if target.exists() and not args.force:
        print(f"error: {target} already exists. Use --force to overwrite or --stdout to preview.",
              file=sys.stderr)
        return 2
    target.write_text(text, encoding="utf-8")
    print(f"Wrote {target} ({len(text.splitlines())} lines)")
    print("Next: add the 2-3 things Claude can't infer from the code, then run "
          "`claudemd-doctor lint`.")
    return 0


def cmd_lint(args: argparse.Namespace) -> int:
    root = Path(args.path).resolve()
    file = Path(args.file).resolve() if args.file else find_claude_md(root)
    if file is None or not file.is_file():
        print(f"error: no CLAUDE.md found in {root}", file=sys.stderr)
        return 2
    report = lint_file(file, root if root.is_dir() else None)
    use_color = sys.stdout.isatty() and not args.no_color

    if args.format == "json":
        print(json.dumps({"file": str(file), "score": report.score, "lines": report.line_count,
                          "issues": [i.as_dict() for i in report.issues]}, indent=2))
    else:
        print(_c("bold", f"{file.name}  ({report.line_count} lines)", use_color))
        order = {ERROR: 0, WARN: 1, INFO: 2}
        for i in sorted(report.issues, key=lambda i: (order[i.severity], i.line or 0)):
            loc = f"L{i.line}" if i.line else "  -"
            tag = _c(i.severity, f"{i.severity:<7}", use_color)
            rule = _c("dim", f"{i.rule:<18}", use_color)
            print(f"  {loc:>5}  {tag}  {rule}  {i.message}")
        if not report.issues:
            print(_c("ok", "  No issues found.", use_color))
        print()
        print(f"Score: {_c('bold', str(report.score), use_color)}/100")

    if report.errors:
        return 1
    if args.fail_under is not None and report.score < args.fail_under:
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="claudemd-doctor",
        description="Generate and lint CLAUDE.md files so Claude actually follows them.")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate", help="scan a repo and write a starter CLAUDE.md")
    g.add_argument("path", nargs="?", default=".", help="repository root (default: .)")
    g.add_argument("-o", "--output", default="CLAUDE.md", help="file name to write")
    g.add_argument("--force", action="store_true", help="overwrite an existing file")
    g.add_argument("--stdout", action="store_true", help="print instead of writing a file")
    g.set_defaults(func=cmd_generate)

    l = sub.add_parser("lint", help="check an existing CLAUDE.md against the repo")
    l.add_argument("path", nargs="?", default=".", help="repository root (default: .)")
    l.add_argument("-f", "--file", help="explicit path to the CLAUDE.md to lint")
    l.add_argument("--format", choices=["text", "json"], default="text")
    l.add_argument("--fail-under", type=int, metavar="N",
                   help="exit 1 if the score is below N (errors always fail)")
    l.add_argument("--no-color", action="store_true")
    l.set_defaults(func=cmd_lint)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
