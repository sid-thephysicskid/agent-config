#!/usr/bin/env python3
"""Merge the guard hooks and deny rules into Claude Code settings.json.

    install_settings.py merge <path> <hook dir>   wire us in, preserving everything else
    install_settings.py check <path> <hook dir>   exit 1 unless wired
    install_settings.py strip <path>              remove exactly what merge added
    install_settings.py validate <path>           exit 1 on a shape merge would guess about

Python 3.9, stdlib only.
"""
import json
import os
import re
import shlex
import shutil
import stat
import sys
import tempfile

# Paths and one flagless command only: a deny rule cannot carve out exceptions or flag permutations.
DENY = (
    "Bash(git reset --hard:*)",
    "Read(**/.env)",
    "Read(**/.env.local)",
    "Read(**/.env.production)",
    "Read(**/id_rsa)",
    "Read(**/id_ed25519)",
    "Read(**/.pgpass)",
    "Read(**/.netrc)",
)
_HOOKS_DENY = re.compile(r"^Write\(.+/\*\*\)$")

WIRING = (
    ("PreToolUse", "Bash", "guard-bash.py", 5),
    ("PreToolUse", "Read|Edit|Write|MultiEdit|NotebookEdit|mcp__.*__(read.*|view.*|write.*|edit.*|move.*|rename.*|delete.*|remove.*|create.*|apply.*)", "guard-files.py", 5),
    ("UserPromptSubmit", None, "guard-prompt.py", 5),
)

_COMMAND_TAG = "agent-config-hook-v1"
_DENY_STATE_SUFFIX = ".agent-config-deny.json"
BACKUP_SUFFIX = ".before-agent-config"
# onbelay-hook-v1 is the 0.4.x spelling of the same marker.
_TAGGED = re.compile(r"^: (?:agent-config|onbelay)-hook-v1:([\w.-]+); ")
# Untagged commands written by releases before the tag existed.
_OUR_SHAPE = re.compile(
    r"^if test -f ~/\.claude/hooks/([\w.-]+); then exec python3 "
    r"~/\.claude/hooks/\1; fi; exit 0$")
_OURS = re.compile(
    r"python3?\s+\S*[./]claude/hooks/"
    r"guard-(bash|files)\.py(\s|;|$)")


def deny_rules(hook_dir):
    # Permission paths: ~/ is home, // is absolute.
    home = os.path.expanduser("~") + "/"
    where = "~/" + hook_dir[len(home):] if hook_dir.startswith(home) else "/" + hook_dir
    return DENY + ("Write(%s/**)" % where.rstrip("/"),)


def _cmd(script, hook_dir):
    path = shlex.quote(os.path.join(hook_dir, script))
    return ": %s:%s; if test -f %s; then exec python3 %s; fi; exit 0" % (
        _COMMAND_TAG, script, path, path)


def our_hook_script(command):
    """The script name if an install of ours wrote this command, else None."""
    text = str(command).strip()
    found = _TAGGED.match(text) or _OUR_SHAPE.match(text)
    return found.group(1) if found else None


def runs_ours(command):
    return bool(our_hook_script(command) or _OURS.search(str(command)))


def _target(path):
    return os.path.realpath(path) if os.path.islink(path) else path


def _load(path):
    cfg = {}
    if os.path.exists(_target(path)):
        with open(_target(path)) as f:
            cfg = json.load(f)
    if not isinstance(cfg, dict):
        raise ValueError("settings.json is not a JSON object")
    hooks = cfg.get("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("hooks is not an object")
    for event, entries in hooks.items():
        if not isinstance(entries, list):
            raise ValueError("hooks.%s is not a list" % event)
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("hooks", []), list) \
                    or not all(isinstance(h, dict) for h in entry.get("hooks", [])):
                raise ValueError("a hooks.%s entry is malformed" % event)
    permissions = cfg.get("permissions", {})
    if not isinstance(permissions, dict):
        raise ValueError("permissions is not an object")
    if not isinstance(permissions.get("deny", []), list):
        raise ValueError("permissions.deny is not a list")
    return cfg


def _deny_state_path(path):
    return _target(path) + _DENY_STATE_SUFFIX


