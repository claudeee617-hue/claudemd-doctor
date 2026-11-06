"""Scan a repository and collect the facts a CLAUDE.md should contain."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

IGNORE_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env", "dist",
    "build", "target", ".next", ".idea", ".vscode", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", "vendor", ".tox", ".gradle", "coverage",
}

MAX_FILES = 20000

LANG_BY_EXT = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".go": "Go", ".rs": "Rust",
    ".java": "Java", ".kt": "Kotlin", ".rb": "Ruby", ".php": "PHP", ".c": "C",
    ".h": "C", ".cpp": "C++", ".cc": "C++", ".hpp": "C++", ".cs": "C#",
    ".swift": "Swift", ".ino": "Arduino", ".sh": "Shell", ".html": "HTML",
    ".css": "CSS", ".vue": "Vue", ".svelte": "Svelte",
}

DIR_HINTS = {
    "src": "Main source code",
    "lib": "Library code",
    "app": "Application code",
    "tests": "Tests",
    "test": "Tests",
    "__tests__": "Tests",
    "docs": "Documentation",
    "doc": "Documentation",
    "scripts": "Helper scripts",
    "examples": "Usage examples",
    "bin": "Executables / entry points",
    "cmd": "Go entry points",
    "pkg": "Go packages",
    "internal": "Private application code",
    "public": "Static assets served as-is",
    "assets": "Static assets",
    "config": "Configuration",
    "migrations": "Database migrations",
    "firmware": "Embedded firmware",
    "hardware": "Schematics / PCB files",
    ".github": "CI workflows and GitHub config",
}

CONFIG_FILES = [
    ".editorconfig", ".prettierrc", ".prettierrc.json", ".eslintrc", ".eslintrc.json",
    ".eslintrc.js", "eslint.config.js", "eslint.config.mjs", "biome.json",
    "ruff.toml", ".ruff.toml", "tsconfig.json", "Dockerfile", "docker-compose.yml",
    "tox.ini", "setup.cfg", ".pre-commit-config.yaml", "rustfmt.toml", ".golangci.yml",
    "platformio.ini",
]

FORMATTER_CONFIGS = {
    ".editorconfig", ".prettierrc", ".prettierrc.json", "biome.json", "ruff.toml",
    ".ruff.toml", "rustfmt.toml", ".eslintrc", ".eslintrc.json", ".eslintrc.js",
    "eslint.config.js", "eslint.config.mjs",
}


@dataclass
class Command:
    label: str
    cmd: str
    source: str


@dataclass
class RepoInfo:
    root: Path
    name: str
    description: str = ""
    languages: dict[str, int] = field(default_factory=dict)
    package_managers: list[str] = field(default_factory=list)
    commands: list[Command] = field(default_factory=list)
    top_dirs: list[tuple[str, str]] = field(default_factory=list)
    config_files: list[str] = field(default_factory=list)
    ci_files: list[str] = field(default_factory=list)
    npm_scripts: set[str] = field(default_factory=set)
    make_targets: set[str] = field(default_factory=set)
    has_formatter_config: bool = False

    def main_languages(self, limit: int = 3) -> list[str]:
        ranked = sorted(self.languages.items(), key=lambda kv: -kv[1])
        return [name for name, _ in ranked[:limit]]


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _walk(root: Path):
    count = 0
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = sorted(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_dir():
                if entry.name in IGNORE_DIRS or entry.is_symlink():
                    continue
                stack.append(entry)
            else:
                count += 1
                if count > MAX_FILES:
                    return
                yield entry


def readme_summary(root: Path) -> str:
    """First real paragraph of the README, skipping headings and badges."""
    for name in ("README.md", "readme.md", "README.rst", "README"):
        text = _read(root / name)
        if not text:
            continue
        para: list[str] = []
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                if para:
                    break
                continue
            if line.startswith(("#", "![", "[![", "<", "=", "-", ">", "|", "```")):
                if para:
                    break
                continue
            para.append(line)
        summary = " ".join(para)
        summary = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", summary)
        if len(summary) > 280:
            summary = summary[:277].rstrip() + "..."
        return summary
    return ""


def _node_commands(root: Path, info: RepoInfo) -> None:
    pkg_path = root / "package.json"
    if not pkg_path.exists():
        return
    try:
        pkg = json.loads(_read(pkg_path))
    except json.JSONDecodeError:
        return
    if not isinstance(pkg, dict):
        return

    manager = "npm"
    for lock, mgr in (("pnpm-lock.yaml", "pnpm"), ("yarn.lock", "yarn"),
                      ("bun.lockb", "bun"), ("bun.lock", "bun")):
        if (root / lock).exists():
            manager = mgr
            break
    info.package_managers.append(manager)
    if not info.description:
        info.description = str(pkg.get("description", ""))[:280]

    scripts = pkg.get("scripts") or {}
    if not isinstance(scripts, dict):
        return
    info.npm_scripts = set(scripts)
    install = {"npm": "npm install", "pnpm": "pnpm install", "yarn": "yarn",
               "bun": "bun install"}[manager]
    info.commands.append(Command("Install dependencies", install, "package.json"))

    priority = ["dev", "start", "build", "test", "lint", "format", "typecheck"]
    ordered = [s for s in priority if s in scripts] + [s for s in scripts if s not in priority]
    for name in ordered[:10]:
        if manager == "npm":
            cmd = "npm test" if name == "test" else f"npm run {name}"
        elif manager == "yarn":
            cmd = f"yarn {name}"
        else:
            cmd = f"{manager} run {name}"
        info.commands.append(Command(f"`{name}` script", cmd, "package.json"))


def _python_commands(root: Path, info: RepoInfo) -> None:
    files = {n: _read(root / n) for n in
             ("pyproject.toml", "requirements.txt", "setup.py", "setup.cfg", "tox.ini",
              "requirements-dev.txt")}
    if not any(files.values()):
        return
    blob = "\n".join(files.values()).lower()
    if files["pyproject.toml"]:
        manager = "poetry" if "[tool.poetry" in blob else "uv" if (root / "uv.lock").exists() else "pip"
    else:
        manager = "pip"
    info.package_managers.append(manager)

    if manager == "poetry":
        info.commands.append(Command("Install dependencies", "poetry install", "pyproject.toml"))
    elif manager == "uv":
        info.commands.append(Command("Install dependencies", "uv sync", "uv.lock"))
    elif files["requirements.txt"]:
        info.commands.append(Command("Install dependencies", "pip install -r requirements.txt",
                                     "requirements.txt"))
    else:
        info.commands.append(Command("Install (editable)", "pip install -e .", "pyproject.toml"))

    tests_dir = root / "tests"
    test_src = ""
    if tests_dir.is_dir():
        for tf in list(tests_dir.rglob("*.py"))[:50]:
            test_src += _read(tf)[:5000]
    uses_pytest = "pytest" in blob or "import pytest" in test_src
    uses_unittest = "import unittest" in test_src or "from unittest" in test_src
    if uses_pytest:
        info.commands.append(Command("Run tests", "pytest", "pytest detected"))
    elif uses_unittest:
        info.commands.append(Command("Run tests", "python -m unittest discover -s tests",
                                     "unittest detected"))
    elif tests_dir.is_dir():
        info.commands.append(Command("Run tests", "pytest", "tests/ directory"))
    if "ruff" in blob or (root / "ruff.toml").exists():
        info.commands.append(Command("Lint", "ruff check .", "ruff detected"))
    if "mypy" in blob:
        info.commands.append(Command("Type check", "mypy .", "mypy detected"))
    if "black" in blob:
        info.commands.append(Command("Format", "black .", "black detected"))

    m = re.search(r'^description\s*=\s*"([^"]+)"', files["pyproject.toml"], re.M)
    if m and not info.description:
        info.description = m.group(1)


def _make_commands(root: Path, info: RepoInfo) -> None:
    text = _read(root / "Makefile")
    if not text:
        return
    targets = set()
    for line in text.splitlines():
        m = re.match(r"^([A-Za-z0-9][A-Za-z0-9_.-]*)\s*:(?!=)", line)
        if m:
            targets.add(m.group(1))
    info.make_targets = targets
    for name in ("install", "build", "test", "lint", "run", "dev", "clean", "format"):
        if name in targets:
            info.commands.append(Command(f"make {name}", f"make {name}", "Makefile"))


def _other_commands(root: Path, info: RepoInfo) -> None:
    if (root / "Cargo.toml").exists():
        info.package_managers.append("cargo")
        info.commands += [
            Command("Build", "cargo build", "Cargo.toml"),
            Command("Run tests", "cargo test", "Cargo.toml"),
            Command("Lint", "cargo clippy", "Cargo.toml"),
        ]
    if (root / "go.mod").exists():
        info.package_managers.append("go")
        info.commands += [
            Command("Build", "go build ./...", "go.mod"),
            Command("Run tests", "go test ./...", "go.mod"),
        ]
    if (root / "platformio.ini").exists():
        info.package_managers.append("platformio")
        info.commands += [
            Command("Build firmware", "pio run", "platformio.ini"),
            Command("Upload firmware", "pio run -t upload", "platformio.ini"),
        ]


def scan(root: str | Path) -> RepoInfo:
    root = Path(root).resolve()
    info = RepoInfo(root=root, name=root.name)

    langs: dict[str, int] = {}
    for path in _walk(root):
        lang = LANG_BY_EXT.get(path.suffix.lower())
        if lang:
            langs[lang] = langs.get(lang, 0) + 1
    info.languages = langs

    _node_commands(root, info)
    _python_commands(root, info)
    _make_commands(root, info)
    _other_commands(root, info)

    # drop duplicate commands, keep first
    seen: set[str] = set()
    unique: list[Command] = []
    for c in info.commands:
        if c.cmd not in seen:
            seen.add(c.cmd)
            unique.append(c)
    info.commands = unique

    info.package_managers = list(dict.fromkeys(info.package_managers))

    for entry in sorted(root.iterdir()):
        if entry.is_dir() and entry.name not in IGNORE_DIRS and not entry.name.startswith(".") \
                or entry.name == ".github" and entry.is_dir():
            info.top_dirs.append((entry.name, DIR_HINTS.get(entry.name, "")))

    for cfg in CONFIG_FILES:
        if (root / cfg).exists():
            info.config_files.append(cfg)
    info.has_formatter_config = any(c in FORMATTER_CONFIGS for c in info.config_files) or \
        "ruff" in _read(root / "pyproject.toml").lower() or \
        "black" in _read(root / "pyproject.toml").lower()

    wf = root / ".github" / "workflows"
    if wf.is_dir():
        info.ci_files = sorted(p.name for p in wf.iterdir() if p.suffix in {".yml", ".yaml"})

    if not info.description:
        info.description = readme_summary(root)
    return info
