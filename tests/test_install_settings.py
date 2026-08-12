#!/usr/bin/env python3
"""The settings merge, tested directly instead of through a 40s bash suite.

    python3 tests/test_install_settings.py

This logic lived inside install.sh as a heredoc, so the only way to exercise it
was to run a real install into a fake HOME. Every case below took roughly two
seconds that way and takes roughly a millisecond now.

The property that matters most: **settings.json belongs to the user.** They
keep their model, their theme, their own hooks and their own deny rules, and a
strip must put them back exactly where they were.

Python 3.9, stdlib only, no network.
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import install_settings as S  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.unlink(self.path)

    def tearDown(self):
        for p in (self.path, self.path + ".tmp",
                  self.path + S._DENY_STATE_SUFFIX):
            if os.path.exists(p):
                os.unlink(p)

    def write(self, cfg):
        with open(self.path, "w") as f:
            json.dump(cfg, f)

    def read(self):
        with open(self.path) as f:
            return json.load(f)

    def commands(self, cfg, event):
        return [h.get("command", "")
                for e in cfg.get("hooks", {}).get(event, [])
                for h in e.get("hooks", [])]


class MergeTest(Base):
    def test_creates_the_file_when_absent(self):
        S.merge(self.path)
        cfg = self.read()
        for event in ("PreToolUse", "Stop", "SessionStart"):
            want = sum(1 for e, _m, _s, _t in S.WIRING if e == event)
            self.assertEqual(len(self.commands(cfg, event)), want, event)

    def test_is_idempotent(self):
        # Running install twice must not run the guard twice per tool call.
        S.merge(self.path)
        first = self.read()
        for _ in range(3):
            S.merge(self.path)
        self.assertEqual(self.read(), first)

    def test_keeps_the_users_own_keys(self):
        self.write({"model": "opus", "theme": "dark",
                    "permissions": {"allow": ["Bash(ls:*)"]}})
        S.merge(self.path)
        cfg = self.read()
        self.assertEqual(cfg["model"], "opus")
        self.assertEqual(cfg["theme"], "dark")
        self.assertEqual(cfg["permissions"]["allow"], ["Bash(ls:*)"])

    def test_keeps_a_users_own_hook_on_the_same_event(self):
        self.write({"hooks": {"PreToolUse": [
            {"matcher": "Bash", "hooks": [
                {"type": "command", "command": "python3 ~/mine/audit.py"}]}]}})
        S.merge(self.path)
        self.assertIn("python3 ~/mine/audit.py",
                      self.commands(self.read(), "PreToolUse"))

    def test_does_not_eat_a_hook_that_merely_mentions_our_path(self):
        # A substring match on the path removed this permanently. It runs the
        # user's wrapper, not our script.
        theirs = "python3 ~/mine/wrap.py --after hooks/guard-files.py"
        self.write({"hooks": {"PreToolUse": [
            {"matcher": "Bash",
             "hooks": [{"type": "command", "command": theirs}]}]}})
        S.merge(self.path)
        self.assertIn(theirs, self.commands(self.read(), "PreToolUse"))

    def test_replaces_an_older_version_of_our_own_hook(self):
        stale = "if test -f ~/.claude/hooks/guard-bash.py; then exec python3 ~/.claude/hooks/guard-bash.py; fi"
        self.write({"hooks": {"PreToolUse": [
            {"matcher": "Bash",
             "hooks": [{"type": "command", "command": stale}]}]}})
        S.merge(self.path)
        cmds = self.commands(self.read(), "PreToolUse")
        self.assertNotIn(stale, cmds)
        self.assertEqual(sum(1 for c in cmds if "guard-bash.py" in c), 1)

    def test_adds_the_deny_rules(self):
        S.merge(self.path)
        self.assertEqual(self.read()["permissions"]["deny"], list(S.DENY))

    def test_does_not_duplicate_a_deny_rule_the_user_already_had(self):
        self.write({"permissions": {"deny": ["Read(**/.env)", "Bash(mine:*)"]}})
        S.merge(self.path)
        deny = self.read()["permissions"]["deny"]
        self.assertEqual(deny.count("Read(**/.env)"), 1)
        self.assertIn("Bash(mine:*)", deny)

    def test_strip_preserves_a_matching_deny_rule_the_user_already_had(self):
        inherited = "Bash(git reset --hard:*)"
        self.write({"permissions": {"deny": [inherited, "Bash(mine:*)"]}})
        S.merge(self.path)
        S.strip(self.path)
        self.assertEqual(self.read()["permissions"]["deny"],
                         [inherited, "Bash(mine:*)"])

    def test_preserves_private_file_permissions(self):
        self.write({"model": "opus"})
        os.chmod(self.path, 0o600)
        S.merge(self.path)
        self.assertEqual(os.stat(self.path).st_mode & 0o777, 0o600)

    def test_does_not_follow_a_predictable_temp_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "settings.json")
            victim = os.path.join(directory, "victim.txt")
            with open(victim, "w") as fh:
                fh.write("mine")
            os.symlink(victim, path + ".tmp")
            S.merge(path)
            with open(victim) as fh:
                self.assertEqual(fh.read(), "mine")
            self.assertFalse(os.path.islink(path))
            self.assertTrue(os.path.islink(path + ".tmp"))


class StripTest(Base):
    def test_round_trip_leaves_the_file_as_it_was(self):
        original = {"model": "opus",
                    "permissions": {"deny": ["Bash(mine:*)"]},
                    "hooks": {"PreToolUse": [
                        {"matcher": "Bash", "hooks": [
                            {"type": "command", "command": "python3 ~/mine/a.py"}]}]}}
        self.write(original)
        S.merge(self.path)
        S.strip(self.path)
        self.assertEqual(self.read(), original)

    def test_leaves_nothing_of_ours_behind(self):
        S.merge(self.path)
        S.strip(self.path)
        cfg = self.read()
        self.assertNotIn("hooks", cfg)
        self.assertNotIn("permissions", cfg)
        self.assertFalse(os.path.exists(self.path + S._DENY_STATE_SUFFIX))

    def test_keeps_a_deny_rule_the_user_wrote(self):
        self.write({"permissions": {"deny": ["Bash(theirs:*)"]}})
        S.merge(self.path)
        S.strip(self.path)
        self.assertEqual(self.read()["permissions"]["deny"], ["Bash(theirs:*)"])

    def test_missing_file_is_not_an_error(self):
        S.strip(self.path)          # must not raise


class WiringTest(Base):
    def test_file_matcher_covers_mcp_file_actions(self):
        matcher = next(m for event, m, script, _timeout in S.WIRING
                       if event == "PreToolUse" and script == "guard-files.py")
        for tool in ("mcp__filesystem__read_file",
                     "mcp__workspace__write_file",
                     "mcp__files__move_file"):
            self.assertRegex(tool, "^(?:%s)$" % matcher)

    def test_every_wired_script_is_recognised_as_ours(self):
        # The property the three hand-copied regexes used to have to share: a
        # script added to WIRING without being matched by runs_ours would be
        # appended on every install, forever.
        for _event, _matcher, script, _timeout in S.WIRING:
            self.assertTrue(S.runs_ours(S._cmd(script)), script)

    def test_a_hook_we_no_longer_ship_is_pruned(self):
        # A script dropped from WIRING used to stay wired forever on any
        # machine that had installed it, pointing at a file that no longer
        # exists. `test -f` made that silent instead of fatal.
        self.write({"hooks": {"Stop": [{"hooks": [
            {"type": "command", "command": S._cmd("gone.py"), "timeout": 5}
        ]}]}})
        S.merge(self.path)
        rendered = json.dumps(self.read())
        self.assertNotIn("gone.py", rendered)
        self.assertNotIn("Stop", self.read()["hooks"])

    def test_pruning_never_touches_a_hook_that_is_not_ours(self):
        self.write({"hooks": {"Stop": [{"hooks": [
            {"type": "command", "command": "python3 ~/mine/x.py"}
        ]}]}})
        S.merge(self.path)
        cmds = [h["command"] for e in self.read()["hooks"]["Stop"]
                for h in e["hooks"]]
        self.assertTrue(any("mine/x.py" in c for c in cmds), cmds)

    def test_every_wired_script_survives_its_own_event(self):
        # The general form: nothing in WIRING may displace anything else.
        S.merge(self.path)
        cfg = self.read()
        for event, _matcher, script, _t in S.WIRING:
            cmds = [h["command"] for e in cfg["hooks"][event]
                    for h in e["hooks"]]
            self.assertTrue(any(script in c for c in cmds),
                            "%s missing from %s" % (script, event))

    def test_a_command_naming_no_script_is_not_ours(self):
        for cmd in ("python3 ~/mine/thing.py", "echo hooks/guard-bash.py",
                    "cat ~/.claude/hooks/guard-bash.py.bak"):
            self.assertFalse(S.runs_ours(cmd), cmd)


class ValidationTest(Base):
    def test_accepts_unknown_well_formed_hook_events(self):
        self.write({"hooks": {"FutureEvent": [
            {"hooks": [{"type": "command", "command": "true"}]}]}})
        S.validate(self.path)

    def test_rejects_a_malformed_event_other_than_pre_tool_use(self):
        self.write({"hooks": {"Stop": "not-a-list"}})
        with self.assertRaisesRegex(ValueError, "hooks.Stop is not a list"):
            S.validate(self.path)

    def test_rejects_malformed_permissions_used_by_merge(self):
        self.write({"permissions": {"deny": "not-a-list"}})
        with self.assertRaisesRegex(ValueError, "permissions.deny is not a list"):
            S.validate(self.path)

    def test_rejects_a_symlinked_managed_deny_state(self):
        self.write({})
        victim = self.path + ".victim"
        with open(victim, "w") as fh:
            fh.write("mine")
        state = self.path + S._DENY_STATE_SUFFIX
        os.symlink(victim, state)
        try:
            with self.assertRaisesRegex(ValueError, "not a regular file"):
                S.validate(self.path)
        finally:
            os.unlink(state)
            os.unlink(victim)


if __name__ == "__main__":
    unittest.main(verbosity=2)
