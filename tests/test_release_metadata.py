#!/usr/bin/env python3
"""Release metadata and native plugin surfaces stay synchronized."""
import json
import filecmp
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class ReleaseMetadataTest(unittest.TestCase):
    def assert_tree_equal(self, left, right):
        def files(root):
            found = []
            for current, dirs, names in os.walk(root):
                dirs[:] = [name for name in dirs if name != "__pycache__"]
                for name in names:
                    if not name.endswith(".pyc"):
                        found.append(os.path.relpath(os.path.join(current, name), root))
            return sorted(found)

        self.assertEqual(files(left), files(right))
        for relative in files(left):
            self.assertTrue(filecmp.cmp(os.path.join(left, relative),
                                       os.path.join(right, relative), shallow=False),
                            relative)

    def test_versions_match(self):
        with open(os.path.join(ROOT, "VERSION")) as fh:
            version = fh.read().strip()
        with open(os.path.join(ROOT, "package.json")) as fh:
            package = json.load(fh)
        self.assertEqual(package["version"], version)
        self.assertEqual(package["name"], "@sid-thephysicskid/agent-config")
        self.assertEqual(package["publishConfig"]["access"], "public")
        for name in ("agent-guard", "agent-workflow", "agent-operator"):
            for host in (".codex-plugin", ".claude-plugin"):
                path = os.path.join(ROOT, "plugins", name, host, "plugin.json")
                with open(path) as fh:
                    self.assertEqual(json.load(fh)["version"], version,
                                     "%s %s" % (name, host))

    def test_npm_publish_uses_oidc_and_a_public_release(self):
        path = os.path.join(ROOT, ".github", "workflows", "publish.yml")
        with open(path) as fh:
            workflow = fh.read()
        self.assertIn("release:\n    types: [published]", workflow)
        self.assertIn("id-token: write", workflow)
        self.assertIn("registry-url: https://registry.npmjs.org", workflow)
        self.assertIn("GITHUB_REF_NAME", workflow)
        self.assertIn('require("./package.json").version', workflow)
        self.assertIn("./scripts/ci-local --full", workflow)
        self.assertIn("npm publish", workflow)
        self.assertIn("NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}", workflow)
        self.assertIn("Remove the secret", workflow)

    def test_marketplace_lists_three_optional_products(self):
        path = os.path.join(ROOT, ".agents", "plugins", "marketplace.json")
        with open(path) as fh:
            entries = json.load(fh)["plugins"]
        self.assertEqual({entry["name"] for entry in entries},
                         {"agent-guard", "agent-workflow", "agent-operator"})
        self.assertTrue(all(entry["policy"]["installation"] == "AVAILABLE"
                            for entry in entries))

    def test_claude_marketplace_lists_three_optional_products(self):
        path = os.path.join(ROOT, ".claude-plugin", "marketplace.json")
        with open(path) as fh:
            entries = json.load(fh)["plugins"]
        self.assertEqual({entry["name"] for entry in entries},
                         {"agent-guard", "agent-workflow", "agent-operator"})
        with open(os.path.join(ROOT, "VERSION")) as fh:
            version = fh.read().strip()
        self.assertTrue(all(entry["version"] == version for entry in entries))

    def test_workflow_plugin_exports_exactly_the_canonical_skills(self):
        canonical = {name for name in os.listdir(os.path.join(ROOT, "skills"))
                     if os.path.isfile(os.path.join(
                         ROOT, "skills", name, "SKILL.md"))}
        exported_dir = os.path.join(ROOT, "plugins", "agent-workflow", "skills")
        exported = set(os.listdir(exported_dir))
        self.assertEqual(exported, canonical)
        for name in exported:
            packaged = os.path.join(exported_dir, name)
            self.assertTrue(os.path.isfile(os.path.join(packaged, "SKILL.md")), name)
            self.assert_tree_equal(os.path.join(ROOT, "skills", name), packaged)

    def test_bootstrap_and_setup_own_the_project_contract(self):
        with open(os.path.join(ROOT, "skills", "bootstrap", "SKILL.md")) as fh:
            bootstrap = fh.read()
        with open(os.path.join(ROOT, "skills", "setup", "SKILL.md")) as fh:
            setup = fh.read()
        self.assertIn("replaces the initializer's generic project-contract", bootstrap)
        self.assertIn("replace its generic `## Project\ncontract` section", setup)

    def test_operator_plugin_exports_exactly_the_optional_skills(self):
        canonical = {name for name in os.listdir(os.path.join(ROOT, "operator-skills"))
                     if os.path.isfile(os.path.join(
                         ROOT, "operator-skills", name, "SKILL.md"))}
        exported_dir = os.path.join(ROOT, "plugins", "agent-operator", "skills")
        exported = set(os.listdir(exported_dir))
        self.assertEqual(exported, canonical)
        for name in exported:
            packaged = os.path.join(exported_dir, name)
            self.assertTrue(os.path.isfile(os.path.join(packaged, "SKILL.md")), name)
            self.assert_tree_equal(os.path.join(ROOT, "operator-skills", name),
                                   packaged)

    def test_plugin_sources_are_self_contained_real_files(self):
        for current, dirs, files in os.walk(os.path.join(ROOT, "plugins")):
            for name in dirs + files:
                path = os.path.join(current, name)
                self.assertFalse(os.path.islink(path), path)
                self.assertNotEqual(name, "__pycache__")
                self.assertFalse(name.endswith(".pyc"), name)

    def test_no_scaffold_placeholders_reach_plugin_metadata(self):
        for current, _, files in os.walk(os.path.join(ROOT, "plugins")):
            for name in files:
                path = os.path.join(current, name)
                if os.path.islink(path):
                    continue
                with open(path, errors="ignore") as fh:
                    text = fh.read()
                self.assertNotIn("[TODO:", text, path)
                self.assertNotIn("Local developer", text, path)

    def test_guard_plugin_executes_the_live_adapter(self):
        plugin = os.path.join(ROOT, "plugins", "agent-guard")
        with open(os.path.join(plugin, "hooks", "hooks.json")) as fh:
            command = json.load(fh)["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        payload = b'{"tool_name":"Bash","tool_input":{"command":"rm -rf /"},"cwd":"/tmp"}'
        result = subprocess.run(["bash", "-c", command], input=payload,
                                capture_output=True,
                                env=dict(os.environ, CLAUDE_PLUGIN_ROOT=plugin,
                                         PYTHONDONTWRITEBYTECODE="1"))
        self.assertEqual(result.returncode, 2, result.stderr.decode())

    def test_plugin_sources_point_at_canonical_payloads(self):
        guard_dir = os.path.join(ROOT, "plugins", "agent-guard", "hooks")
        for name in os.listdir(os.path.join(ROOT, "hooks")):
            if not (name.startswith("guard") and name.endswith(".py")):
                continue
            packaged = os.path.join(guard_dir, name)
            self.assertTrue(os.path.isfile(packaged), name)
            self.assertTrue(filecmp.cmp(packaged, os.path.join(ROOT, "hooks", name),
                                        shallow=False), name)
        style_dir = os.path.join(ROOT, "plugins", "agent-operator", "output-styles")
        self.assertEqual(set(os.listdir(style_dir)), set(os.listdir(
            os.path.join(ROOT, "output-styles"))))
        for name in os.listdir(style_dir):
            self.assertTrue(filecmp.cmp(os.path.join(style_dir, name),
                                        os.path.join(ROOT, "output-styles", name),
                                        shallow=False), name)
        self.assert_tree_equal(os.path.join(ROOT, "operator-profiles"),
                               os.path.join(ROOT, "plugins", "agent-operator",
                                            "operator-profiles"))
        workflow = os.path.join(ROOT, "plugins", "agent-workflow")
        for relative in ("scripts/agent-init", "templates/AGENTS.project.md"):
            self.assertTrue(filecmp.cmp(os.path.join(ROOT, relative),
                                        os.path.join(workflow, relative),
                                        shallow=False), relative)

    def test_published_plugin_sources_carry_exact_legal_notices(self):
        for plugin in ("agent-guard", "agent-workflow", "agent-operator"):
            root = os.path.join(ROOT, "plugins", plugin)
            for name in ("LICENSE", "THIRD-PARTY-NOTICES.md"):
                self.assertTrue(filecmp.cmp(os.path.join(ROOT, name),
                                            os.path.join(root, name),
                                            shallow=False),
                                "%s/%s" % (plugin, name))

    def test_release_artifacts_are_self_contained(self):
        with tempfile.TemporaryDirectory() as parent:
            output = os.path.join(parent, "release")
            subprocess.run(["bash", os.path.join(ROOT, "scripts",
                                                  "build-plugins"), output],
                           check=True, capture_output=True, text=True)
            for plugin in ("agent-guard", "agent-workflow", "agent-operator"):
                root = os.path.join(output, plugin)
                self.assertTrue(os.path.isfile(os.path.join(root, "LICENSE")))
                self.assertTrue(os.path.isfile(os.path.join(
                    root, "THIRD-PARTY-NOTICES.md")))
                for current, dirs, files in os.walk(root):
                    for name in dirs + files:
                        self.assertFalse(os.path.islink(os.path.join(current, name)),
                                         os.path.join(current, name))
                        self.assertNotEqual(name, "__pycache__")
                        self.assertFalse(name.endswith(".pyc"), name)
                self.assertTrue(os.path.isfile(os.path.join(
                    root, ".codex-plugin", "plugin.json")))
                self.assertTrue(os.path.isfile(os.path.join(
                    root, ".claude-plugin", "plugin.json")))
            self.assertTrue(os.path.isfile(os.path.join(
                output, "agent-workflow", "skills", "ship", "SKILL.md")))
            self.assertTrue(os.path.isfile(os.path.join(
                output, "agent-workflow", "scripts", "agent-init")))
            self.assertTrue(os.path.isfile(os.path.join(
                output, "agent-workflow", "templates", "AGENTS.project.md")))
            self.assertTrue(os.path.isfile(os.path.join(
                output, "agent-guard", "hooks", "guard-codex.py")))
            self.assertTrue(os.path.isfile(os.path.join(
                output, "agent-operator", "skills", "wizard", "SKILL.md")))
            self.assertTrue(os.path.isfile(os.path.join(
                output, "agent-operator", "output-styles", "terse.md")))

    def test_release_builder_refuses_an_existing_destination(self):
        with tempfile.TemporaryDirectory() as output:
            sentinel = os.path.join(output, "mine")
            with open(sentinel, "w") as fh:
                fh.write("untouched")
            result = subprocess.run(
                ["bash", os.path.join(ROOT, "scripts", "build-plugins"), output],
                capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            with open(sentinel) as fh:
                self.assertEqual(fh.read(), "untouched")

    def test_release_builder_leaves_no_partial_destination_on_failure(self):
        with tempfile.TemporaryDirectory() as parent:
            clone = os.path.join(parent, "repo")
            shutil.copytree(ROOT, clone, ignore=shutil.ignore_patterns(
                ".git", ".claude", "__pycache__", "*.pyc"))
            os.remove(os.path.join(clone, "output-styles", "terse.md"))
            output = os.path.join(parent, "release")
            result = subprocess.run(
                ["bash", os.path.join(clone, "scripts", "build-plugins"), output],
                capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(os.path.lexists(output))

    def test_public_release_builder_is_tracked_and_executable(self):
        path = os.path.join(ROOT, "scripts", "build-public-release")
        self.assertTrue(os.path.isfile(path))
        self.assertTrue(os.access(path, os.X_OK))

    def test_public_release_builder_exports_clean_history_free_source(self):
        with tempfile.TemporaryDirectory() as parent:
            repo = os.path.join(parent, "repo")
            export = os.path.join(parent, "public")
            shutil.copytree(ROOT, repo, ignore=shutil.ignore_patterns(
                ".git", ".claude", "__pycache__", "node_modules", "*.pyc"))
            for command in (
                    ["git", "init", "-b", "main"],
                    ["git", "config", "user.email", "release@example.com"],
                    ["git", "config", "user.name", "Release Test"],
                    ["git", "add", "--all"],
                    ["git", "commit", "-m", "test: release fixture"]):
                subprocess.run(command, cwd=repo, check=True,
                               capture_output=True, text=True)
            for unsafe in ("public", os.path.join(parent, "repo-link", "public")):
                if "repo-link" in unsafe:
                    os.symlink(repo, os.path.join(parent, "repo-link"))
                refused = subprocess.run(
                    [os.path.join(repo, "scripts", "build-public-release"), unsafe],
                    cwd=repo,
                    capture_output=True,
                    text=True,
                )
                self.assertNotEqual(refused.returncode, 0)
                self.assertIn("Refusing unsafe destination", refused.stderr)
                self.assertFalse(os.path.lexists(os.path.join(repo, "public")))
            result = subprocess.run(
                [os.path.join(repo, "scripts", "build-public-release"), export],
                cwd=repo,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse(os.path.exists(os.path.join(export, ".git")))
            self.assertTrue(os.path.isfile(os.path.join(export, "package.json")))
            self.assertIn("no Git history", result.stdout)

    def test_public_audit_scans_a_history_free_tree(self):
        with tempfile.TemporaryDirectory() as parent:
            export = os.path.join(parent, "export")
            shutil.copytree(ROOT, export, ignore=shutil.ignore_patterns(
                ".git", ".claude", "__pycache__", "node_modules", "*.pyc"))
            result = subprocess.run(
                ["python3", os.path.join(export, "tests", "audit.py")],
                cwd=export,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("audit: 0 tracked files", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
