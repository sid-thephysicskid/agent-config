#!/usr/bin/env python3
"""Tests for the checks themselves.

    python3 -m unittest discover -s evals -p 'test_*.py' -v

A check that always returns green is worse than no check, so every check here
is fed a synthetic input it should reject. If a check is ever weakened into a
no-op, one of these fails. Standard library only, Python 3.9.

The em dash test builds the character with chr(0x2014) rather than writing it
literally, because the repo's global rules ban the character from any file
written on the user's behalf, including this one.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evals.harness import guard_checks, static_checks  # noqa: E402
from evals.harness.model import load_skills, parse_frontmatter  # noqa: E402

EM_DASH = chr(0x2014)


def write_skill(root, name, frontmatter, body, extra_files=None):
    directory = os.path.join(root, name)
    os.makedirs(directory, exist_ok=True)
    fm = "---\n" + "\n".join("%s: %s" % kv for kv in frontmatter.items()) + "\n---\n"
    with open(os.path.join(directory, "SKILL.md"), "w", encoding="utf-8") as fh:
        fh.write(fm + body)
    for fname, content in (extra_files or {}).items():
        path = os.path.join(directory, fname)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
    return directory


class TempSuite(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="eval-test-")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def load(self):
        return load_skills(self.root)


class TestFrontmatter(TempSuite):
    def test_parses_scalar_keys_and_skips_nested(self):
        fm, body = parse_frontmatter('---\nname: x\ndescription: "a b"\nmeta:\n  nested: 1\n---\nbody\n')
        self.assertEqual(fm["name"], "x")
        self.assertEqual(fm["description"], "a b")
        self.assertNotIn("nested", fm)
        self.assertEqual(body.strip(), "body")

    def test_name_mismatch_is_an_error(self):
        write_skill(self.root, "alpha", {"name": "beta", "description": "Use when x"}, "body")
        findings = static_checks.check_frontmatter(self.load())
        self.assertTrue(any("does not match directory" in f.message for f in findings))

    def test_missing_description_is_an_error(self):
        write_skill(self.root, "alpha", {"name": "alpha"}, "body")
        findings = static_checks.check_frontmatter(self.load())
        self.assertTrue(any("no `description`" in f.message for f in findings))

    def test_oversized_description_is_an_error(self):
        write_skill(self.root, "alpha", {"name": "alpha", "description": "x" * 1200}, "body")
        findings = static_checks.check_frontmatter(self.load())
        self.assertTrue(any(f.severity == "error" and "over the" in f.message for f in findings))

    def test_healthy_frontmatter_is_silent(self):
        write_skill(self.root, "alpha", {"name": "alpha", "description": "Use when the user says alpha"}, "body")
        self.assertEqual(static_checks.check_frontmatter(self.load()), [])


class TestHouseStyle(TempSuite):
    def test_em_dash_is_caught(self):
        write_skill(self.root, "alpha", {"name": "alpha", "description": "Use when x"}, "a %s b" % EM_DASH)
        findings = static_checks.check_em_dash(self.load())
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "error")

    def test_clean_file_is_silent(self):
        write_skill(self.root, "alpha", {"name": "alpha", "description": "Use when x"}, "a, b; c.")
        self.assertEqual(static_checks.check_em_dash(self.load()), [])


class TestLinks(TempSuite):
    def test_broken_relative_link_is_caught(self):
        write_skill(self.root, "alpha", {"name": "alpha", "description": "d"}, "see [x](MISSING.md)")
        findings = static_checks.check_internal_links(self.load())
        self.assertTrue(any("broken link" in f.message for f in findings))

    def test_resolving_link_is_silent(self):
        write_skill(
            self.root, "alpha", {"name": "alpha", "description": "d"}, "see [x](NOTES.md)", {"NOTES.md": "hi"}
        )
        self.assertEqual(static_checks.check_internal_links(self.load()), [])

    def test_external_links_are_ignored(self):
        write_skill(self.root, "alpha", {"name": "alpha", "description": "d"}, "see [x](https://example.com/a.md)")
        self.assertEqual(static_checks.check_internal_links(self.load()), [])


class TestReferences(TempSuite):
    def test_reference_to_missing_skill_is_an_error(self):
        write_skill(self.root, "alpha", {"name": "alpha", "description": "d"}, "hand off to `/nowhere`")
        findings = static_checks.check_skill_references(self.load())
        self.assertTrue(any("no such skill exists" in f.message for f in findings))

    def test_paths_are_not_mistaken_for_skill_references(self):
        write_skill(self.root, "alpha", {"name": "alpha", "description": "d"}, "hit `/api/health` after deploy")
        findings = static_checks.check_skill_references(self.load())
        self.assertFalse(any("no such skill" in f.message for f in findings))

    def test_router_found_by_description_not_name(self):
        write_skill(self.root, "front-door", {"name": "front-door", "description": "Router and orientation"}, "x")
        router = static_checks.find_router(self.load())
        self.assertIsNotNone(router)
        self.assertEqual(router.name, "front-door")

    def _write_new_project_loop(self, missing=None):
        edges = {
            "navigate": ("prototype",),
            "prototype": ("architect",),
            "to-spec": ("breakdown",),
            "breakdown": ("tdd",),
            "architect": ("tdd",),
            "tdd": (),
        }
        for source, targets in edges.items():
            body = "\n".join(
                "hand off to `/%s`" % target
                for target in targets
                if (source, target) != missing)
            write_skill(
                self.root,
                source,
                {"name": source, "description": "Use when %s" % source},
                body,
            )

    def test_new_project_loop_reports_a_missing_handoff(self):
        self._write_new_project_loop(missing=("architect", "tdd"))
        findings = static_checks.check_orchestration_handoffs(self.load())
        self.assertTrue(any(
            f.skill == "architect" and "tdd" in f.message
            for f in findings))

    def test_reference_anywhere_counts(self):
        self._write_new_project_loop(missing=("architect", "tdd"))
        write_skill(
            self.root,
            "architect",
            {"name": "architect", "description": "Use when architect"},
            "Implementation continues with `/tdd`.",
        )
        self.assertEqual(
            static_checks.check_orchestration_handoffs(self.load()), [])

    def test_complete_new_project_loop_is_silent(self):
        self._write_new_project_loop()
        self.assertEqual(
            static_checks.check_orchestration_handoffs(self.load()), [])


class TestInvocationParity(TempSuite):
    """Both directions and the clean case, because a check that only ever
    passes is worth nothing and a check that only ever fails is worse."""

    YAML_OPEN = 'interface:\n  display_name: "A"\n  short_description: "a"\n'
    YAML_CLOSED = YAML_OPEN + "policy:\n  allow_implicit_invocation: false\n"

    def _one(self, frontmatter, yaml_text):
        extra = {"agents/openai.yaml": yaml_text} if yaml_text is not None else None
        write_skill(self.root, "alpha", frontmatter, "x", extra_files=extra)
        return static_checks.check_invocation_parity(self.load())

    def test_claude_only_is_caught(self):
        f = self._one(
            {"name": "alpha", "description": "d", "disable-model-invocation": "true"},
            self.YAML_OPEN)
        self.assertTrue(any("still implicitly invocable for Codex" in x.message for x in f))

    def test_codex_only_is_caught(self):
        f = self._one({"name": "alpha", "description": "d"}, self.YAML_CLOSED)
        self.assertTrue(any("still model-invocable for Claude Code" in x.message for x in f))

    def test_missing_yaml_is_caught(self):
        f = self._one({"name": "alpha", "description": "d"}, None)
        self.assertTrue(any("no agents/openai.yaml" in x.message for x in f))

    def test_both_user_invoked_is_silent(self):
        f = self._one(
            {"name": "alpha", "description": "d", "disable-model-invocation": "true"},
            self.YAML_CLOSED)
        self.assertEqual(f, [])

    def test_both_model_invocable_is_silent(self):
        f = self._one({"name": "alpha", "description": "d"}, self.YAML_OPEN)
        self.assertEqual(f, [])


class TestSize(TempSuite):
    def test_large_file_is_flagged(self):
        write_skill(self.root, "alpha", {"name": "alpha", "description": "d"}, "word " * 3200)
        findings = static_checks.check_size_budget(self.load())
        # Reported, never fatal. Length is a judgement call: a skill covering
        # eleven sequential gates is legitimately long, and nobody has measured
        # a point at which an agent stops following a longer instruction file.
        # Failing a build on a word count would be false precision.
        self.assertEqual(findings[0].severity, "warn")
        self.assertEqual(findings[0].basis, "heuristic")

    def test_size_never_fails_a_build(self):
        write_skill(self.root, "alpha", {"name": "alpha", "description": "d"}, "word " * 99000)
        findings = static_checks.check_size_budget(self.load())
        self.assertTrue(findings)
        self.assertNotIn("error", [f.severity for f in findings])

    def test_small_file_is_silent(self):
        write_skill(self.root, "alpha", {"name": "alpha", "description": "d"}, "word " * 50)
        self.assertEqual(static_checks.check_size_budget(self.load()), [])


class TestDuplication(TempSuite):
    PHRASE = (
        "stage the paths you created by name and never use the blanket form because "
        "it stages things the user did not intend to stage at all"
    )

    def test_cross_skill_repeat_is_caught(self):
        write_skill(self.root, "alpha", {"name": "alpha", "description": "d"}, self.PHRASE)
        write_skill(self.root, "beta", {"name": "beta", "description": "d"}, self.PHRASE)
        findings = static_checks.check_duplication(self.load())
        self.assertTrue(any("also present in" in f.message for f in findings))

    def test_intra_file_repeat_is_caught(self):
        write_skill(self.root, "alpha", {"name": "alpha", "description": "d"}, self.PHRASE + "\n\nfiller\n\n" + self.PHRASE)
        findings = static_checks.check_duplication(self.load())
        self.assertTrue(any("more than once inside its own" in f.message for f in findings))

    def test_distinct_prose_is_silent(self):
        write_skill(self.root, "alpha", {"name": "alpha", "description": "d"}, "one two three four five six seven")
        write_skill(self.root, "beta", {"name": "beta", "description": "d"}, "eight nine ten eleven twelve thirteen")
        self.assertEqual(static_checks.check_duplication(self.load()), [])


class TestCommandExtraction(TempSuite):
    def test_commands_are_found_and_prose_is_skipped(self):
        body = "```\ngit status --short\nbranch:    <name>\nnot done:  nothing\n```\n"
        write_skill(self.root, "alpha", {"name": "alpha", "description": "d"}, body)
        skill = self.load()[0]
        commands, skipped = guard_checks.extract_commands(skill)
        self.assertEqual([c for _, c in commands], ["git status --short"])
        self.assertEqual(skipped, 2)

    def test_continuations_are_joined(self):
        body = "```\ngh pr create --title \"x\" \\\n  --body \"y\"\n```\n"
        write_skill(self.root, "alpha", {"name": "alpha", "description": "d"}, body)
        commands, _ = guard_checks.extract_commands(self.load()[0])
        self.assertEqual(len(commands), 1)
        self.assertIn("--body", commands[0][1])

    def test_assignment_wrapped_command_is_recognised(self):
        body = "```\nBASE=$(git rev-parse HEAD)\n```\n"
        write_skill(self.root, "alpha", {"name": "alpha", "description": "d"}, body)
        commands, _ = guard_checks.extract_commands(self.load()[0])
        self.assertEqual(len(commands), 1)


class TestReferencedPaths(TempSuite):
    def test_missing_shipped_script_is_reported(self):
        write_skill(self.root, "alpha", {"name": "alpha", "description": "d"}, "run `scripts/nope.sh` yourself")
        findings = static_checks.check_referenced_paths(self.load())
        self.assertTrue(any("does not exist under the skill directory" in f.message for f in findings))

    def test_present_shipped_script_is_silent(self):
        write_skill(
            self.root,
            "alpha",
            {"name": "alpha", "description": "d"},
            "run `scripts/yes.sh` yourself",
            {os.path.join("scripts", "yes.sh"): "#!/bin/sh\n"},
        )
        self.assertEqual(static_checks.check_referenced_paths(self.load()), [])

    def test_project_files_are_not_flagged(self):
        write_skill(self.root, "alpha", {"name": "alpha", "description": "d"}, "write `.github/dependabot.yml`")
        self.assertEqual(static_checks.check_referenced_paths(self.load()), [])


class TestTriggerCollisions(TempSuite):
    def test_heavy_overlap_is_reported(self):
        shared = "Use when the user mentions widget frobnicator turbine flange gasket calibration"
        write_skill(self.root, "alpha", {"name": "alpha", "description": shared}, "x")
        write_skill(self.root, "beta", {"name": "beta", "description": shared}, "x")
        findings = static_checks.check_trigger_collisions(self.load())
        self.assertTrue(any("share" in f.message for f in findings))

    def test_distinct_triggers_are_silent(self):
        write_skill(self.root, "alpha", {"name": "alpha", "description": "Use when the user mentions widgets"}, "x")
        write_skill(self.root, "beta", {"name": "beta", "description": "Use when the user mentions turbines"}, "x")
        self.assertEqual(static_checks.check_trigger_collisions(self.load()), [])


class TestGuardFixtures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures = guard_checks.Fixtures()
        cls.fixtures.build()

    @classmethod
    def tearDownClass(cls):
        cls.fixtures.cleanup()

    def setUp(self):
        if self.fixtures.error:
            self.skipTest("git fixtures unavailable: %s" % self.fixtures.error)

    def test_fixtures_are_on_the_expected_branches(self):
        self.assertEqual(sorted(self.fixtures.dirs), ["feature", "protected", "virgin"])

    def test_a_wrong_expectation_is_reported(self):
        claim = {
            "id": "synthetic",
            "skill": "ship",
            "file": "AGENTS.md",
            "quote": "",
            "command": "git commit -m \"x\"",
            "branch": "protected",
            "expect": "allow",
            "kind": "claim",
            "why": "synthetic",
        }
        findings = guard_checks.check_guard_claims(self.fixtures, [claim])
        self.assertTrue(any("says the guard would allow" in f.message for f in findings))

    def test_a_stale_quote_is_reported(self):
        claim = {
            "id": "synthetic",
            "skill": "ship",
            "file": "AGENTS.md",
            "quote": "this sentence is definitely not in AGENTS dot md anywhere at all",
            "command": "git status",
            "branch": "feature",
            "expect": "allow",
            "kind": "claim",
        }
        findings = guard_checks.check_guard_claims(self.fixtures, [claim])
        self.assertTrue(any("no longer in" in f.message for f in findings))

    def test_a_correct_claim_is_silent(self):
        claim = {
            "id": "synthetic",
            "skill": "ship",
            "file": "AGENTS.md",
            "quote": "",
            "command": "git commit -m \"x\"",
            "branch": "protected",
            "expect": "block",
            "kind": "claim",
        }
        self.assertEqual(guard_checks.check_guard_claims(self.fixtures, [claim]), [])

    def test_a_blocked_prescribed_command_is_reported(self):
        root = tempfile.mkdtemp(prefix="eval-cmd-")
        try:
            write_skill(
                root,
                "alpha",
                {"name": "alpha", "description": "d"},
                "```\ngit push --force\n```\n",
            )
            findings = guard_checks.check_prescribed_commands(load_skills(root), self.fixtures)
            self.assertTrue(any("the guard blocks" in f.message for f in findings))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_an_allowed_prescribed_command_is_silent(self):
        root = tempfile.mkdtemp(prefix="eval-cmd-")
        try:
            write_skill(
                root,
                "alpha",
                {"name": "alpha", "description": "d"},
                "```\ngit status --short\n```\n",
            )
            self.assertEqual(guard_checks.check_prescribed_commands(load_skills(root), self.fixtures), [])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_shipped_claims_file_is_well_formed(self):
        for claim in guard_checks.load_claims():
            for key in ("id", "skill", "file", "command", "branch", "expect"):
                self.assertIn(key, claim, "claim %r missing %s" % (claim.get("id"), key))
            self.assertIn(claim["branch"], self.fixtures.dirs)
            self.assertIn(claim["expect"], ("block", "allow"))



if __name__ == "__main__":
    unittest.main(verbosity=1)
