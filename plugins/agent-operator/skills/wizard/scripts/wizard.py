#!/usr/bin/env python3
"""Execute a narrowly declarative, human-run credential setup plan."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import webbrowser
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit


class PlanError(ValueError):
    """The setup plan is outside the runner's narrow schema."""


NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
REPOSITORY_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
HOST_RE = re.compile(
    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)"
    r"(?:\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))*\Z"
)


def _object(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PlanError(f"{context} must be an object")
    return value


def _keys(
    value: dict[str, Any],
    *,
    required: set[str],
    optional: set[str],
    context: str,
) -> None:
    missing = required - value.keys()
    unknown = value.keys() - required - optional
    if missing:
        raise PlanError(f"{context} is missing: {', '.join(sorted(missing))}")
    if unknown:
        raise PlanError(f"{context} has unsupported fields: {', '.join(sorted(unknown))}")


def _text(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PlanError(f"{context} must be a non-empty string")
    return value.strip()


def _host(value: Any, context: str) -> str:
    host = _text(value, context).lower().rstrip(".")
    if not HOST_RE.fullmatch(host):
        raise PlanError(f"{context} must be an exact DNS hostname without wildcards")
    return host


def _url(value: Any, allowed_hosts: set[str], context: str) -> str:
    url = _text(value, context)
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise PlanError(f"{context} must be an HTTPS URL")
    try:
        port = parsed.port
    except ValueError as error:
        raise PlanError(f"{context} has an invalid port") from error
    if parsed.username or parsed.password or port not in (None, 443):
        raise PlanError(f"{context} cannot contain credentials or a nonstandard port")
    if parsed.hostname.lower().rstrip(".") not in allowed_hosts:
        raise PlanError(f"{context} hostname is not in allowed_hosts")
    return url


def _relative_env_path(value: Any) -> str:
    path = PurePosixPath(_text(value, "env_file"))
    if path.is_absolute() or ".." in path.parts or path.name == ".env.example":
        raise PlanError("env_file must be a relative path inside the current directory")
    return str(path)


def validate_plan(raw: Any) -> dict[str, Any]:
    plan = _object(raw, "plan")
    _keys(
        plan,
        required={"version", "title", "allowed_hosts", "stages"},
        optional={"env_file", "github_repository"},
        context="plan",
    )
    if plan["version"] != 1:
        raise PlanError("version must be 1")
    title = _text(plan["title"], "title")

    raw_hosts = plan["allowed_hosts"]
    if not isinstance(raw_hosts, list):
        raise PlanError("allowed_hosts must be a list")
    hosts = {_host(value, "allowed_hosts entry") for value in raw_hosts}
    if len(hosts) != len(raw_hosts):
        raise PlanError("allowed_hosts contains a duplicate")

    env_file = _relative_env_path(plan.get("env_file", ".env"))
    repository = plan.get("github_repository")
    if repository is not None:
        repository = _text(repository, "github_repository")
        if not REPOSITORY_RE.fullmatch(repository):
            raise PlanError("github_repository must have the form owner/repository")

    raw_stages = plan["stages"]
    if not isinstance(raw_stages, list) or not raw_stages:
        raise PlanError("stages must be a non-empty list")

    stages: list[dict[str, Any]] = []
    seen_destinations: set[tuple[str, str]] = set()
    needs_github = False
    for stage_index, raw_stage in enumerate(raw_stages, start=1):
        context = f"stage {stage_index}"
        stage = _object(raw_stage, context)
        _keys(
            stage,
            required={"title", "instructions"},
            optional={"url", "confirmation", "captures"},
            context=context,
        )
        instructions = stage["instructions"]
        if not isinstance(instructions, list) or not instructions:
            raise PlanError(f"{context}.instructions must be a non-empty list")
        clean_stage: dict[str, Any] = {
            "title": _text(stage["title"], f"{context}.title"),
            "instructions": [
                _text(item, f"{context}.instructions entry") for item in instructions
            ],
            "captures": [],
        }
        if "url" in stage:
            clean_stage["url"] = _url(stage["url"], hosts, f"{context}.url")
        if "confirmation" in stage:
            clean_stage["confirmation"] = _text(
                stage["confirmation"], f"{context}.confirmation"
            )

        captures = stage.get("captures", [])
        if not isinstance(captures, list):
            raise PlanError(f"{context}.captures must be a list")
        for capture_index, raw_capture in enumerate(captures, start=1):
            capture_context = f"{context}.capture {capture_index}"
            capture = _object(raw_capture, capture_context)
            _keys(
                capture,
                required={"name", "prompt", "secret", "destinations"},
                optional=set(),
                context=capture_context,
            )
            name = _text(capture["name"], f"{capture_context}.name")
            if not NAME_RE.fullmatch(name):
                raise PlanError(f"{capture_context}.name must be an environment-style name")
            if not isinstance(capture["secret"], bool):
                raise PlanError(f"{capture_context}.secret must be true or false")
            destinations = capture["destinations"]
            if not isinstance(destinations, list) or not destinations:
                raise PlanError(f"{capture_context}.destinations must be a non-empty list")

            clean_destinations: list[dict[str, str]] = []
            for destination_index, raw_destination in enumerate(destinations, start=1):
                destination_context = f"{capture_context}.destination {destination_index}"
                destination = _object(raw_destination, destination_context)
                _keys(
                    destination,
                    required={"type", "name"},
                    optional=set(),
                    context=destination_context,
                )
                destination_type = _text(
                    destination["type"], f"{destination_context}.type"
                )
                if destination_type not in {"env", "github-secret"}:
                    raise PlanError(
                        f"{destination_context}.type must be env or github-secret"
                    )
                destination_name = _text(
                    destination["name"], f"{destination_context}.name"
                )
                if not NAME_RE.fullmatch(destination_name):
                    raise PlanError(
                        f"{destination_context}.name must be an environment-style name"
                    )
                identity = (destination_type, destination_name)
                if identity in seen_destinations:
                    raise PlanError(
                        f"destination {destination_type}:{destination_name} is duplicated"
                    )
                seen_destinations.add(identity)
                needs_github = needs_github or destination_type == "github-secret"
                clean_destinations.append(
                    {"type": destination_type, "name": destination_name}
                )

            clean_stage["captures"].append(
                {
                    "name": name,
                    "prompt": _text(capture["prompt"], f"{capture_context}.prompt"),
                    "secret": capture["secret"],
                    "destinations": clean_destinations,
                }
            )
        stages.append(clean_stage)

    if needs_github and repository is None:
        raise PlanError("github_repository is required for github-secret destinations")
    return {
        "version": 1,
        "title": title,
        "allowed_hosts": sorted(hosts),
        "env_file": env_file,
        "github_repository": repository,
        "stages": stages,
    }


def load_plan(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PlanError(f"cannot read plan: {error}") from error
    return validate_plan(raw)


def _confirm(question: str) -> bool:
    return input(f"{question} Type yes to continue: ").strip().lower() == "yes"


def _destination_label(destination: dict[str, str], plan: dict[str, Any]) -> str:
    if destination["type"] == "env":
        return f"{plan['env_file']}:{destination['name']}"
    return f"GitHub {plan['github_repository']} secret {destination['name']}"


def print_summary(plan: dict[str, Any]) -> None:
    print(plan["title"])
    print("Allowed HTTPS hosts:")
    if not plan["allowed_hosts"]:
        print("  - none")
    for host in plan["allowed_hosts"]:
        print(f"  - {host}")
    print("Destinations:")
    destinations = [
        destination
        for stage in plan["stages"]
        for capture in stage["captures"]
        for destination in capture["destinations"]
    ]
    if not destinations:
        print("  - none (instructions only)")
    for destination in destinations:
        print(f"  - {_destination_label(destination, plan)}")


def _encode_dotenv(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace("$", "\\$")
        .replace("`", "\\`")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace('"', '\\"')
    )
    return f'"{escaped}"'


def _env_target(root: Path, relative_path: str) -> Path:
    target = root / relative_path
    if target.is_symlink():
        raise RuntimeError(f"refusing to write symbolic link: {relative_path}")
    resolved_root = root.resolve()
    resolved_target = target.resolve(strict=False)
    try:
        resolved_target.relative_to(resolved_root)
    except ValueError as error:
        raise RuntimeError("environment file resolves outside the current directory") from error
    if not target.parent.is_dir():
        raise RuntimeError(f"environment file parent does not exist: {target.parent}")
    return target


def _write_env(root: Path, relative_path: str, name: str, value: str) -> None:
    target = _env_target(root, relative_path)
    existing = ""
    if target.exists():
        if not target.is_file():
            raise RuntimeError(f"environment destination is not a file: {relative_path}")
        existing = target.read_text(encoding="utf-8")

    assignment = re.compile(rf"^(?:export\s+)?{re.escape(name)}\s*=.*$")
    output = [line for line in existing.splitlines() if not assignment.match(line)]
    output.append(f"{name}={_encode_dotenv(value)}")
    payload = "\n".join(output) + "\n"

    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target.parent,
            prefix=f".{target.name}.",
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            os.chmod(temporary_name, stat.S_IRUSR | stat.S_IWUSR)
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, target)
        os.chmod(target, stat.S_IRUSR | stat.S_IWUSR)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _set_github_secret(repository: str, name: str, value: str) -> None:
    if shutil.which("gh") is None:
        raise RuntimeError("GitHub CLI is required for a github-secret destination")
    result = subprocess.run(
        ["gh", "secret", "set", name, "--repo", repository],
        input=value,
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"GitHub CLI could not set secret {name}")


def run(plan: dict[str, Any], root: Path) -> int:
    print_summary(plan)
    needs_github = any(
        destination["type"] == "github-secret"
        for stage in plan["stages"]
        for capture in stage["captures"]
        for destination in capture["destinations"]
    )
    if needs_github and shutil.which("gh") is None:
        raise RuntimeError("install and authenticate GitHub CLI before running this plan")
    if not _confirm("Review the hosts and destinations above."):
        print("Cancelled. Nothing changed.")
        return 1

    for index, stage in enumerate(plan["stages"], start=1):
        print(f"\n[{index}/{len(plan['stages'])}] {stage['title']}")
        if "url" in stage:
            if _confirm(f"Open {stage['url']}?"):
                if not webbrowser.open(stage["url"]):
                    print(f"Open this URL manually: {stage['url']}")
            else:
                print(f"Open this URL manually when ready: {stage['url']}")
        for instruction in stage["instructions"]:
            print(f"  - {instruction}")
        if "confirmation" in stage and not _confirm(stage["confirmation"]):
            print("Cancelled before this stage changed anything.")
            return 1

        for capture in stage["captures"]:
            value = (
                getpass.getpass(f"{capture['prompt']}: ")
                if capture["secret"]
                else input(f"{capture['prompt']}: ")
            )
            if not value:
                raise RuntimeError(f"{capture['name']} cannot be empty")
            for destination in capture["destinations"]:
                label = _destination_label(destination, plan)
                if not _confirm(f"Write {capture['name']} to {label}?"):
                    print(f"Skipped {label}.")
                    continue
                if destination["type"] == "env":
                    _write_env(root, plan["env_file"], destination["name"], value)
                else:
                    _set_github_secret(
                        plan["github_repository"], destination["name"], value
                    )
                print(f"Wrote {label}.")
            del value

    print("\nSetup complete. The runner did not print captured values.")
    return 0


def main(argv: list[str] | None = None) -> int:
    os.umask(0o077)
    parser = argparse.ArgumentParser(
        description="Validate or run a declarative human credential setup plan."
    )
    parser.add_argument("plan", type=Path)
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate and summarize without opening URLs, prompting, or writing",
    )
    args = parser.parse_args(argv)
    try:
        plan = load_plan(args.plan)
        if args.check:
            print_summary(plan)
            print("Plan is valid. No URLs were opened and nothing was written.")
            return 0
        return run(plan, Path.cwd())
    except (PlanError, RuntimeError) as error:
        print(f"wizard: {error}", file=sys.stderr)
        return 2
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled. No captured value was printed.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
