#!/usr/bin/env python3
"""Merge the guard hook into Codex hooks.json without taking it over.

    install_codex_hooks.py merge <path> <repo>
    install_codex_hooks.py check <path> <repo>
    install_codex_hooks.py strip <path>
    install_codex_hooks.py validate <path>

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
LEGACY_SCRIPTS = {"guard-codex.py", "check-docs.py", "welcome.py"}
WIRING = (
    ("PreToolUse", ".*", "guard-codex.py", 5, "Checking guardrails..."),
    ("UserPromptSubmit", None, "guard-prompt.py", 5, "Checking the prompt for keys..."),
)
BACKUP_SUFFIX = ".before-agent-config"
_COMMAND_TAG = "agent-config-hook-v1"
# onbelay-hook-v1 is the 0.4.x spelling of the same marker.
_OUR_COMMAND = re.compile(
    r"^: (?:agent-config|onbelay)-hook-v1:([\w.-]+); if test -f (.+); "
    r"then exec python3 \2; fi; exit 0$")
_LEGACY_COMMAND = re.compile(
    r"^if test -f '([^']+)/hooks/([\w.-]+)'; then exec python3 "
    r"'\1/hooks/\2'; fi; exit 0$")


def _command(repo, script):
    path = shlex.quote("%s/hooks/%s" % (repo.rstrip("/"), script))
    return ": %s:%s; if test -f %s; then exec python3 %s; fi; exit 0" % (
        _COMMAND_TAG, script, path, path)


def _legacy_command(repo, script):
    path = "%s/hooks/%s" % (repo.rstrip("/"), script)
    return "if test -f '%s'; then exec python3 '%s'; fi; exit 0" % (path, path)


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
        for group in groups:
            kept = [h for h in group.get("hooks", []) if not _owned(h, legacy)]
            if len(kept) != len(group.get("hooks", [])):
                group["hooks"], changed = kept, True
        groups[:] = [g for g in groups if g.get("hooks")]
        if not groups:
            del events[event]
    if "hooks" in cfg and not events:
        del cfg["hooks"]
    return changed


def merge(path, repo):
    cfg, existed = _load(path)
    _remove_ours(cfg)
    for event, matcher, script, timeout, status in WIRING:
        handler = {"type": "command", "command": _command(repo, script),
                   "timeout": timeout, "statusMessage": status}
        group = {"hooks": [handler]}
        if matcher is not None:
            group["matcher"] = matcher
        cfg.setdefault("hooks", {}).setdefault(event, []).append(group)
    if cfg.get("description") in LEGACY_DESCRIPTIONS or not existed:
        cfg["description"] = DESCRIPTION
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
    if not cfg and not os.path.islink(path):
        os.unlink(path)
    else:
        _save(cfg, path)


def check(path, repo):
    cfg, existed = _load(path)
    if not existed:
        return False
    for event, matcher, script, timeout, status in WIRING:
        wanted = {"type": "command", "command": _command(repo, script),
                  "timeout": timeout, "statusMessage": status}
        if not any(g.get("matcher") == matcher and wanted in g.get("hooks", [])
                   for g in cfg.get("hooks", {}).get(event, [])):
            return False
    return True


def main(argv):
    if len(argv) == 4 and argv[1] == "merge":
        merge(argv[2], argv[3])
        return 0
    if len(argv) == 4 and argv[1] == "check":
        return 0 if check(argv[2], argv[3]) else 1
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
        print("%s: %s" % (sys.argv[2] if len(sys.argv) > 2 else "hooks.json", error), file=sys.stderr)
        sys.exit(1)
