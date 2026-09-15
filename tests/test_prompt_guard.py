#!/usr/bin/env python3
"""hooks/guard-prompt.py refuses prompts carrying a credential and passes everything else.

Fake keys are assembled at runtime so tests/audit.py finds no secret literal here.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(ROOT, "hooks", "guard-prompt.py")


def fake(prefix, n, suffix="", alphabet="Ab3xQ9"):
    return prefix + (alphabet * (n // len(alphabet) + 1))[:n] + suffix


POSITIVES = {
    "Anthropic API key": fake("sk-" + "ant-api03-", 93, "AA"),
    "Anthropic admin key": fake("sk-" + "ant-admin01-", 93, "AA"),
    "OpenAI API key": fake("sk-" + "proj-", 74, fake("T3Blbk" + "FJ", 74)),
    "OpenAI service key": fake("sk-" + "svcacct-", 58, fake("T3Blbk" + "FJ", 58)),
    "GitHub token": fake("gh" + "p_", 36),
    "GitHub fine-grained token": fake("github" + "_pat_", 82),
    "AWS access key": fake("AK" + "IA", 16, alphabet="ABCD2345"),
    "Stripe secret key": fake("sk" + "_live_", 24),
    "Stripe restricted key": fake("rk" + "_prod_", 24),
    "Slack bot token": "xo" + "xb-1234567890-1234567890-" + fake("", 24),
    "Slack user token": "xo" + "xp-1234567890-1234567890-1234567890-" + fake("", 32),
    "npm token": fake("np" + "m_", 36),
    "private key": "-----BEGIN OPENSSH " + "PRIVATE KEY-----\n" + fake("b3BlbnNzaC1rZXk", 60) + "\n",
}

NEGATIVES = {
    "mention of the prefix": "why does my sk-ant key get rejected by the API?",
    "git SHA": "revert 3f9c2a1b7e4d5f6a8b9c0d1e2f3a4b5c6d7e8f90 please",
    "UUID": "row 123e4567-e89b-12d3-a456-426614174000 is missing",
    "base64 image": "data:image/png;base64," + "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk" * 200,
    "bare GitHub prefix": "tokens start with gh" + "p_ right?",
    "Stripe test key": fake("sk" + "_test_", 24),
    "markdown code block": "```python\n" + "def f(x):\n    return hashlib.sha256(x).hexdigest()\n" * 2000 + "```",
    "hello": "hello",
    "AWS doc example": "AK" + "IAIOSFODNN7EXAMPLE",
    "Stripe placeholder": "sk" + "_live_" + "x" * 12,
    "GitHub placeholder": "gh" + "p_" + "x" * 36,
    "bare PEM header": "-----BEGIN RSA " + "PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----",
    "Firebase web config": fake("AI" + "za", 35),
}


def run(stdin, home):
    return subprocess.run([sys.executable, HOOK], input=stdin, capture_output=True, text=True,
                          env=dict(os.environ, HOME=home, PYTHONDONTWRITEBYTECODE="1"))


class PromptGuardTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.home.cleanup()

    def prompt(self, text):
        return run(json.dumps({"hook_event_name": "UserPromptSubmit", "prompt": text}), self.home.name)

    def test_each_credential_shape_is_refused(self):
        for label, key in POSITIVES.items():
            with self.subTest(label):
                result = self.prompt("here is my key: %s thanks" % key)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("rotate", result.stderr)
                self.assertIn("agent-config secret NAME", result.stderr)
                self.assertNotIn(key.strip(), result.stderr)

    def test_ordinary_prompts_pass(self):
        for label, text in NEGATIVES.items():
            with self.subTest(label):
                result = self.prompt(text)
                self.assertEqual((result.returncode, result.stderr), (0, ""))

    def test_malformed_payloads_fail_open_and_log_without_the_payload(self):
        for stdin in ("not json " + POSITIVES["GitHub token"], "[1]", ""):
            self.assertEqual(run(stdin, self.home.name).returncode, 0)
        with open(os.path.join(self.home.name, ".claude", "guard-failopen.log")) as log:
            text = log.read()
        self.assertNotIn(POSITIVES["GitHub token"], text)

    def test_the_fail_open_log_follows_claude_config_dir(self):
        config = os.path.join(self.home.name, "cc")
        subprocess.run([sys.executable, HOOK], input="[1]", capture_output=True, text=True,
                       env=dict(os.environ, HOME=self.home.name, CLAUDE_CONFIG_DIR=config))
        self.assertTrue(os.path.exists(os.path.join(config, "guard-failopen.log")))
        self.assertFalse(os.path.exists(os.path.join(self.home.name, ".claude")))

    def test_a_200kb_prompt_is_judged_in_under_50ms(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("guard_prompt", HOOK)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        text = ("lorem ipsum sk-ant gh" + "p_ AIza 0123456789abcdef " * 8)[:1000] * 200
        start = time.perf_counter()
        self.assertFalse(any(pattern.search(text) for _kind, pattern in module.KINDS))
        self.assertLess(time.perf_counter() - start, 0.05)


if __name__ == "__main__":
    unittest.main(verbosity=2)
