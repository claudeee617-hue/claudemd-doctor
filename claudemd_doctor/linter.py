"""Lint an existing CLAUDE.md against the repository it describes."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .scanner import RepoInfo, scan

ERROR, WARN, INFO = "error", "warning", "info"
PENALTY = {ERROR: 15, WARN: 7, INFO: 2}

VAGUE_PHRASES = [
    "write clean code", "write good code", "follow best practices", "best practices",
    "be careful", "high quality", "high-quality", "make sure it works", "think carefully",
    "don't make mistakes", "do not make mistakes", "be helpful", "use common sense",
    "follow good practices", "write readable code", "write maintainable code",
]

SECRET_PATTERNS = [
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key"),
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"), "GitHub token"),
    (re.compile(r"sk-[A-Za-z0-9_-]{20,}"), "API secret key"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key"),
    (re.compile(r"(?i)\b(password|passwd|secret|api[_-]?key)\b\s*[:=]\s*['\"]?[^\s'\"<>$]{6,}"),
     "hard-coded credential"),
]

STYLE_WORDS = re.compile(
    r"(?i)\b(indent(ation|ing)?|tabs? vs\.? spaces|\d+[- ]spaces?|semicolons?|"
    r"trailing commas?|single quotes?|double quotes?|line length|max line)\b"
)

SHOUT = re.compile(r"\b(IMPORTANT|CRITICAL|NEVER|ALWAYS|MUST|YOU MUST|DO NOT)\b")
PATH_EXTS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".md", ".toml", ".yml", ".yaml", ".go",
    ".rs", ".java", ".c", ".h", ".cpp", ".html", ".css", ".sh", ".ini", ".cfg", ".txt",
    ".sql", ".env", ".lock",
}
RUN_RE = re.compile(r"(?:(?:npm|pnpm|bun)\s+run\s+([A-Za-z0-9:_-]+)"
                    r"|yarn\s+(?!install\b|add\b|remove\b)([A-Za-z0-9:_-]+))")
MAKE_RE = re.compile(r"make\s+([A-Za-z0-9][A-Za-z0-9_.-]*)")
NPM_BUILTIN = {"install", "test", "start", "init", "ci", "stop", "restart"}
COMMAND_HINT = re.compile(
    r"\b(npm|pnpm|yarn|bun|pytest|make|cargo|go (build|test|run)|pip|poetry|uv|pio|"
    r"python|node|docker|gradle|mvn|dotnet|ruff|mypy|tox)\b"
)


@dataclass
class Issue:
    severity: str
    rule: str
    message: str
    line: int | None = None

    def as_dict(self) -> dict:
        return {"severity": self.severity, "rule": self.rule,
                "message": self.message, "line": self.line}


@dataclass
class Report:
    path: Path
    issues: list[Issue]
    score: int
    line_count: int

    @property
    def errors(self) -> int:
        return sum(1 for i in self.issues if i.severity == ERROR)


def _is_path_like(token: str) -> bool:
    token = token.replace("\\", "/")  # Windows-style separators count as paths too
    if not token or " " in token or len(token) > 120:
        return False
    if token.startswith(("http://", "https://", "-", "/", "~", "$", "@")):
        return False
    if any(ch in token for ch in "*<>{}$|=()[]!?,;:"):
        return False
    if token.endswith("/") and "/" in token.rstrip("/"):
        return True
    suffix = Path(token).suffix.lower()
    if "/" in token:
        return True
    return suffix in PATH_EXTS and token.count(".") == 1 and not token[0].isdigit()


def lint_text(text: str, info: RepoInfo, path: Path | None = None) -> Report:
    lines = text.splitlines()
    issues: list[Issue] = []

    n = len(lines)
    if n > 400:
        issues.append(Issue(ERROR, "too-long", f"{n} lines. Long files get ignored; "
                            "aim for under 200 and move detail into linked docs."))
    elif n > 200:
        issues.append(Issue(WARN, "too-long", f"{n} lines. Aim for under 200 so every rule "
                            "keeps its weight."))

    if not any(l.lstrip().startswith("#") for l in lines):
        issues.append(Issue(WARN, "no-headings", "No headings. Sections make the file "
                            "scannable for both people and Claude."))

    if not COMMAND_HINT.search(text):
        issues.append(Issue(WARN, "no-commands", "No build, test or run commands found. "
                            "Claude can't verify its work without them."))

    in_fence = False
    seen: dict[str, int] = {}
    shout_count = 0

    for idx, raw in enumerate(lines, start=1):
        line = raw.strip()
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        lower = line.lower()

        for phrase in VAGUE_PHRASES:
            if phrase in lower:
                issues.append(Issue(WARN, "vague-rule", f'"{phrase}" says nothing Claude '
                                    "doesn't already do. Replace it with a concrete, "
                                    "checkable rule.", idx))
                break

        for pattern, label in SECRET_PATTERNS:
            if pattern.search(raw):
                issues.append(Issue(ERROR, "secret", f"Possible {label}. Never commit "
                                    "secrets to CLAUDE.md.", idx))
                break

        # Only look at things that are clearly commands: fenced lines and `inline code`.
        candidates = [line.lstrip("$ ")] if in_fence else \
            [c.lstrip("$ ") for c in re.findall(r"`([^`\n]+)`", raw)]
        for cand in candidates:
            m = RUN_RE.match(cand)
            if m and info.npm_scripts:
                script = m.group(1) or m.group(2)
                if script not in info.npm_scripts and script not in NPM_BUILTIN:
                    issues.append(Issue(ERROR, "stale-command", f"`{script}` is not a script "
                                        "in package.json.", idx))
            m = MAKE_RE.match(cand)
            if m and (info.root / "Makefile").exists() and m.group(1) not in info.make_targets:
                issues.append(Issue(ERROR, "stale-command", f"`make {m.group(1)}` is not a "
                                    "target in the Makefile.", idx))

        if not in_fence:
            for tok in re.findall(r"`([^`\n]+)`", raw):
                norm = tok.replace("\\", "/")
                if _is_path_like(tok) and not (info.root / norm.rstrip("/")).exists():
                    issues.append(Issue(WARN, "stale-path", f"`{tok}` does not exist in the "
                                        "repo. Update or remove it.", idx))

            if info.has_formatter_config and STYLE_WORDS.search(line) \
                    and line.startswith(("-", "*", "+")):
                issues.append(Issue(INFO, "style-in-claude-md", "Formatting rules belong in "
                                    "your formatter config, which enforces them. Don't spend "
                                    "CLAUDE.md lines on it.", idx))

            shout_count += len(SHOUT.findall(raw))

            if len(line) > 20 and not line.startswith("#"):
                key = lower
                if key in seen:
                    issues.append(Issue(INFO, "duplicate", f"Same line as line {seen[key]}.", idx))
                else:
                    seen[key] = idx

            if re.search(r"\b(TODO|FIXME|lorem ipsum|TBD)\b", raw, re.I):
                issues.append(Issue(INFO, "placeholder", "Leftover placeholder text.", idx))

    if shout_count > 8:
        issues.append(Issue(WARN, "shouting", f"{shout_count} emphasis words (IMPORTANT, "
                            "NEVER, MUST...). When everything is critical, nothing is."))

    # dedupe identical (rule, line, message)
    uniq: dict[tuple, Issue] = {}
    for i in issues:
        uniq.setdefault((i.rule, i.line, i.message), i)
    issues = list(uniq.values())

    score = max(0, 100 - sum(PENALTY[i.severity] for i in issues))
    return Report(path or Path("CLAUDE.md"), issues, score, n)


def lint_file(file: str | Path, repo_root: str | Path | None = None) -> Report:
    file = Path(file)
    root = Path(repo_root) if repo_root else file.resolve().parent
    if file.parent.name == ".claude":
        root = file.resolve().parent.parent
    info = scan(root)
    text = file.read_text(encoding="utf-8", errors="replace")
    return lint_text(text, info, file)
