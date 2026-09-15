#!/usr/bin/env python3
"""Codex and Cursor hooks.json merge and strip behavior."""
import json
import os
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import install_hooks_json as H  # noqa: E402


class CodexHooksTest(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        self.original = {
            "description": "mine",
            "hooks": {
                "PreToolUse": [{
                    "matcher": "Bash",
                    "hooks": [{
                        "type": "command",
                        "command": "python3 ~/mine/audit.py",
                    }],
                }],
            },
        }
        with open(self.path, "w") as f:
            json.dump(self.original, f)

    def tearDown(self):
        for path in (self.path, self.path + ".tmp"):
            if os.path.exists(path):
                os.unlink(path)

    def read(self):
        with open(self.path) as f:
            return json.load(f)

    def commands(self, event):
        return [
            hook.get("command", "")
            for group in self.read().get("hooks", {}).get(event, [])
            for hook in group.get("hooks", [])
        ]

    def test_existing_hook_survives_merge_and_strip(self):
        H.merge("codex", self.path, "/opt/agent-config")
        self.assertIn("python3 ~/mine/audit.py", self.commands("PreToolUse"))

        H.strip(self.path)
        self.assertEqual(self.read(), self.original)

    def test_installs_only_the_pre_tool_and_prompt_guards(self):
        H.merge("codex", self.path, "/opt/agent-config")
        cfg = self.read()
        self.assertTrue(any("guard-codex.py" in c for c in self.commands("PreToolUse")))
        self.assertEqual(len(self.commands("UserPromptSubmit")), 1)
        self.assertIn("guard-prompt.py", self.commands("UserPromptSubmit")[0])
        self.assertNotIn("matcher", cfg["hooks"]["UserPromptSubmit"][0])
        self.assertNotIn("Stop", cfg["hooks"])
        self.assertNotIn("SessionStart", cfg["hooks"])

    def test_merge_is_idempotent(self):
        H.merge("codex", self.path, "/opt/agent-config")
        first = self.read()
        for _ in range(3):
            H.merge("codex", self.path, "/opt/agent-config")
        self.assertEqual(self.read(), first)

    def test_relocation_replaces_only_our_old_commands(self):
        H.merge("codex", self.path, "/old/agent-config")
        H.merge("codex", self.path, "/new/agent-config")
        rendered = json.dumps(self.read())
        self.assertNotIn("/old/agent-config", rendered)
        self.assertIn("/new/agent-config", rendered)
        self.assertIn("python3 ~/mine/audit.py", rendered)

    def test_upgrades_the_previous_exclusive_file_and_still_uninstalls_cleanly(self):
        legacy = {
            "description": "Guardrails shared with Claude Code via agent-config/hooks",
            "hooks": {
                "PreToolUse": [{
                    "matcher": ".*",
                    "hooks": [{
                        "type": "command",
                        "command": H._legacy_command(
                            "/old/agent-config", "guard-codex.py"),
                        "timeout": 5,
                        "statusMessage": "Checking guardrails...",
                    }],
                }],
            },
        }
        with open(self.path, "w") as f:
            json.dump(legacy, f)
        H.merge("codex", self.path, "/new/agent-config")
        self.assertEqual(self.read()["description"], H.DESCRIPTION)
        H.strip(self.path)
        self.assertFalse(os.path.exists(self.path))

    def test_a_command_that_only_mentions_our_script_is_not_removed(self):
        theirs = "python3 ~/mine/wrap.py --after hooks/guard-codex.py"
        self.original["hooks"]["PreToolUse"][0]["hooks"].append({
            "type": "command",
            "command": theirs,
        })
        with open(self.path, "w") as f:
            json.dump(self.original, f)
        H.merge("codex", self.path, "/opt/agent-config")
        H.strip(self.path)
        self.assertIn(theirs, self.commands("PreToolUse"))

    def test_an_unrelated_hook_with_the_same_script_name_is_not_removed(self):
        theirs = H._legacy_command("/opt/not-agent-config", "guard-codex.py")
        self.original["hooks"]["SessionStart"] = [{
            "hooks": [{
                "type": "command",
                "command": theirs,
                "timeout": 5,
                "statusMessage": "Loading agent-config...",
            }],
        }]
        with open(self.path, "w") as f:
            json.dump(self.original, f)
        H.merge("codex", self.path, "/opt/agent-config")
        H.strip(self.path)
        self.assertIn(theirs, self.commands("SessionStart"))

    def test_new_file_is_removed_on_strip(self):
        os.unlink(self.path)
        H.merge("codex", self.path, "/opt/agent-config")
        self.assertTrue(os.path.exists(self.path))
        H.strip(self.path)
        self.assertFalse(os.path.exists(self.path))

    def test_owned_description_is_removed_when_user_keys_remain(self):
        os.unlink(self.path)
        H.merge("codex", self.path, "/opt/agent-config")
        cfg = self.read()
        cfg["theme"] = "mine"
        with open(self.path, "w") as f:
            json.dump(cfg, f)
        H.strip(self.path)
        self.assertEqual(self.read(), {"theme": "mine"})

    def test_merge_preserves_existing_file_mode(self):
        os.chmod(self.path, 0o600)
        H.merge("codex", self.path, "/opt/agent-config")
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o600)

    def test_command_quotes_an_apostrophe_in_the_repo_path(self):
        command = H._command("/opt/sid's config", "guard-codex.py")
        self.assertIn("sid'\"'\"'s config", command)

    def test_check_requires_the_current_definition(self):
        H.merge("codex", self.path, "/opt/agent-config")
        self.assertTrue(H.check("codex", self.path, "/opt/agent-config"))
        cfg = self.read()
        cfg["hooks"]["PreToolUse"] = [cfg["hooks"]["PreToolUse"][0]]
        with open(self.path, "w") as f:
            json.dump(cfg, f)
        self.assertFalse(H.check("codex", self.path, "/opt/agent-config"))

    def test_merge_removes_retired_tagged_lifecycle_hooks(self):
        self.original["hooks"]["Stop"] = [{"hooks": [{
            "type": "command",
            "command": H._command("/old/agent-config", "gone.py"),
            "timeout": 130,
            "statusMessage": "Checking documentation...",
        }]}]
        with open(self.path, "w") as f:
            json.dump(self.original, f)
        H.merge("codex", self.path, "/new/agent-config")
        self.assertNotIn("Stop", self.read()["hooks"])

    def test_rejects_a_malformed_user_hook_before_rewriting(self):
        malformed = {"hooks": {"PreToolUse": [{"hooks": ["not an object"]}]}}
        with open(self.path, "w") as f:
            json.dump(malformed, f)
        with open(self.path) as f:
            before = f.read()
        with self.assertRaises(ValueError):
            H.merge("codex", self.path, "/opt/agent-config")
        with open(self.path) as f:
            self.assertEqual(f.read(), before)

    def test_replaces_a_0_4_onbelay_hook(self):
        onbelay = {"description": "PreToolUse guardrails from onbelay", "hooks": {"PreToolUse": [{
            "matcher": ".*", "hooks": [{"type": "command", "command": H._command(
                "/old/onbelay/0.4.2", "guard-codex.py").replace("agent-config-hook-v1", "onbelay-hook-v1")}]}]}}
        with open(self.path, "w") as f:
            json.dump(onbelay, f)
        H.merge("codex", self.path, "/new/agent-config")
        self.assertNotIn("onbelay", json.dumps(self.read()))
        self.assertTrue(H.check("codex", self.path, "/new/agent-config"))
        self.assertEqual(len(self.commands("PreToolUse")), 1)

    def test_strip_restores_the_backup_bytes_and_skips_files_without_ours(self):
        original = '{"description":"mine","hooks":{"PreToolUse":[{"matcher":"Bash","hooks":[{"type":"command","command":"python3 ~/mine/audit.py"}]}]}}'
        with open(self.path, "w") as f:
            f.write(original)
        H.strip(self.path)
        with open(self.path) as f:
            self.assertEqual(f.read(), original)
        with open(self.path + H.BACKUP_SUFFIX, "w") as f:
            f.write(original)
        H.merge("codex", self.path, "/opt/agent-config")
        H.strip(self.path)
        with open(self.path) as f:
            self.assertEqual(f.read(), original)
        self.assertFalse(os.path.exists(self.path + H.BACKUP_SUFFIX))

    def test_updates_a_symlink_target_without_detaching_it(self):
        target = self.path + ".target"
        os.rename(self.path, target)
        os.symlink(target, self.path)
        try:
            H.merge("codex", self.path, "/opt/agent-config")
            self.assertTrue(os.path.islink(self.path))
            self.assertTrue(H.check("codex", self.path, "/opt/agent-config"))
        finally:
            os.unlink(self.path)
            os.unlink(target)