def _load_managed_denies(path):
    state = _deny_state_path(path)
    if not os.path.lexists(state):
        return []
    if os.path.islink(state) or not os.path.isfile(state):
        raise ValueError("managed deny state is not a regular file")
    with open(state) as f:
        managed = json.load(f)
    if not isinstance(managed, list) or any(rule not in DENY and not _HOOKS_DENY.match(str(rule)) for rule in managed):
        raise ValueError("managed deny state is invalid")
    return managed


def validate(path):
    _load(path)
    _load_managed_denies(path)


def _save(value, path):
    # tmp-then-rename so a crash cannot truncate the file.
    path = _target(path)
    mode = stat.S_IMODE(os.stat(path).st_mode) if os.path.exists(path) else 0o600
    fd, tmp = tempfile.mkstemp(prefix=".%s.tmp-" % os.path.basename(path),
                               dir=os.path.dirname(os.path.abspath(path)))
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "w") as f:
            fd = -1
            json.dump(value, f, indent=2)
            f.write("\n")
        os.replace(tmp, path)
        tmp = None
    finally:
        if fd >= 0:
            os.close(fd)
        if tmp is not None:
            os.unlink(tmp)


def _remove_ours(cfg, keep=()):
    """Drop our hook commands, except scripts in keep. Returns True if anything changed."""
    changed = False
    events = cfg.get("hooks", {})
    for event, entries in list(events.items()):
        for entry in entries:
            inner = entry.get("hooks", [])
            kept = [h for h in inner if not runs_ours(h.get("command", ""))
                    or our_hook_script(h.get("command", "")) in keep]
            if len(kept) != len(inner):
                entry["hooks"], changed = kept, True
        entries[:] = [e for e in entries if e.get("hooks")]
        if not entries:
            del events[event]
    if "hooks" in cfg and not cfg["hooks"]:
        del cfg["hooks"]
    return changed


def merge(path, hook_dir):
    cfg = _load(path)
    managed = _load_managed_denies(path)
    _remove_ours(cfg)
    for event, matcher, script, timeout in WIRING:
        entries = cfg.setdefault("hooks", {}).setdefault(event, [])
        entry = next((e for e in entries if e.get("matcher") == matcher), None)
        if entry is None:
            entry = {"hooks": []} if matcher is None else {"matcher": matcher, "hooks": []}
            entries.append(entry)
        entry["hooks"].append(
            {"type": "command", "command": _cmd(script, hook_dir), "timeout": timeout})
    deny = cfg.setdefault("permissions", {}).setdefault("deny", [])
    for rule in deny_rules(hook_dir):
        if rule not in deny:
            deny.append(rule)
            if rule not in managed:
                managed.append(rule)
    _save(cfg, path)
    # The ledger tells strip our rules apart from identical ones the user already had.
    _save(managed, _deny_state_path(path))


def strip(path):
    """Remove exactly what merge added. Restores the pre-install backup when nothing else changed."""
    if not os.path.exists(_target(path)):
        return
    cfg = _load(path)
    state = _deny_state_path(path)
    managed = set(_load_managed_denies(path))
    changed = _remove_ours(cfg)
    perms = cfg.get("permissions", {})
    if managed and isinstance(perms.get("deny"), list):
        perms["deny"] = [r for r in perms["deny"] if r not in managed]
        if not perms["deny"]:
            del perms["deny"]
        if not perms:
            del cfg["permissions"]
        changed = True
    if os.path.lexists(state):
        os.unlink(state)
    if not changed:
        return
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
        return
    _save(cfg, path)


def check(path, hook_dir):
    cfg = _load(path)
    for event, matcher, script, timeout in WIRING:
        wanted = _cmd(script, hook_dir)
        if not any(entry.get("matcher") == matcher
                   and any(h.get("command") == wanted and h.get("timeout") == timeout
                           for h in entry.get("hooks", []))
                   for entry in cfg.get("hooks", {}).get(event, [])):
            return False
    return True


def main(argv):
    action = argv[1] if len(argv) > 1 else ""
    if action == "merge" and len(argv) == 4:
        merge(argv[2], argv[3])
        return 0
    if action == "check" and len(argv) == 4:
        return 0 if check(argv[2], argv[3]) else 1
    if action in ("strip", "validate") and len(argv) == 3:
        {"strip": strip, "validate": validate}[action](argv[2])
        return 0
    print(__doc__.strip(), file=sys.stderr)
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except (OSError, ValueError) as error:
        print("%s: %s" % (sys.argv[2] if len(sys.argv) > 2 else "settings", error), file=sys.stderr)
        sys.exit(1)
