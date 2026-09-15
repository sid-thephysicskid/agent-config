#!/usr/bin/env python3
"""The npm CLI stages a versioned payload and drives install.sh from it."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(ROOT, "bin", "agent-config.js")
VERSION = open(os.path.join(ROOT, "VERSION")).read().strip()


def packed(stdout):
    """npm 10 returns a list, npm 11 an object keyed by name."""
    data = json.loads(stdout)
    return (list(data.values()) if isinstance(data, dict) else data)[0]


def stable(home):
    return os.path.join(home, ".local", "share", "agent-config", VERSION)


class NpxCliTest(unittest.TestCase):
    def run_cli(self, home, *args, check=True):
        return subprocess.run(["node", CLI, *args], cwd=ROOT, text=True, capture_output=True, check=check,
                              env=dict(os.environ, HOME=home, PYTHONDONTWRITEBYTECODE="1"))

    def test_help_and_version(self):
        with tempfile.TemporaryDirectory() as home:
            help_text = self.run_cli(home, "--help").stdout
            for command in ("install", "doctor", "uninstall", "secret"):
                self.assertIn("agent-config " + command, help_text)
            self.assertNotIn("--extras", help_text)
            self.assertEqual(self.run_cli(home, "--version").stdout.strip(), VERSION)

    def test_round_trip_through_a_versioned_payload(self):
        with tempfile.TemporaryDirectory() as home:
            self.assertIn("not installed", self.run_cli(home, "doctor", check=False).stderr)
            self.run_cli(home, "install", "guard")  # the 0.4 spelling still works
            hook = os.path.join(home, ".claude", "hooks", "guard-bash.py")
            self.assertTrue(os.readlink(hook).startswith(stable(home) + os.sep))
            self.assertIn("All good", self.run_cli(home, "doctor").stdout)
            os.remove(hook)
            broken = self.run_cli(home, "doctor", check=False)
            self.assertEqual(broken.returncode, 1)
            self.assertIn("npx @sid-thephysicskid/agent-config@latest install", broken.stdout)
            self.run_cli(home, "uninstall")
            self.assertFalse(os.path.lexists(os.path.join(home, ".claude", "hooks")))
            self.assertFalse(os.path.exists(os.path.join(home, ".local", "share", "agent-config")))

    def test_a_tampered_staged_payload_is_refused(self):
        with tempfile.TemporaryDirectory() as home:
            self.run_cli(home, "install")
            with open(os.path.join(stable(home), "hooks", "guard_rules.py"), "a") as fh:
                fh.write("\n# tampered\n")
            result = self.run_cli(home, "install", check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("does not match the published package", result.stderr)

    def test_unknown_options_fail_without_staging(self):
        with tempfile.TemporaryDirectory() as home:
            for args in (("install", "--extras"), ("install", "--dry-run"), ("init",)):
                self.assertNotEqual(self.run_cli(home, *args, check=False).returncode, 0, args)
            self.assertFalse(os.path.exists(os.path.join(home, ".local")))

    def test_pack_contains_the_payload_and_nothing_private(self):
        result = subprocess.run(["npm", "pack", "--dry-run", "--json", "--ignore-scripts"],
                                cwd=ROOT, text=True, capture_output=True, check=True)
        files = {entry["path"] for entry in packed(result.stdout)["files"]}
        for path in ("bin/agent-config.js", "hooks/guard-bash.py", "hooks/guard-prompt.py", "install.sh",
                     "uninstall.sh", "LICENSE", "README.md", "VERSION", "scripts/install_settings.py",
                     "scripts/install_codex_hooks.py", "scripts/migrate-legacy.sh"):
            self.assertIn(path, files)
        for prefix in ("tests/", "docs/"):
            self.assertFalse(any(p.startswith(prefix) for p in files), prefix)
        hooks = {os.path.basename(p) for p in files if p.startswith("hooks/")}
        self.assertEqual(hooks, set(os.listdir(os.path.join(ROOT, "hooks"))) - {"__pycache__"})
        self.assertFalse(files & {"CHANGELOG.md", "AGENTS.md", "SECURITY.md"})

    def test_packed_tarball_round_trips_through_npx(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(["npm", "pack", "--json", "--ignore-scripts", "--pack-destination", directory],
                                    cwd=ROOT, text=True, capture_output=True, check=True)
            tarball = os.path.join(directory, packed(result.stdout)["filename"])
            home = os.path.join(directory, "home")
            settings = Path(home, ".claude", "settings.json")
            settings.parent.mkdir(parents=True)
            settings.write_bytes(b'{"model":"opus"}\n')
            env = dict(os.environ, HOME=home, PYTHONDONTWRITEBYTECODE="1",
                       npm_config_cache=os.path.join(directory, "npm-cache"))
            prefix = ["npx", "--yes", "--package", tarball, "agent-config"]
            for command in ("--version", "install", "doctor", "uninstall"):
                out = subprocess.run(prefix + [command], cwd=directory, env=env,
                                     text=True, capture_output=True, check=True).stdout
                if command == "--version":
                    self.assertEqual(out.strip(), VERSION)
                if command == "install":
                    self.assertTrue(os.readlink(os.path.join(home, ".claude", "hooks", "guard-bash.py"))
                                    .startswith(stable(home) + os.sep))
            self.assertEqual(settings.read_bytes(), b'{"model":"opus"}\n')
            self.assertEqual(sorted(os.listdir(settings.parent)), ["settings.json"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
