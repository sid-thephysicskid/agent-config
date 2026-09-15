#!/usr/bin/env python3
"""Merge the guard hooks into Codex or Cursor hooks.json without taking it over.

    install_hooks_json.py merge codex|cursor <path> <repo>
    install_hooks_json.py check codex|cursor <path> <repo>
    install_hooks_json.py strip <path>
    install_hooks_json.py validate <path>

Python 3.9, stdlib only.
"""
import json
import os
import re
import shlex
import shutil
import sys
import tempfile

DESCRIPTION = "PreToolUse guardrails from agent-config"
LEGACY_DESCRIPTIONS = {
    "PreToolUse guardrails from onbelay",
    "Guardrails shared with Claude Code via agent-config/hooks",
    "Lifecycle hooks shared with Claude Code via agent-config/hooks",
}
LEGACY_SCRIPTS = {"guard-codex.py"}
HOSTS = {
    "codex": (
        ("PreToolUse", ".*", "guard-codex.py", 5, "Checking guardrails..."),
        ("UserPromptSubmit", None, "guard-prompt.py", 5, "Checking the prompt for keys..."),
    ),
    "cursor": (
        ("preToolUse", "^(Shell|Read|Write|Delete|MCP:.*)$", "guard-cursor.py", 5, None),
        ("beforeSubmitPrompt", None, "guard-prompt.py", 5, None),
    ),
}
BACKUP_SUFFIX = ".before-agent-config"
_COMMAND_TAG = "agent-config-hook-v1"
# onbelay-hook-v1 is the 0.4.x spelling of the same marker.
_OUR_COMMAND = re.compile(
    r"^: (?:agent-config|onbelay)-hook-v1:([\w.-]+); if test -f (.+); "
    r"then exec python3 \2; fi; exit [01]$")
_LEGACY_COMMAND = re.compile(
    r"^if test -f '([^']+)/hooks/([\w.-]+)'; then exec python3 "
    r"'\1/hooks/\2'; fi; exit 0$")


def _command(repo, script, missing=0):
    path = shlex.quote("%s/hooks/%s" % (repo.rstrip("/"), script))
    return ": %s:%s; if test -f %s; then exec python3 %s; fi; exit %d" % (
        _COMMAND_TAG, script, path, path, missing)


def _legacy_command(repo, script):
    path = "%s/hooks/%s" % (repo.rstrip("/"), script)
    return "if test -f '%s'; then exec python3 '%s'; fi; exit 0" % (path, path)


def _entry(host, repo, matcher, script, timeout, status):
    # Cursor reads exit 0 with no output as a deny, so a missing hook exits 1, which it allows.
    hook = {"type": "command", "command": _command(repo, script, host == "cursor"), "timeout": timeout}
    if host == "codex":
        hook["statusMessage"] = status
        hook = {"hooks": [hook]}
    if matcher is not None:
        hook["matcher"] = matcher
    return hook


def our_script(command):
    found = _OUR_COMMAND.match(str(command).strip())
    return found.group(1) if found else None


def _owned(handler, legacy):
    command = str(handler.get("command", "")).strip()
    if our_script(command):
        return True
    old = _LEGACY_COMMAND.match(command)
    # Untagged commands are only ours inside a file an old release wrote.
    return bool(legacy and old and old.group(2) in LEGACY_SCRIPTS)


def _target(path):
    return os.path.realpath(path) if os.path.islink(path) else path


def _load(path):
    if not os.path.exists(_target(path)):
        return {}, False
    with open(_target(path)) as f:
        cfg = json.load(f)
    if not isinstance(cfg, dict) or not isinstance(cfg.get("hooks", {}), dict):
        raise ValueError("hooks.json is not a JSON object with a hooks object")
    for event, groups in cfg.get("hooks", {}).items():
        if not isinstance(groups, list) or not all(
                isinstance(g, dict) and isinstance(g.get("hooks", []), list)
                and all(isinstance(h, dict) for h in g.get("hooks", []))
                for g in groups):
            raise ValueError("hooks.json hooks.%s is malformed" % event)
    return cfg, True


def _save(cfg, path):
    path = _target(path)
    rendered = json.dumps(cfg, indent=2) + "\n"
    mode = None
    if os.path.exists(path):
        with open(path) as f:
            if f.read() == rendered:
                return
        mode = os.stat(path).st_mode & 0o777
    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(path) + ".", dir=os.path.dirname(path) or ".")
    try:
        if mode is not None:
            os.fchmod(fd, mode)
        with os.fdopen(fd, "w") as f:
            fd = -1
            f.write(rendered)
        os.replace(tmp, path)
        tmp = None
    finally:
        if fd >= 0:
            os.close(fd)
        if tmp is not None:
            os.unlink(tmp)


def _remove_ours(cfg):
    """Returns True if anything was removed."""
    legacy = cfg.get("description") in LEGACY_DESCRIPTIONS
    changed = False
    events = cfg.get("hooks", {})
    for event, groups in list(events.items()):
        # A Codex group nests its handlers; a Cursor entry is its own handler.
        before = sum(len(g.get("hooks", [g])) for g in groups)
        for group in groups:
            if "hooks" in group:
                group["hooks"] = [h for h in group["hooks"] if not _owned(h, legacy)]
        groups[:] = [g for g in groups if (g["hooks"] if "hooks" in g else not _owned(g, legacy))]
        changed |= before != sum(len(g.get("hooks", [g])) for g in groups)
        if not groups:
            del events[event]
    if "hooks" in cfg and not events:
        del cfg["hooks"]
    return changed


def merge(host, path, repo):
    cfg, existed = _load(path)
    _remove_ours(cfg)
    if host == "cursor":
        cfg.setdefault("version", 1)
    elif cfg.get("description") in LEGACY_DESCRIPTIONS or not existed:
        cfg["description"] = DESCRIPTION
    for event, *wiring in HOSTS[host]:
        cfg.setdefault("hooks", {}).setdefault(event, []).append(_entry(host, repo, *wiring))
    _save(cfg, path)


def strip(path):
    """Remove what merge added. Restores the pre-install backup when nothing else changed."""
    cfg, existed = _load(path)
    if not existed or not _remove_ours(cfg):
        return
    if cfg.get("description") in LEGACY_DESCRIPTIONS | {DESCRIPTION}:
        del cfg["description"]
    backup = path + BACKUP_SUFFIX
    if os.path.isfile(backup):
        with open(backup) as f:
            try:
                same = json.load(f) == cfg
            except ValueError:
                same = False
        if same:
            shutil.copyfile(backup, _target(path))
            os.unlink(backup)
            return
    if cfg in ({}, {"version": 1}) and not os.path.islink(path):
        os.unlink(path)
    else:
        _save(cfg, path)


def check(host, path, repo):
    cfg, existed = _load(path)
    return existed and all(_entry(host, repo, *wiring) in cfg.get("hooks", {}).get(event, [])
                           for event, *wiring in HOSTS[host])


def main(argv):
    if len(argv) == 5 and argv[1] in ("merge", "check") and argv[2] in HOSTS:
        if argv[1] == "merge":
            merge(*argv[2:])
            return 0
        return 0 if check(*argv[2:]) else 1
    if len(argv) == 3 and argv[1] == "strip":
        strip(argv[2])
        return 0
    if len(argv) == 3 and argv[1] == "validate":
        _load(argv[2])
        return 0
    print(__doc__.strip(), file=sys.stderr)
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except (OSError, ValueError) as error:
        print("%s: %s" % (sys.argv[-2 if len(sys.argv) == 5 else -1], error), file=sys.stderr)
        sys.exit(1)
