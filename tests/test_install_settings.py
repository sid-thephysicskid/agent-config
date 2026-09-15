#!/usr/bin/env python3
"""settings.json merge, strip, and validation. Python 3.9, stdlib only."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import install_settings as S  # noqa: E402

HOOKS = "/home/u/.claude/hooks"


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "settings.json")

    def tearDown(self):
        self.dir.cleanup()

    def write(self, cfg, path=None):
        with open(path or self.path, "w") as f:
            json.dump(cfg, f)

    def read(self):
        with open(self.path) as f:
            return json.load(f)

    def commands(self, cfg=None):
        cfg = self.read() if cfg is None else cfg
        return [h.get("command", "") for event in cfg.get("hooks", {}).values()
                for e in event for h in e.get("hooks", [])]


class MergeTest(Base):
    def test_creates_the_file_and_is_idempotent(self):
        S.merge(self.path, HOOKS)
        first = self.read()
        self.assertEqual(len(self.commands(first)), len(S.WIRING))
        self.assertEqual(first["permissions"]["deny"], list(S.deny_rules(HOOKS)))
        S.merge(self.path, HOOKS)
        self.assertEqual(self.read(), first)
        self.assertTrue(S.check(self.path, HOOKS))

    def test_keeps_the_users_keys_hooks_and_deny_rules(self):
        self.write({"model": "opus", "permissions": {"allow": ["Bash(ls:*)"], "deny": ["Read(**/.env)"]},
                    "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
                        {"type": "command", "command": "python3 ~/mine/audit.py"},
                        {"type": "command", "command": "python3 ~/mine/wrap.py --after hooks/guard-files.py"}]}]}})
        S.merge(self.path, HOOKS)
        cfg = self.read()
        self.assertEqual(cfg["model"], "opus")
        self.assertEqual(cfg["permissions"]["allow"], ["Bash(ls:*)"])
        self.assertEqual(cfg["permissions"]["deny"].count("Read(**/.env)"), 1)
        self.assertIn("python3 ~/mine/audit.py", self.commands(cfg))
        self.assertIn("python3 ~/mine/wrap.py --after hooks/guard-files.py", self.commands(cfg))

    def test_replaces_every_older_spelling_of_our_hooks(self):
        old = [
            "if test -f ~/.claude/hooks/guard-bash.py; then exec python3 ~/.claude/hooks/guard-bash.py; fi; exit 0",
            ": onbelay-hook-v1:guard-bash.py; if test -f /x/guard-bash.py; then exec python3 /x/guard-bash.py; fi; exit 0",
            ": agent-config-hook-v1:gone.py; if test -f /x/gone.py; then exec python3 /x/gone.py; fi; exit 0",
            "python3 ~/.claude/hooks/check-docs.py",
        ]
        self.write({"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
            {"type": "command", "command": c} for c in old]}],
            "Stop": [{"hooks": [{"type": "command", "command": old[3]}]}]}})
        S.merge(self.path, HOOKS)
        cmds = self.commands()
        self.assertEqual(len(cmds), len(S.WIRING))
        self.assertNotIn("Stop", self.read()["hooks"])

    def test_the_hooks_deny_rule_follows_the_hook_dir(self):
        home = os.path.expanduser("~")
        self.assertEqual(S.deny_rules(home + "/.claude/hooks")[-1], "Write(~/.claude/hooks/**)")
        self.assertEqual(S.deny_rules("/srv/cc/hooks")[-1], "Write(//srv/cc/hooks/**)")
        S.merge(self.path, "/srv/cc/hooks")
        S.strip(self.path)
        self.assertEqual(os.listdir(self.dir.name), [])

    def test_updates_a_symlink_target_without_detaching_it(self):
        target = os.path.join(self.dir.name, "dots.json")
        self.write({"model": "opus"}, target)
        os.symlink(target, self.path)
        S.merge(self.path, HOOKS)
        self.assertTrue(os.path.islink(self.path))
        self.assertEqual(self.read()["model"], "opus")
        self.assertTrue(os.path.isfile(target + S._DENY_STATE_SUFFIX))

    def test_preserves_mode_and_ignores_a_planted_temp_symlink(self):
        self.write({"model": "opus"})
        os.chmod(self.path, 0o600)
        victim = os.path.join(self.dir.name, "victim")
        with open(victim, "w") as f:
            f.write("mine")
        os.symlink(victim, self.path + ".tmp")
        S.merge(self.path, HOOKS)
        self.assertEqual(os.stat(self.path).st_mode & 0o777, 0o600)
        with open(victim) as f:
            self.assertEqual(f.read(), "mine")

    def test_file_matcher_covers_mcp_file_actions(self):
        matcher = next(m for _e, m, script, _t in S.WIRING if script == "guard-files.py")
        for tool in ("mcp__filesystem__read_file", "mcp__files__move_file"):
            self.assertRegex(tool, "^(?:%s)$" % matcher)

    def test_prompt_hook_has_no_matcher_and_strips_out_of_a_users_entry(self):
        S.merge(self.path, HOOKS)
        self.assertNotIn("matcher", self.read()["hooks"]["UserPromptSubmit"][0])
        original = {"hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": "mine.sh"}]}]}}
        self.write(original)
        S.merge(self.path, HOOKS)
        S.merge(self.path, HOOKS)
        self.assertEqual(len(self.read()["hooks"]["UserPromptSubmit"]), 1)
        self.assertTrue(S.check(self.path, HOOKS))
        S.strip(self.path)
        self.assertEqual(self.read(), original)

    def test_check_rejects_a_hook_that_only_mentions_our_script(self):
        self.write({"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
            {"type": "command", "command": "# TODO wire guard-bash.py"}]}]}})
        self.assertFalse(S.check(self.path, HOOKS))


class StripTest(Base):
    def test_round_trip_restores_the_backup_bytes(self):
        original = '{"model":"opus","hooks":{"PreToolUse":[{"matcher":"Bash","hooks":[{"type":"command","command":"a.sh"}]}]}}'
        with open(self.path, "w") as f:
            f.write(original)
        with open(self.path + S.BACKUP_SUFFIX, "w") as f:
            f.write(original)
        S.merge(self.path, HOOKS)
        S.strip(self.path)
        with open(self.path) as f:
            self.assertEqual(f.read(), original)
        self.assertEqual(os.listdir(self.dir.name), ["settings.json"])

    def test_keeps_later_user_changes_and_their_own_matching_deny_rule(self):
        self.write({"permissions": {"deny": ["Bash(git reset --hard:*)"]}})
        S.merge(self.path, HOOKS)
        cfg = self.read()
        cfg["theme"] = "dark"
        self.write(cfg)
        S.strip(self.path)
        self.assertEqual(self.read(), {"permissions": {"deny": ["Bash(git reset --hard:*)"]}, "theme": "dark"})

    def test_a_file_we_created_is_removed(self):
        S.merge(self.path, HOOKS)
        S.strip(self.path)
        self.assertEqual(os.listdir(self.dir.name), [])

    def test_a_file_with_nothing_of_ours_is_not_rewritten(self):
        original = '{"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "python3 ~/mine/wrap.py --after hooks/guard-files.py"}]}]}}'
        with open(self.path, "w") as f:
            f.write(original)
        S.strip(self.path)
        with open(self.path) as f:
            self.assertEqual(f.read(), original)

    def test_missing_file_is_not_an_error(self):
        S.strip(self.path)


class ValidationTest(Base):
    def test_accepts_unknown_well_formed_events(self):
        self.write({"hooks": {"FutureEvent": [{"hooks": [{"type": "command", "command": "true"}]}]}})
        S.validate(self.path)

    def test_rejects_shapes_merge_would_guess_about(self):
        for cfg in (["not", "an", "object"], {"hooks": {"Stop": "x"}},
                    {"hooks": {"PreToolUse": [{"hooks": ["x"]}]}},
                    {"permissions": {"deny": "x"}}):
            self.write(cfg)
            with self.assertRaises(ValueError):
                S.validate(self.path)

    def test_rejects_a_symlinked_deny_ledger(self):
        self.write({})
        victim = os.path.join(self.dir.name, "victim")
        open(victim, "w").close()
        os.symlink(victim, self.path + S._DENY_STATE_SUFFIX)
        with self.assertRaisesRegex(ValueError, "not a regular file"):
            S.validate(self.path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
