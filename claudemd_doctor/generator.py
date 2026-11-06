"""Turn scan results into a concise CLAUDE.md."""

from __future__ import annotations

from .scanner import FORMATTER_CONFIGS, RepoInfo


def generate(info: RepoInfo) -> str:
    out: list[str] = [f"# {info.name}", ""]

    if info.description:
        out += [info.description, ""]

    stack = info.main_languages() + info.package_managers
    if stack:
        out += [f"**Stack:** {', '.join(stack)}", ""]

    if info.commands:
        out += ["## Commands", ""]
        out += [f"- {c.label}: `{c.cmd}`" for c in info.commands]
        out.append("")

    if info.top_dirs:
        out += ["## Project structure", ""]
        for name, hint in info.top_dirs:
            out.append(f"- `{name}/`" + (f" - {hint}" if hint else ""))
        out.append("")

    rules: list[str] = []
    configs = [c for c in info.config_files if c in FORMATTER_CONFIGS]
    if configs:
        listed = ", ".join(f"`{c}`" for c in configs)
        rules.append(f"Style rules live in {listed}. Run the formatter instead of "
                     "hand-formatting.")
    elif info.has_formatter_config:
        rules.append("Style rules live in `pyproject.toml`. Run the formatter instead of "
                     "hand-formatting.")
    if info.ci_files:
        listed = ", ".join(f"`.github/workflows/{f}`" for f in info.ci_files)
        rules.append(f"CI is defined in {listed}. Keep it green.")
    if any("test" in c.cmd.lower() for c in info.commands):
        rules.append("Run the tests after every change and fix failures before moving on.")
    if rules:
        out += ["## Working agreements", ""]
        out += [f"- {r}" for r in rules]
        out.append("")

    return "\n".join(out).rstrip() + "\n"
