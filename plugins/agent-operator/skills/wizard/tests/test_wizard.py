from __future__ import annotations

import importlib.util
import io
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

RUNNER = Path(__file__).parents[1] / "scripts" / "wizard.py"
SPEC = importlib.util.spec_from_file_location("wizard_runner", RUNNER)
assert SPEC and SPEC.loader
wizard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(wizard)


class WizardTests(unittest.TestCase):
    def test_validate_rejects_generated_operations(self) -> None:
        plan = {
            "version": 1,
            "title": "Dummy",
            "allowed_hosts": ["example.com"],
            "stages": [
                {
                    "title": "Bad stage",
                    "instructions": ["Test only"],
                    "command": "curl https://example.com",
                }
            ],
        }
        with self.assertRaisesRegex(wizard.PlanError, "unsupported fields"):
            wizard.validate_plan(plan)

    def test_env_write_is_atomic_private_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / ".env"
            target.write_text("KEEP=one\nDUMMY=old\n", encoding="utf-8")
            os.chmod(target, 0o644)

            wizard._write_env(root, ".env", "DUMMY", "dummy secret\nline two")

            self.assertEqual(
                target.read_text(encoding="utf-8"),
                'KEEP=one\nDUMMY="dummy secret\\nline two"\n',
            )
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)

    def test_env_write_refuses_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outside = root / "outside"
            outside.write_text("DUMMY=old\n", encoding="utf-8")
            (root / ".env").symlink_to(outside)
            with self.assertRaisesRegex(RuntimeError, "symbolic link"):
                wizard._write_env(root, ".env", "DUMMY", "dummy")

    def test_env_write_keeps_shell_substitution_inert(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            value = "$(touch bad) `touch worse` $HOME"
            wizard._write_env(root, ".env", "DUMMY", value)

            result = subprocess.run(
                ["/bin/sh", "-c", '. ./.env && printf "%s" "$DUMMY"'],
                cwd=root,
                text=True,
                capture_output=True,
                check=True,
            )

            self.assertEqual(result.stdout, value)
            self.assertFalse((root / "bad").exists())
            self.assertFalse((root / "worse").exists())

    def test_example_plan_is_valid(self) -> None:
        example = Path(__file__).parents[1] / "assets" / "plan.example.json"
        plan = wizard.load_plan(example)
        self.assertEqual(plan["allowed_hosts"], ["example.com"])
        self.assertEqual(plan["github_repository"], "owner/repository")

    def test_run_uses_hidden_input_and_never_prints_value(self) -> None:
        plan = wizard.validate_plan(
            {
                "version": 1,
                "title": "Dummy local setup",
                "allowed_hosts": ["example.com"],
                "env_file": ".env",
                "stages": [
                    {
                        "title": "Capture dummy",
                        "instructions": ["Dummy data only"],
                        "captures": [
                            {
                                "name": "DUMMY_KEY",
                                "prompt": "Dummy key",
                                "secret": True,
                                "destinations": [
                                    {"type": "env", "name": "DUMMY_KEY"}
                                ],
                            }
                        ],
                    }
                ],
            }
        )
        with tempfile.TemporaryDirectory() as temporary:
            output = io.StringIO()
            with (
                mock.patch.object(
                    wizard.getpass, "getpass", return_value="dummy-only-value"
                ) as hidden_input,
                mock.patch.object(wizard, "_confirm", return_value=True),
                mock.patch("sys.stdout", output),
            ):
                self.assertEqual(wizard.run(plan, Path(temporary)), 0)
            hidden_input.assert_called_once()
            self.assertNotIn("dummy-only-value", output.getvalue())
            self.assertEqual(
                stat.S_IMODE((Path(temporary) / ".env").stat().st_mode), 0o600
            )

    def test_github_secret_flows_through_stdin(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake_gh = root / "gh"
            stdin_capture = root / "stdin"
            args_capture = root / "args"
            fake_gh.write_text(
                "#!/bin/sh\nprintf '%s\\n' \"$@\" > \"$DUMMY_ARGS_CAPTURE\"\n"
                "/bin/cat > \"$DUMMY_STDIN_CAPTURE\"\n",
                encoding="utf-8",
            )
            os.chmod(fake_gh, 0o700)
            environment = {
                "PATH": str(root),
                "DUMMY_ARGS_CAPTURE": str(args_capture),
                "DUMMY_STDIN_CAPTURE": str(stdin_capture),
            }
            with mock.patch.dict(os.environ, environment):
                wizard._set_github_secret(
                    "owner/repository", "DUMMY_KEY", "dummy-only-value"
                )
            self.assertEqual(stdin_capture.read_text(encoding="utf-8"), "dummy-only-value")
            arguments = args_capture.read_text(encoding="utf-8")
            self.assertEqual(
                arguments,
                "secret\nset\nDUMMY_KEY\n--repo\nowner/repository\n",
            )
            self.assertNotIn("dummy-only-value", arguments)


if __name__ == "__main__":
    unittest.main()