class CursorHooksTest(unittest.TestCase):
    ORIGINAL = {"version": 1, "theirs": True, "hooks": {
        "stop": [{"command": "./hooks/mine.sh"}],
        "preToolUse": [{"command": "./hooks/audit.sh", "matcher": "Shell"}]}}

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "hooks.json")
        with open(self.path, "w") as f:
            json.dump(self.ORIGINAL, f)

    def tearDown(self):
        self.dir.cleanup()

    def read(self):
        with open(self.path) as f:
            return json.load(f)

    def test_merge_keeps_their_entries_and_is_idempotent(self):
        H.merge("cursor", self.path, "/opt/agent-config")
        first = self.read()
        H.merge("cursor", self.path, "/opt/agent-config")
        self.assertEqual(self.read(), first)
        self.assertEqual((first["version"], first["theirs"]), (1, True))
        self.assertNotIn("description", first)
        self.assertEqual(first["hooks"]["stop"], self.ORIGINAL["hooks"]["stop"])
        self.assertIn(self.ORIGINAL["hooks"]["preToolUse"][0], first["hooks"]["preToolUse"])
        self.assertTrue(H.check("cursor", self.path, "/opt/agent-config"))
        self.assertFalse(H.check("cursor", self.path, "/new/agent-config"))

    def test_entries_are_flat_and_a_missing_hook_exits_1(self):
        H.merge("cursor", self.path, "/opt/agent-config")
        hooks = self.read()["hooks"]
        tool = [e for e in hooks["preToolUse"] if "guard-cursor.py" in e["command"]]
        self.assertEqual(len(tool), 1)
        self.assertEqual(sorted(tool[0]), ["command", "matcher", "timeout", "type"])
        self.assertTrue(tool[0]["command"].endswith("; fi; exit 1"))
        self.assertEqual(len(hooks["beforeSubmitPrompt"]), 1)
        self.assertIn("guard-prompt.py", hooks["beforeSubmitPrompt"][0]["command"])

    def test_strip_restores_their_file(self):
        H.merge("cursor", self.path, "/opt/agent-config")
        H.strip(self.path)
        self.assertEqual(self.read(), self.ORIGINAL)

    def test_a_file_merge_created_is_removed_on_strip(self):
        os.unlink(self.path)
        H.merge("cursor", self.path, "/opt/agent-config")
        self.assertEqual(list(self.read())[0], "version")
        H.strip(self.path)
        self.assertFalse(os.path.exists(self.path))


if __name__ == "__main__":
    unittest.main(verbosity=2)
