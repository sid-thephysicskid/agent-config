#!/usr/bin/env python3
"""scripts/migrate-legacy.sh on small hand-built layouts. The full 0.3.1/0.4.2 installs are in install_test.sh."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIGRATE = ROOT / "scripts" / "migrate-legacy.sh"


class MigrateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.claude = self.home / ".claude"
        self.codex = self.home / ".codex"
        self.share = self.home / ".local" / "share"
        self.claude.mkdir()
        self.codex.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def payload(self, name, version):
        root = self.share / name / version
        (root / "skills" / "ship").mkdir(parents=True)
        (root / "hooks").mkdir()
        (root / "VERSION").write_text(version + "\n")
        return root

    def migrate(self, keep=""):
        return subprocess.run(["bash", str(MIGRATE), str(self.claude), str(self.codex), keep],
                              env=dict(os.environ, HOME=str(self.home)),
                              capture_output=True, text=True, check=True).stdout

    def test_strips_the_instruction_block_byte_for_byte(self):
        original = b"Mine.  \r\n\r\n"
        block = b"<!-- onbelay:start -->\r\n# On Belay\r\n<!-- onbelay:end -->"
        path = self.claude / "CLAUDE.md"
        path.write_bytes(original + block)
        Path(str(path) + ".before-onbelay").write_bytes(original)
        self.migrate()
        self.assertEqual(path.read_bytes(), original)
        self.assertFalse(Path(str(path) + ".before-onbelay").exists())

    def test_a_block_only_file_we_created_is_removed_but_a_symlinked_one_is_kept(self):
        (self.codex / "AGENTS.md").write_text("<!-- agent-config:start -->\nx\n<!-- agent-config:end -->")
        dots = self.home / "dots.md"
        dots.write_text("Mine.\n<!-- agent-config:start -->\nx\n<!-- agent-config:end -->")
        (self.claude / "CLAUDE.md").symlink_to(dots)
        self.migrate()
        self.assertFalse((self.codex / "AGENTS.md").exists())
        self.assertTrue((self.claude / "CLAUDE.md").is_symlink())
        self.assertEqual(dots.read_text(), "Mine.\n")

    def test_removes_only_old_link_shapes_and_restores_moved_skills(self):
        old = self.payload("onbelay", "0.4.2")
        dots = self.home / "dots"
        (dots / "mine").mkdir(parents=True)
        (self.claude / ".onbelay-origins").write_text(str(dots))  # no trailing newline
        skills = self.claude / "skills"
        skills.mkdir()
        (skills / "ship").symlink_to(old / "skills" / "ship")
        (skills / "mine").symlink_to(dots / "mine")
        backup = self.share / "onbelay" / "conflicts.json.d" / "abc"
        backup.mkdir(parents=True)
        (backup / "SKILL.md").write_text("theirs\n")
        (self.share / "onbelay" / "conflicts.json").write_text(json.dumps(
            [{"path": str(skills / "review"), "backup": str(backup)}]))
        self.migrate()
        self.assertEqual(sorted(os.listdir(skills)), ["mine", "review"])
        self.assertEqual((skills / "review" / "SKILL.md").read_text(), "theirs\n")
        self.assertFalse((self.share / "onbelay").exists())
        self.assertFalse((self.claude / ".onbelay-origins").exists())

    def test_keeps_the_current_payload_and_any_payload_a_user_link_still_uses(self):
        current = self.payload("agent-config", "0.5.0")
        used = self.payload("agent-config", "0.3.1")
        (used / "notes.md").write_text("x")
        (self.claude / "notes.md").symlink_to(used / "notes.md")
        (self.claude / "hooks").mkdir()
        (self.claude / "hooks" / "guard-bash.py").symlink_to(current / "hooks" / "guard-bash.py")
        out = self.migrate(keep=str(current))
        self.assertTrue(current.is_dir())
        self.assertTrue((self.claude / "hooks" / "guard-bash.py").is_symlink())
        self.assertTrue(used.is_dir())
        self.assertIn("still links into it", out)

    def test_renames_settings_state_to_the_current_spelling(self):
        (self.claude / "settings.json").write_text("{}")
        (self.claude / "settings.json.before-onbelay").write_text('{"model":"opus"}')
        (self.claude / "settings.json.onbelay-deny.json").write_text("[]")
        self.migrate()
        self.assertEqual(sorted(os.listdir(self.claude)), [
            "settings.json", "settings.json.agent-config-deny.json", "settings.json.before-agent-config"])

    def test_is_silent_on_a_clean_home(self):
        self.assertEqual(self.migrate(), "")
        self.assertEqual(sorted(os.listdir(self.home)), [".claude", ".codex"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
