#!/usr/bin/env python3
"""agent-config secret stores a value in .env or GitHub without echoing it or passing it in argv."""
import os
import shutil
import stat
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(ROOT, "bin", "agent-config.js")
VALUE = "s3cr3t-" + "value-9f8e7d"


class SecretCliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.env = os.path.join(self.dir, ".env")

    def tearDown(self):
        self.tmp.cleanup()

    def secret(self, *args, value=VALUE + "\n", path=None):
        result = subprocess.run(["node", CLI, "secret", *args], cwd=self.dir, input=value, text=True,
                                capture_output=True, env=dict(os.environ, PATH=path or os.environ["PATH"]))
        if value.strip():
            self.assertNotIn(value.strip(), result.stdout + result.stderr)
        return result

    def read(self, path=None):
        with open(path or self.env, "rb") as f:
            return f.read()

    def test_creates_the_file_0600(self):
        result = self.secret("API_KEY")
        self.assertEqual((result.returncode, result.stdout), (0, "wrote API_KEY to .env\n"))
        self.assertEqual(self.read(), b"API_KEY=" + VALUE.encode() + b"\n")
        self.assertEqual(stat.S_IMODE(os.stat(self.env).st_mode), 0o600)

    def test_replaces_in_place_and_keeps_every_other_byte(self):
        before = b"# mine\r\nexport API_KEY=old\nOTHER=1 # keep\n\xff raw\nAPI_KEY_2=x"
        with open(self.env, "wb") as f:
            f.write(before)
        os.chmod(self.env, 0o644)
        self.assertEqual(self.secret("API_KEY").returncode, 0)
        self.assertEqual(self.read(), before.replace(b"=old", b"=" + VALUE.encode()))
        self.assertEqual(stat.S_IMODE(os.stat(self.env).st_mode), 0o600)
        self.assertEqual(self.secret("NEW_KEY").returncode, 0)
        self.assertEqual(self.read(), before.replace(b"=old", b"=" + VALUE.encode())
                         + b"\nNEW_KEY=" + VALUE.encode() + b"\n")

    def test_quotes_values_a_parser_would_split(self):
        cases = {"a b": "'a b'", 'a"b $x #1': "'a\"b $x #1'", "it's #1": '"it\'s #1"',
                 'it\'s "$x"': '"it\'s \\"\\$x\\""'}
        for value, written in cases.items():
            with self.subTest(value):
                self.assertEqual(self.secret("K", "--env", "custom.env", value=value).returncode, 0)
                self.assertEqual(self.read(os.path.join(self.dir, "custom.env")).decode(), "K=%s\n" % written)

    def test_rejects_bad_names_and_empty_values_writing_nothing(self):
        for name in ("api_key", "1KEY", "KEY-X", "--env"):
            self.assertNotEqual(self.secret(name).returncode, 0, name)
        self.assertNotEqual(self.secret().returncode, 0)
        self.assertNotEqual(self.secret("API_KEY", value="\n").returncode, 0)
        self.assertEqual(os.listdir(self.dir), [])

    def test_warns_when_env_is_not_gitignored(self):
        subprocess.run(["git", "init", "-q", self.dir], check=True)
        self.assertIn("not gitignored", self.secret("API_KEY").stderr)
        with open(os.path.join(self.dir, ".gitignore"), "w") as f:
            f.write(".env\n")
        self.assertEqual(self.secret("API_KEY").stderr, "")

    def test_github_gets_the_value_on_stdin_only(self):
        bin_dir = os.path.join(self.dir, "bin")
        os.mkdir(bin_dir)
        gh = os.path.join(bin_dir, "gh")
        with open(gh, "w") as f:
            f.write('#!/bin/sh\nprintf "%%s\\n" "$@" > %s/argv\ncat > %s/stdin\n' % (self.dir, self.dir))
        os.chmod(gh, 0o755)
        result = self.secret("API_KEY", "--github", "me/repo", path=bin_dir + os.pathsep + os.environ["PATH"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.read(os.path.join(self.dir, "stdin")), VALUE.encode())
        self.assertEqual(self.read(os.path.join(self.dir, "argv")), b"secret\nset\nAPI_KEY\n--repo\nme/repo\n")
        self.assertFalse(os.path.exists(self.env))

    def test_github_without_gh_says_so(self):
        node_only = os.path.join(self.dir, "node-only")
        os.mkdir(node_only)
        os.symlink(shutil.which("node"), os.path.join(node_only, "node"))
        result = self.secret("API_KEY", "--github", path=node_only)
        self.assertEqual(result.returncode, 1)
        self.assertIn("gh is not installed", result.stderr)
        self.assertFalse(os.path.exists(self.env))


if __name__ == "__main__":
    unittest.main(verbosity=2)
