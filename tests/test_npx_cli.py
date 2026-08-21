#!/usr/bin/env python3
"""The npm CLI installs from an ephemeral package into a stable home."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(ROOT, "bin", "agent-config.js")


class NpxCliTest(unittest.TestCase):
    def run_cli(self, home, *args, cwd=None, check=True):
        env = dict(os.environ, HOME=home, PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run(
            ["node", CLI, *args],
            cwd=cwd or ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=check,
        )

    def test_help_and_version(self):
        with tempfile.TemporaryDirectory() as home:
            help_text = self.run_cli(home, "--help").stdout
            self.assertIn("install [guard] [--extras]", help_text)
            # The guardrails install on their own. Pinned because that path was
            # shipped, called legacy in the usage text, and documented nowhere.
            self.assertIn("install guard", help_text)
            self.assertEqual(self.run_cli(home, "--version").stdout.strip(), "0.2.0")

    def test_guard_round_trip_uses_stable_versioned_payload(self):
        with tempfile.TemporaryDirectory() as home:
            result = self.run_cli(home, "install", "guard")
            stable = os.path.join(home, ".local", "share", "agent-config", "0.2.0")
            self.assertEqual(result.returncode, 0)
            self.assertTrue(os.path.isfile(os.path.join(stable, "install.sh")))
            hook = os.path.join(home, ".claude", "hooks", "guard-bash.py")
            self.assertTrue(os.path.islink(hook))
            self.assertTrue(os.readlink(hook).startswith(stable + os.sep))
            self.run_cli(home, "doctor", "guard")
            self.run_cli(home, "uninstall", "guard")
            self.assertFalse(os.path.lexists(hook))

    def test_init_creates_one_project_contract_for_both_hosts(self):
        with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as project:
            self.run_cli(home, "init", cwd=project)
            agents = os.path.join(project, "AGENTS.md")
            claude = os.path.join(project, "CLAUDE.md")
            self.assertTrue(os.path.isfile(agents))
            self.assertTrue(os.path.islink(claude))
            self.assertEqual(os.readlink(claude), "AGENTS.md")

    def test_existing_staged_payload_must_match_the_package(self):
        with tempfile.TemporaryDirectory() as home:
            self.run_cli(home, "install", "guard")
            staged = os.path.join(home, ".local", "share", "agent-config",
                                  "0.2.0", "install.sh")
            with open(staged, "a", encoding="utf-8") as fh:
                fh.write("\n# tampered\n")
            result = self.run_cli(home, "install", "guard", check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("does not match the published package", result.stderr)

    def test_pack_contains_runtime_and_excludes_private_working_state(self):
        result = subprocess.run(
            ["npm", "pack", "--dry-run", "--json", "--ignore-scripts"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        files = {entry["path"] for entry in json.loads(result.stdout)[0]["files"]}
        self.assertIn("bin/agent-config.js", files)
        self.assertIn("hooks/guard-bash.py", files)
        self.assertIn("skills/ship/SKILL.md", files)
        self.assertIn("scripts/manage_conflicts.py", files)
        self.assertIn("scripts/manage_instructions.py", files)
        self.assertIn("templates/AGENTS.global.md", files)
        self.assertNotIn("PRODUCT.md", files)
        self.assertFalse(any(path.startswith("evals/") for path in files))
        self.assertFalse(any(path.startswith("tests/") for path in files))
        self.assertFalse(any(".lavish" in path for path in files))
        self.assertFalse(any("__pycache__" in path for path in files))
        self.assertFalse(any(path.endswith((".pyc", ".pyo")) for path in files))

    def test_packed_tarball_runs_through_npx(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                ["npm", "pack", "--json", "--ignore-scripts",
                 "--pack-destination", directory],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=True,
            )
            tarball = os.path.join(directory, json.loads(result.stdout)[0]["filename"])
            home = os.path.join(directory, "home")
            os.mkdir(home)
            env = dict(os.environ, HOME=home,
                       npm_config_cache=os.path.join(directory, "npm-cache"))
            executed = subprocess.run(
                ["npx", "--yes", "--package", tarball,
                 "agent-config", "--version"],
                cwd=directory,
                env=env,
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertEqual(executed.stdout.strip(), "0.2.0")

    def test_packed_tarball_installs_and_removes_standard_setup(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                ["npm", "pack", "--json", "--ignore-scripts",
                 "--pack-destination", directory],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=True,
            )
            tarball = os.path.join(directory, json.loads(result.stdout)[0]["filename"])
            home = os.path.join(directory, "home")
            os.mkdir(home)
            os.makedirs(os.path.join(home, ".claude", "skills", "review"))
            instructions = os.path.join(home, ".claude", "CLAUDE.md")
            original_instructions = b"My instructions.  \n\n"
            Path(instructions).write_bytes(original_instructions)
            Path(home, ".claude", "skills", "review", "SKILL.md").write_text(
                "existing review\n", encoding="utf-8")
            env = dict(os.environ, HOME=home,
                       npm_config_cache=os.path.join(directory, "npm-cache"),
                       PYTHONDONTWRITEBYTECODE="1")
            prefix = ["npx", "--yes", "--package", tarball, "agent-config"]
            subprocess.run(prefix + ["install", "--replace-conflicts"], cwd=directory, env=env,
                           text=True, capture_output=True, check=True)
            hook = os.path.join(home, ".claude", "hooks", "guard-bash.py")
            stable = os.path.join(home, ".local", "share", "agent-config", "0.2.0")
            self.assertTrue(os.path.islink(hook))
            self.assertTrue(os.readlink(hook).startswith(stable + os.sep))
            self.assertTrue(os.path.islink(os.path.join(
                home, ".claude", "skills", "ship")))
            self.assertIn("agent-config:start", Path(instructions).read_text(
                encoding="utf-8"))
            subprocess.run(prefix + ["doctor"], cwd=directory, env=env,
                           text=True, capture_output=True, check=True)
            subprocess.run(prefix + ["uninstall"], cwd=directory, env=env,
                           text=True, capture_output=True, check=True)
            self.assertFalse(os.path.lexists(hook))
            self.assertEqual(Path(instructions).read_bytes(), original_instructions)
            self.assertEqual(Path(home, ".claude", "skills", "review", "SKILL.md").read_text(
                encoding="utf-8"), "existing review\n")

    def test_unknown_options_fail_without_installing(self):
        with tempfile.TemporaryDirectory() as home:
            result = self.run_cli(home, "install", "guard", "--dry-run", check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unknown install option", result.stderr)
            self.assertFalse(os.path.exists(os.path.join(home, ".local", "share",
                                                        "agent-config")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
