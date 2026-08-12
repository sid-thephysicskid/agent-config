#!/usr/bin/env python3
"""Black-box tests for the cross-agent project instruction initializer."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "agent-init"


class AgentInitTests(unittest.TestCase):
    def run_init(self, directory: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(SCRIPT), *args],
            cwd=directory,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_creates_one_canonical_file_and_a_relative_claude_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            result = self.run_init(project)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((project / "AGENTS.md").is_file())
            self.assertTrue((project / "CLAUDE.md").is_symlink())
            self.assertEqual(os.readlink(project / "CLAUDE.md"), "AGENTS.md")
            self.assertEqual(
                (project / "CLAUDE.md").read_bytes(),
                (project / "AGENTS.md").read_bytes(),
            )
            self.assertEqual(list(project.glob(".AGENTS.md.*")), [])

    def test_preserves_existing_agents_file_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            original = b"# My project\n\nRun `make test`.\n"
            (project / "AGENTS.md").write_bytes(original)

            first = self.run_init(project)
            second = self.run_init(project)

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual((project / "AGENTS.md").read_bytes(), original)
            self.assertEqual(os.readlink(project / "CLAUDE.md"), "AGENTS.md")

    def test_repairs_our_broken_claude_link_by_creating_agents(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            os.symlink("AGENTS.md", project / "CLAUDE.md")

            result = self.run_init(project)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((project / "AGENTS.md").is_file())
            self.assertEqual(os.readlink(project / "CLAUDE.md"), "AGENTS.md")

    def test_uses_git_root_when_run_from_a_subdirectory(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw) / "project"
            nested = project / "src" / "feature"
            nested.mkdir(parents=True)
            subprocess.run(["git", "init", "-q", str(project)], check=True)

            result = self.run_init(nested)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((project / "AGENTS.md").is_file())
            self.assertTrue((project / "CLAUDE.md").is_symlink())
            self.assertFalse((nested / "AGENTS.md").exists())

    def test_check_reports_missing_files_without_mutating(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)

            result = self.run_init(project, "--check")

            self.assertEqual(result.returncode, 1)
            self.assertIn("AGENTS.md is missing", result.stderr)
            self.assertFalse((project / "AGENTS.md").exists())
            self.assertFalse((project / "CLAUDE.md").exists())

    def test_inaccessible_directory_never_falls_back_to_current_directory(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            sandbox = Path(raw)
            current = sandbox / "current"
            inaccessible = sandbox / "inaccessible"
            current.mkdir()
            inaccessible.mkdir()
            inaccessible.chmod(0)
            try:
                result = subprocess.run(
                    [str(SCRIPT), str(inaccessible)],
                    cwd=current,
                    text=True,
                    capture_output=True,
                    check=False,
                )
            finally:
                inaccessible.chmod(0o700)

            self.assertEqual(result.returncode, 1)
            self.assertIn("cannot access directory", result.stderr)
            self.assertFalse((current / "AGENTS.md").exists())
            self.assertFalse((current / "CLAUDE.md").exists())

    def test_conflicting_claude_file_refuses_before_creating_agents(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            claude = project / "CLAUDE.md"
            claude.write_text("# Existing Claude instructions\n", encoding="utf-8")

            result = self.run_init(project)

            self.assertEqual(result.returncode, 1)
            self.assertIn("will not replace it", result.stderr)
            self.assertEqual(claude.read_text(encoding="utf-8"), "# Existing Claude instructions\n")
            self.assertFalse((project / "AGENTS.md").exists())

    def test_conflicting_claude_symlink_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            (project / "other.md").write_text("other\n", encoding="utf-8")
            os.symlink("other.md", project / "CLAUDE.md")

            result = self.run_init(project)

            self.assertEqual(result.returncode, 1)
            self.assertEqual(os.readlink(project / "CLAUDE.md"), "other.md")
            self.assertFalse((project / "AGENTS.md").exists())

    def test_absolute_claude_symlink_is_rejected_as_nonportable(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            agents = project / "AGENTS.md"
            agents.write_text("instructions\n", encoding="utf-8")
            os.symlink(str(agents), project / "CLAUDE.md")

            result = self.run_init(project)

            self.assertEqual(result.returncode, 1)
            self.assertEqual(os.readlink(project / "CLAUDE.md"), str(agents))

    def test_agents_symlink_is_rejected_as_noncanonical(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            source = project / "instructions.md"
            source.write_text("instructions\n", encoding="utf-8")
            os.symlink("instructions.md", project / "AGENTS.md")

            result = self.run_init(project)

            self.assertEqual(result.returncode, 1)
            self.assertIn("real canonical file", result.stderr)
            self.assertFalse((project / "CLAUDE.md").exists())

    def test_concurrent_agents_file_is_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            sandbox = Path(raw)
            bundle = sandbox / "bundle"
            project = sandbox / "project"
            (bundle / "scripts").mkdir(parents=True)
            (bundle / "templates").mkdir()
            project.mkdir()
            copied = bundle / "scripts" / "agent-init"
            shutil.copy2(SCRIPT, copied)
            fifo = bundle / "templates" / "AGENTS.project.md"
            os.mkfifo(fifo)

            process = subprocess.Popen(
                [str(copied), str(project)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            # The initializer is blocked reading the FIFO after inspecting the
            # final paths. Occupy AGENTS.md before allowing publication.
            deadline = time.monotonic() + 5
            while not list(project.glob(".AGENTS.md.*")):
                if process.poll() is not None or time.monotonic() >= deadline:
                    self.fail("initializer did not reach its prepared-file stage")
                time.sleep(0.01)
            (project / "AGENTS.md").write_text("user instructions\n", encoding="utf-8")
            with fifo.open("w", encoding="utf-8") as stream:
                stream.write("template instructions\n")
            _, stderr = process.communicate(timeout=5)

            self.assertEqual(process.returncode, 1, stderr)
            self.assertEqual(
                (project / "AGENTS.md").read_text(encoding="utf-8"),
                "user instructions\n",
            )
            self.assertFalse((project / "CLAUDE.md").exists())

    def test_concurrent_claude_file_rolls_back_only_our_agents_file(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            sandbox = Path(raw)
            bundle = sandbox / "bundle"
            project = sandbox / "project"
            (bundle / "scripts").mkdir(parents=True)
            (bundle / "templates").mkdir()
            project.mkdir()
            copied = bundle / "scripts" / "agent-init"
            shutil.copy2(SCRIPT, copied)
            fifo = bundle / "templates" / "AGENTS.project.md"
            os.mkfifo(fifo)
            process = subprocess.Popen(
                [str(copied), str(project)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            deadline = time.monotonic() + 5
            while not list(project.glob(".AGENTS.md.*")):
                if process.poll() is not None or time.monotonic() >= deadline:
                    self.fail("initializer did not reach its prepared-file stage")
                time.sleep(0.01)
            (project / "CLAUDE.md").write_text("user instructions\n", encoding="utf-8")
            with fifo.open("w", encoding="utf-8") as stream:
                stream.write("template instructions\n")
            _, stderr = process.communicate(timeout=5)

            self.assertEqual(process.returncode, 1, stderr)
            self.assertFalse((project / "AGENTS.md").exists())
            self.assertEqual(
                (project / "CLAUDE.md").read_text(encoding="utf-8"),
                "user instructions\n",
            )
            self.assertEqual(list(project.glob(".AGENTS.md.*")), [])


if __name__ == "__main__":
    unittest.main()
