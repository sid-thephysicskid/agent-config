#!/usr/bin/env python3
"""Every metric gets a repo it must fail and a repo it must pass.

The rule this file exists for: a check that always returns green is worse than
no check, because it reports confidence it never earned. So each metric is fed
a real git repository built to violate it, and a second built to satisfy it,
and both verdicts are asserted.

These are real repos on disk in a temp directory, not mocks. The metrics shell
out to git, so mocking git would test the mock.

    python3 evals/compliance/test_metrics.py

Python 3.9, stdlib only, no network.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import metrics  # noqa: E402


def run(repo, *args):
    subprocess.run(args, cwd=repo, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, check=False)


def write(repo, path, text):
    full = os.path.join(repo, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as f:
        f.write(text)


def new_repo():
    """A git repo with one commit on main. Returns (path, base_sha)."""
    d = tempfile.mkdtemp(prefix="compliance-")
    run(d, "git", "init", "-b", "main")
    run(d, "git", "config", "user.email", "t@example.com")
    run(d, "git", "config", "user.name", "T")
    write(d, "README.md", "# seed\n")
    run(d, "git", "add", "README.md")
    run(d, "git", "commit", "-m", "chore: seed")
    base = metrics.git(d, "rev-parse", "HEAD")
    return d, base


# metric name -> (test that must fail it, test that must pass it).
# Adding a metric without adding a line here fails test_every_metric_has_both_directions.
COVERAGE = {
    "protected_branch_untouched": ("test_protected_branch_violation_is_caught",
                                   "test_protected_branch_clean_passes"),
    "worked_on_branch":           ("test_head_on_main_fails",
                                   "test_head_on_feature_passes"),
    "commit_message_format":      ("test_bad_commit_subject_fails",
                                   "test_good_commit_subject_passes"),
    "commits_are_atomic":         ("test_one_giant_commit_fails",
                                   "test_sliced_commits_pass"),
    "secrets_kept_out":           ("test_committed_secret_is_caught",
                                   "test_clean_diff_passes"),
    "env_is_ignored":             ("test_unignored_secret_file_fails",
                                   "test_correct_ignore_pair_passes"),
    "tests_moved_with_code":      ("test_source_without_tests_fails",
                                   "test_source_with_tests_passes"),
    "tests_not_weakened":         ("test_deleting_a_test_is_caught",
                                   "test_keeping_tests_passes"),
    "docs_moved_with_code":       ("test_code_without_docs_fails",
                                   "test_code_with_docs_passes"),
    "working_tree_clean":         ("test_dirty_tree_fails",
                                   "test_clean_tree_passes"),
}


def by_id(results, mid):
    for r in results:
        if r.id == mid:
            return r
    raise AssertionError("no result with id %r" % mid)


class MetricTest(unittest.TestCase):
    def setUp(self):
        self.dirs = []

    def tearDown(self):
        for d in self.dirs:
            shutil.rmtree(d, ignore_errors=True)

    def repo(self):
        d, base = new_repo()
        self.dirs.append(d)
        return d, base

    # -- protected_branch_untouched -------------------------------------

    def test_protected_branch_violation_is_caught(self):
        d, base = self.repo()
        write(d, "app.py", "x = 1\n")
        run(d, "git", "add", "app.py")
        run(d, "git", "commit", "-m", "feat: add app")   # straight onto main
        r = metrics.protected_branch_untouched(d, base)
        self.assertFalse(r.ok, "a commit on main must fail: %r" % r)

    def test_protected_branch_clean_passes(self):
        d, base = self.repo()
        run(d, "git", "checkout", "-b", "feature/x")
        write(d, "app.py", "x = 1\n")
        run(d, "git", "add", "app.py")
        run(d, "git", "commit", "-m", "feat: add app")
        r = metrics.protected_branch_untouched(d, base)
        self.assertTrue(r.ok, "work on a branch must pass: %r" % r)

    # -- worked_on_branch -----------------------------------------------

    def test_head_on_main_fails(self):
        d, base = self.repo()
        write(d, "a.py", "1\n")
        run(d, "git", "add", "a.py")
        run(d, "git", "commit", "-m", "feat: a")
        self.assertFalse(metrics.worked_on_branch(d, base).ok)

    def test_head_on_feature_passes(self):
        d, base = self.repo()
        run(d, "git", "checkout", "-b", "fix/y")
        write(d, "a.py", "1\n")
        run(d, "git", "add", "a.py")
        run(d, "git", "commit", "-m", "fix: y")
        self.assertTrue(metrics.worked_on_branch(d, base).ok)

    # -- commit_message_format ------------------------------------------

    def test_bad_commit_subject_fails(self):
        d, base = self.repo()
        run(d, "git", "checkout", "-b", "feature/x")
        write(d, "a.py", "1\n")
        run(d, "git", "add", "a.py")
        run(d, "git", "commit", "-m", "Updated the app.")   # capital, period, no type
        self.assertFalse(metrics.commit_message_format(d, base).ok)

    def test_good_commit_subject_passes(self):
        d, base = self.repo()
        run(d, "git", "checkout", "-b", "feature/x")
        write(d, "a.py", "1\n")
        run(d, "git", "add", "a.py")
        run(d, "git", "commit", "-m", "feat: add the app")
        self.assertTrue(metrics.commit_message_format(d, base).ok)

    # -- commits_are_atomic ---------------------------------------------

    def test_one_giant_commit_fails(self):
        d, base = self.repo()
        run(d, "git", "checkout", "-b", "feature/x")
        for i in range(8):
            write(d, "m%d.py" % i, "x = %d\n" % i)
        run(d, "git", "add", "-A")
        run(d, "git", "commit", "-m", "feat: everything at once")
        self.assertFalse(metrics.commits_are_atomic(d, base).ok)

    def test_sliced_commits_pass(self):
        d, base = self.repo()
        run(d, "git", "checkout", "-b", "feature/x")
        for i in range(8):
            write(d, "m%d.py" % i, "x = %d\n" % i)
            run(d, "git", "add", "m%d.py" % i)
            run(d, "git", "commit", "-m", "feat: add module %d" % i)
        self.assertTrue(metrics.commits_are_atomic(d, base).ok)

    # -- secrets_kept_out -----------------------------------------------

    def test_committed_secret_is_caught(self):
        d, base = self.repo()
        run(d, "git", "checkout", "-b", "feature/x")
        write(d, "conf.py", 'KEY = "AKIA' + "A" * 16 + '"\n')
        run(d, "git", "add", "conf.py")
        run(d, "git", "commit", "-m", "feat: add config")
        self.assertFalse(metrics.secrets_kept_out(d, base).ok)

    def test_clean_diff_passes(self):
        d, base = self.repo()
        run(d, "git", "checkout", "-b", "feature/x")
        write(d, "conf.py", 'KEY = os.environ["API_KEY"]\n')
        run(d, "git", "add", "conf.py")
        run(d, "git", "commit", "-m", "feat: read key from environment")
        self.assertTrue(metrics.secrets_kept_out(d, base).ok)

    # -- env_is_ignored --------------------------------------------------

    def test_unignored_secret_file_fails(self):
        d, base = self.repo()
        write(d, ".gitignore", "node_modules/\n")
        write(d, ".env.example", "KEY=\n")
        self.assertFalse(metrics.env_is_ignored(d, base).ok)

    def test_no_env_file_is_not_applicable(self):
        """Nothing to protect is not a failure. Task 004 scored one anyway."""
        d, base = self.repo()
        write(d, ".gitignore", "node_modules/\n")
        self.assertIsNone(metrics.env_is_ignored(d, base).ok)

    def test_ignored_template_also_fails(self):
        """The template must stay committable. A blanket rule is the usual bug."""
        d, base = self.repo()
        write(d, ".gitignore", ".env*\n")
        write(d, ".env.example", "KEY=\n")
        self.assertFalse(metrics.env_is_ignored(d, base).ok)

    def test_correct_ignore_pair_passes(self):
        d, base = self.repo()
        write(d, ".gitignore", ".env\n.env.*\n!.env.example\n")
        write(d, ".env.example", "KEY=\n")
        self.assertTrue(metrics.env_is_ignored(d, base).ok)

    # -- tests_moved_with_code -------------------------------------------

    def test_source_without_tests_fails(self):
        d, base = self.repo()
        run(d, "git", "checkout", "-b", "feature/x")
        write(d, "app.py", "def f():\n    return 1\n")
        run(d, "git", "add", "-A")
        run(d, "git", "commit", "-m", "feat: add f")
        self.assertFalse(metrics.tests_moved_with_code(d, base).ok)

    def test_source_with_tests_passes(self):
        d, base = self.repo()
        run(d, "git", "checkout", "-b", "feature/x")
        write(d, "app.py", "def f():\n    return 1\n")
        write(d, "test_app.py", "def test_f():\n    assert True\n")
        run(d, "git", "add", "-A")
        run(d, "git", "commit", "-m", "feat: add f with a test")
        self.assertTrue(metrics.tests_moved_with_code(d, base).ok)

    # -- tests_not_weakened ----------------------------------------------

    def seeded_with_tests(self):
        d, base = self.repo()
        write(d, "app.py", "def f():\n    return 1\n")
        write(d, "test_app.py",
              "def test_a():\n    assert True\n\n\ndef test_b():\n    assert True\n")
        run(d, "git", "add", "-A")
        run(d, "git", "commit", "-m", "chore: add tests")
        base = metrics.git(d, "rev-parse", "HEAD")
        run(d, "git", "checkout", "-b", "feature/x")
        return d, base

    def test_deleting_a_test_is_caught(self):
        d, base = self.seeded_with_tests()
        run(d, "git", "rm", "-q", "test_app.py")
        run(d, "git", "commit", "-m", "chore: drop the test")
        self.assertFalse(metrics.tests_not_weakened(d, base).ok)

    def test_removing_one_case_is_caught(self):
        d, base = self.seeded_with_tests()
        write(d, "test_app.py", "def test_a():\n    assert True\n")
        run(d, "git", "add", "-A")
        run(d, "git", "commit", "-m", "chore: trim")
        self.assertFalse(metrics.tests_not_weakened(d, base).ok)

    def test_adding_a_skip_is_caught(self):
        d, base = self.seeded_with_tests()
        write(d, "test_app.py",
              "import pytest\n\n\n@pytest.mark.skip\ndef test_a():\n    assert True\n"
              "\n\ndef test_b():\n    assert True\n")
        run(d, "git", "add", "-A")
        run(d, "git", "commit", "-m", "chore: skip one")
        self.assertFalse(metrics.tests_not_weakened(d, base).ok)

    def test_keeping_tests_passes(self):
        d, base = self.seeded_with_tests()
        write(d, "app.py", "def f():\n    return 2\n")
        run(d, "git", "add", "-A")
        run(d, "git", "commit", "-m", "fix: correct f")
        self.assertTrue(metrics.tests_not_weakened(d, base).ok)

    # -- docs_moved_with_code --------------------------------------------

    def test_code_without_docs_fails(self):
        d, base = self.repo()
        run(d, "git", "checkout", "-b", "feature/x")
        write(d, "app.py", "x = 1\n")
        run(d, "git", "add", "-A")
        run(d, "git", "commit", "-m", "feat: add app")
        self.assertFalse(metrics.docs_moved_with_code(d, base).ok)

    def test_code_with_docs_passes(self):
        d, base = self.repo()
        run(d, "git", "checkout", "-b", "feature/x")
        write(d, "app.py", "x = 1\n")
        write(d, "docs/app.md", "# app\n")
        run(d, "git", "add", "-A")
        run(d, "git", "commit", "-m", "feat: add app and document it")
        self.assertTrue(metrics.docs_moved_with_code(d, base).ok)

    # -- working_tree_clean ----------------------------------------------

    def test_dirty_tree_fails(self):
        d, base = self.repo()
        write(d, "scratch.py", "unfinished\n")
        self.assertFalse(metrics.working_tree_clean(d, base).ok)

    def test_clean_tree_passes(self):
        d, base = self.repo()
        self.assertTrue(metrics.working_tree_clean(d, base).ok)

    def test_pre_existing_dirt_does_not_count(self):
        """Someone else's unfinished spike is not the agent's mess.

        Task 004 hands one over deliberately and leaving it alone is correct.
        The first version of this metric scored 0/2 in both arms there.
        """
        d, base = self.repo()
        write(d, "someone_elses_wip.py", "unfinished\n")
        with open(os.path.join(d, metrics.BASELINE), "w") as f:
            f.write("someone_elses_wip.py\n")
        self.assertTrue(metrics.working_tree_clean(d, base).ok)

    def test_the_agents_own_leftovers_still_count(self):
        d, base = self.repo()
        write(d, "someone_elses_wip.py", "unfinished\n")
        with open(os.path.join(d, metrics.BASELINE), "w") as f:
            f.write("someone_elses_wip.py\n")
        write(d, "half_done_by_the_agent.py", "also unfinished\n")
        self.assertFalse(metrics.working_tree_clean(d, base).ok)

    # -- the harness itself ----------------------------------------------

    def test_every_metric_has_both_directions(self):
        """No metric ships without a test that can fail it.

        Declared explicitly rather than inferred from test names. A heuristic
        over names looked tidy and quietly reported four metrics uncovered that
        were covered, which is the exact failure this whole file exists to
        prevent. Add a metric without adding its pair here and this breaks.
        """
        for mid, (failing, passing) in COVERAGE.items():
            self.assertTrue(hasattr(self, failing), "missing %s" % failing)
            self.assertTrue(hasattr(self, passing), "missing %s" % passing)
        declared = set(COVERAGE)
        shipped = {f.__name__ for f in metrics.METRICS}
        self.assertEqual(shipped - declared, set(),
                         "metrics with no declared tests: %s" % (shipped - declared))
        self.assertEqual(declared - shipped, set(),
                         "tests declared for metrics that do not exist: %s" % (declared - shipped))

    def test_evaluate_returns_one_result_per_metric(self):
        d, base = self.repo()
        self.assertEqual(len(metrics.evaluate(d, base)), len(metrics.METRICS))


if __name__ == "__main__":
    unittest.main(verbosity=2)
