#!/usr/bin/env python3
"""Does the credential gate detect the formats it claims to?

audit.py calls itself "the gate that stops a credential reaching a public
clone". It matched seven issuer shapes and missed every current one: the
OpenAI project format, Stripe, Google, npm, Slack app tokens, GitLab, and the
AWS SECRET (only the key id was matched, so the half that actually grants
access could be committed while the gate reported clean).

A pattern list nobody exercises drifts as issuers change formats, so this runs
it against fabricated samples of each shape.

Two deliberate constraints:

  - Every sample is built by CONCATENATION. A literal would make this file trip
    the scanner, and exempting it would put a hole in the one file that must not
    have one. test_this_file_does_not_trip_the_scanner keeps that honest.
  - SECRETS is read with ast rather than imported, because audit.py is a script
    with no __main__ guard: importing it runs the whole audit and calls
    sys.exit.

Python 3.9, stdlib only, no network.
"""
import ast
import os
import re
import unittest

AUDIT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audit.py")
HERE = os.path.abspath(__file__)

Q = '"'
AT = "@"
DASH5 = "-" * 5


def load_secrets():
    """The SECRETS table, without executing the module around it."""
    tree = ast.parse(open(AUDIT, encoding="utf-8").read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                getattr(t, "id", None) == "SECRETS" for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError("audit.py has no SECRETS table")


def url(scheme, secret):
    return scheme + "://u:" + secret + AT + "db.example.com/app"


MUST_DETECT = [
    ("OpenAI project key", "sk-proj-" + "a" * 40),
    ("OpenAI-style key", "sk-" + "b" * 40),
    ("Stripe secret key", "sk_live_" + "c" * 30),
    ("Stripe restricted key", "rk_live_" + "d" * 30),
    ("Anthropic key", "sk-ant-" + "e" * 30),
    ("GitHub token", "ghp_" + "f" * 30),
    ("GitLab token", "glpat-" + "g" * 25),
    ("AWS access key id", "AKIA" + "H" * 16),
    ("AWS secret access key", "aws_secret_access_key = " + Q + "A" * 40 + Q),
    ("Google API key", "AIza" + "i" * 35),
    ("Google OAuth token", "ya29" + "." + "j" * 30),
    ("npm token", "npm_" + "k" * 36),
    ("Slack token", "xoxb-" + "1" * 20),
    ("Slack app token", "xapp-1-" + "m" * 20),
    ("DigitalOcean token", "dop_v1_" + "a" * 64),
    ("Hugging Face token", "hf_" + "o" * 34),
    ("private key block", DASH5 + "BEGIN RSA PRIVATE KEY" + DASH5),
    ("database URL with a password", url("postgres", "s3cretvalue")),
    ("database URL with a password", url("mysql", "s3cretvalue")),
    ("database URL with a password", url("mongodb+srv", "s3cretvalue")),
    ("database URL with a password", url("redis", "s3cretvalue")),
]

# A false positive here blocks a merge, so the nearest legitimate shapes are
# pinned too. Without them, the fix for a miss is to widen a pattern until it
# matches prose.
MUST_NOT_DETECT = [
    "rotate the credentials and keys regularly",
    "OPENAI_API_KEY=sk-your-key-here",
    "postgres://localhost:5432/app",
    "postgres://user" + AT + "db.example.com/app",
    "the sk-prefixed keys are documented above",
    "mongodb://127.0.0.1:27017/test",
]


class AuditPatternTest(unittest.TestCase):
    def setUp(self):
        self.patterns = [(re.compile(p), label) for p, label in load_secrets()]

    def hits(self, text):
        return [label for rx, label in self.patterns if rx.search(text)]

    def test_every_claimed_format_is_detected(self):
        for label, sample in MUST_DETECT:
            with self.subTest(label):
                found = self.hits(sample)
                self.assertTrue(found, "%s went undetected" % label)
                self.assertIn(label, found)

    def test_ordinary_text_is_not_a_credential(self):
        for sample in MUST_NOT_DETECT:
            with self.subTest(sample[:40]):
                self.assertEqual(self.hits(sample), [])

    def test_this_file_does_not_trip_the_scanner(self):
        """Keeps the samples concatenated. A literal here fails the audit."""
        self.assertEqual(self.hits(open(HERE, encoding="utf-8").read()), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
