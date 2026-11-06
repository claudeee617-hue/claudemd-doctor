import json
import tempfile
import unittest
from pathlib import Path

from claudemd_doctor.cli import main
from claudemd_doctor.generator import generate
from claudemd_doctor.linter import lint_text
from claudemd_doctor.scanner import scan


def make_repo(files: dict[str, str]) -> Path:
    root = Path(tempfile.mkdtemp())
    for name, content in files.items():
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return root


NODE_REPO = {
    "package.json": json.dumps({
        "name": "demo", "description": "A demo app",
        "scripts": {"dev": "vite", "build": "vite build", "test": "vitest", "lint": "eslint ."},
    }),
    "pnpm-lock.yaml": "",
    "src/index.ts": "export {}",
    "src/app.tsx": "export {}",
    ".prettierrc": "{}",
    ".github/workflows/ci.yml": "on: push",
}


class ScannerTests(unittest.TestCase):
    def test_detects_node_project(self):
        info = scan(make_repo(NODE_REPO))
        cmds = {c.cmd for c in info.commands}
        self.assertIn("pnpm install", cmds)
        self.assertIn("pnpm run build", cmds)
        self.assertEqual(info.package_managers, ["pnpm"])
        self.assertEqual(info.main_languages()[0], "TypeScript")
        self.assertTrue(info.has_formatter_config)
        self.assertEqual(info.ci_files, ["ci.yml"])

    def test_detects_python_and_makefile(self):
        info = scan(make_repo({
            "pyproject.toml": '[project]\ndescription = "Tool"\n[tool.pytest.ini_options]\n',
            "Makefile": "build:\n\techo hi\ntest:\n\tpytest\n.PHONY: build\n",
            "app.py": "",
        }))
        cmds = {c.cmd for c in info.commands}
        self.assertIn("pytest", cmds)
        self.assertIn("make build", cmds)
        self.assertEqual(info.make_targets, {"build", "test"})
        self.assertEqual(info.description, "Tool")

    def test_detects_unittest(self):
        info = scan(make_repo({
            "pyproject.toml": "[project]\nname='x'\n",
            "tests/test_a.py": "import unittest\n",
        }))
        self.assertIn("python -m unittest discover -s tests", {c.cmd for c in info.commands})
        self.assertNotIn("pytest", {c.cmd for c in info.commands})

    def test_ignores_node_modules(self):
        info = scan(make_repo({"node_modules/x/a.js": "", "main.py": ""}))
        self.assertEqual(info.languages, {"Python": 1})

    def test_readme_summary(self):
        info = scan(make_repo({"README.md": "# T\n\n[![b](x)](y)\n\nDoes a useful thing.\n"}))
        self.assertEqual(info.description, "Does a useful thing.")


class GeneratorTests(unittest.TestCase):
    def test_generated_file_is_clean_when_linted(self):
        root = make_repo(NODE_REPO)
        info = scan(root)
        text = generate(info)
        self.assertIn("## Commands", text)
        self.assertIn("`pnpm run build`", text)
        report = lint_text(text, info)
        self.assertEqual(report.errors, 0)
        self.assertGreaterEqual(report.score, 90)


class LinterTests(unittest.TestCase):
    def setUp(self):
        self.root = make_repo(NODE_REPO)
        self.info = scan(self.root)

    def rules(self, text):
        return {i.rule for i in lint_text(text, self.info).issues}

    def test_vague_rule(self):
        self.assertIn("vague-rule", self.rules("# X\n- Write clean code\n`pnpm run build`\n"))

    def test_stale_path(self):
        self.assertIn("stale-path", self.rules("# X\nSee `src/missing.ts`. `pnpm run build`\n"))

    def test_existing_path_ok(self):
        self.assertNotIn("stale-path", self.rules("# X\nSee `src/index.ts`. `pnpm run build`\n"))

    def test_stale_path_backslash(self):
        self.assertIn("stale-path", self.rules("# X\nSee `src\\missing.ts`. `pnpm run build`\n"))

    def test_existing_backslash_path_ok(self):
        self.assertNotIn("stale-path", self.rules("# X\nSee `src\\index.ts`. `pnpm run build`\n"))

    def test_stale_npm_script(self):
        self.assertIn("stale-command", self.rules("# X\nRun `npm run deploy`\n"))

    def test_valid_npm_script(self):
        self.assertNotIn("stale-command", self.rules("# X\nRun `npm run build`\n"))

    def test_stale_command_in_fence(self):
        self.assertIn("stale-command", self.rules("# X\n```\n$ pnpm run nope\n```\n"))

    def test_secret_is_error(self):
        report = lint_text("# X\n`pnpm run build`\napi_key = abcdef123456\n", self.info)
        self.assertGreaterEqual(report.errors, 1)

    def test_too_long(self):
        text = "# X\n`pnpm run build`\n" + "\n".join(f"- rule number {i} here" for i in range(250))
        self.assertIn("too-long", self.rules(text))

    def test_no_commands(self):
        self.assertIn("no-commands", self.rules("# X\nBe nice to the user.\n"))

    def test_style_rule_when_formatter_exists(self):
        self.assertIn("style-in-claude-md",
                      self.rules("# X\n- Use 2 spaces for indentation\n`pnpm run build`\n"))

    def test_shouting(self):
        text = "# X\n`pnpm run build`\n" + "\n".join(f"- NEVER do thing {i}" for i in range(10))
        self.assertIn("shouting", self.rules(text))

    def test_duplicates(self):
        line = "- Always run the full test suite before committing"
        self.assertIn("duplicate", self.rules(f"# X\n`pnpm run build`\n{line}\n{line}\n"))

    def test_make_target(self):
        info = scan(make_repo({"Makefile": "build:\n\techo\n"}))
        issues = lint_text("# X\nRun `make deploy`\n", info).issues
        self.assertTrue(any(i.rule == "stale-command" for i in issues))


class CliTests(unittest.TestCase):
    def test_generate_then_lint(self):
        root = make_repo(NODE_REPO)
        self.assertEqual(main(["generate", str(root)]), 0)
        self.assertTrue((root / "CLAUDE.md").exists())
        self.assertEqual(main(["generate", str(root)]), 2)  # refuses to overwrite
        self.assertEqual(main(["generate", str(root), "--force"]), 0)
        self.assertEqual(main(["lint", str(root), "--no-color"]), 0)

    def test_lint_fails_on_errors(self):
        root = make_repo({**NODE_REPO, "CLAUDE.md": "# X\nRun `npm run ghost`\n"})
        self.assertEqual(main(["lint", str(root)]), 1)

    def test_fail_under(self):
        root = make_repo({**NODE_REPO, "CLAUDE.md": "# X\n- Write clean code\n"})
        self.assertEqual(main(["lint", str(root), "--fail-under", "95"]), 1)

    def test_missing_file(self):
        self.assertEqual(main(["lint", str(make_repo({"a.py": ""}))]), 2)


if __name__ == "__main__":
    unittest.main()
