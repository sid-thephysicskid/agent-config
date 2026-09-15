#!/usr/bin/env python3
import os
import re
import shlex

from guard_parse import *          # noqa: F401,F403
from guard_git import *          # noqa: F401,F403
from guard_secrets import *          # noqa: F401,F403
from guard_db import *          # noqa: F401,F403
from guard_tools import *          # noqa: F401,F403
from guard_paths import *          # noqa: F401,F403

# Private names the orchestrator itself calls; star imports skip these.
from guard_parse import (  # noqa: F401
    _BRACE_BUDGET,
    interpreter_heredoc_body,
    _cap_segments,
    _piped_segment_indices,
    _shell_fed_indices,
    split_oversize,
)

import guard_db, guard_git, guard_paths, guard_repo, guard_secrets, guard_tools  # noqa: E401,E402

MIDDLE_SIGNALS = re.compile("|".join(
    guard_db.MIDDLE_SIGNALS + guard_git.MIDDLE_SIGNALS + guard_paths.MIDDLE_SIGNALS
    + guard_secrets.MIDDLE_SIGNALS + guard_tools.MIDDLE_SIGNALS), re.I)

def _oversize_verdict(cmd):
    analysable, middle = split_oversize(cmd)
    if middle and MIDDLE_SIGNALS.search(middle):
        return cmd, ("a destructive command buried in the middle of an oversized "
                     "command line, which is too long to analyse in full.",
                     "run the destructive part as its own command, so it can be "
                     "judged on its own")
    return analysable, None
from guard_git import (  # noqa: F401
    _note_checkout,
    _note_git_init,
)
from guard_secrets import (  # noqa: F401
    _is_secret_path,
    _substitution_bodies,
)

MESSAGE_BEARING = re.compile(
    r"^\s*(git\s+(commit|tag|notes)|gh\s+(pr|issue|release)\s+(create|edit|comment)"
    r"|git\s+(log|show|grep|blame)"
    r"|echo|printf|say|grep|rg|ag|ack|fgrep|egrep)\b"
)

depth_guard = [0]

CD_PREFIX = re.compile(
    r"^(?:cd|pushd)(?:\s+(?:-[LP]|--))*\s+(?P<dir>'[^']+'|\"[^\"]+\"|[^\s>&]+)"
    r"(?:\s+\d?>[>&]?\s*\S+)*\s*$")
_ASSIGN = re.compile(
    r"(?:^|[;&\n])\s*(?:export\s+)?([A-Za-z_]\w*)="
    r"('[^'\n]*'|\"[^\"\n]*\"|[^\s;&|'\"`()<>]+)(?=\s*(?:[;&\n]|$))")
_DIR_VAR = re.compile(
    r"((?:\s-C|(?:^|[;&|\n(])\s*cd)\s+)(\"?)\$(\{)?([A-Za-z_]\w*)(?(3)\})\2(?=[\s;&|)]|$)")

def _resolve_dir_vars(cmd):
    found = [(m.start(), m.group(1), m.group(2).strip("'\"")) for m in _ASSIGN.finditer(cmd)]
    if not found:
        return cmd

    def sub(m):
        vals = [v for pos, name, v in found if name == m.group(4) and pos < m.start()]
        if not vals:
            return m.group(0)
        v = re.sub(r"\$\{?HOME\}?(?=/|$)", "~", vals[-1])
        return m.group(0) if re.search(r"[$`\s]", v) or not v else m.group(1) + v
    return _DIR_VAR.sub(sub, cmd)

# popd returns somewhere we did not track, so treat it as unknown.
POPD = re.compile(r"^popd\b")

def _sql_file_written_then_run(cmd, segs):
    fed = set()
    for m in re.finditer(r"\b(?:" + FILE_FED_CLIENT + r")\b"
                         r"[^\n|;&]*?(?:-f|--file)[=\s]+([^\s;&|<>]+)", cmd, re.I):
        fed.add(m.group(1).strip("'\""))
    for m in re.finditer(r"\b(?:" + FILE_FED_CLIENT + r")\b[^\n|;&]*?<\s*([^\s;&|<>]+)",
                         cmd, re.I):
        fed.add(m.group(1).strip("'\""))
    if not fed:
        return False
    names = fed | {os.path.basename(f) for f in fed} | {f.lstrip("./") for f in fed}
    for s in segs:
        m = re.search(r">>?\s*([^\s;&|<>]+)", getattr(s, "raw", str(s)))
        if m and m.group(1).strip("'\"") in names:
            return True
    return False

SEGMENT_RULES = (
    ("sql", lambda seg, inv: check_sql(seg, local=inv.is_local_db)),
    ("prod-db", lambda seg, inv: check_prod_db(inv.raw, stripped=inv.stripped)),
    ("db-wipe", lambda seg, inv: check_db_wipe(inv.raw, stripped=inv.stripped)),
    ("rm", lambda seg, inv: check_rm(seg)),
    ("tools", lambda seg, inv: check_tools(
        strip_quoted(seg)
        if inline_code(inv.unwrapped) and not PROGRAM_EXECUTES.search(seg)
        else seg)),
    ("inline-code", lambda seg, inv: check_inline_code(inv.unwrapped)),
)

_LAST_RULE = [None]

def last_rule():
    return _LAST_RULE[0]

RUNS_A_FILE = re.compile(
    r"(^|[\s;&|(])(" + "|".join(sorted(RUNNER_NAMES, key=len, reverse=True))
    + r"|source|\.)\s")

def _written_then_run(segs, cwd):
    written = {}
    for s in segs:
        raw = getattr(s, "raw", str(s))
        m = re.search(r"^\s*(?:echo|printf|cat)\b(.*?)>>?\s*([^\s;&|<>]+)", raw)
        if not m:
            continue
        quoted = re.findall(r"'([^']*)'|\"([^\"]*)\"", m.group(1))
        body = " ".join(a or b for a, b in quoted) or m.group(1).strip()
        target = m.group(2).strip("'\"")
        if body.strip():
            written[target] = body
            written[os.path.basename(target)] = body
            written["./" + os.path.basename(target)] = body
    if not written:
        return None
    for s in segs:
        raw = getattr(s, "raw", str(s))
        for tok in tokens(raw):
            name = tok.strip("'\"")
            if name not in written:
                continue
            if not RUNS_A_FILE.search(raw) and "<" not in raw:
                continue
            hit = check_command(written[name], cwd)
            if hit:
                return hit
    return None

def _normalise(cmd, cwd):
    if isinstance(cmd, (list, tuple)):
        parts = [str(c) for c in cmd]
        if (len(parts) >= 3 and parts[1].startswith("-")
                and not parts[1].startswith("--")
                and "c" in parts[1]
                and os.path.basename(parts[0]) in SHELL_NAMES):
            cmd = parts[-1]
        else:
            cmd = shlex.join(parts)
    if not cmd or not isinstance(cmd, str) or not cmd.strip():
        return None
    cwd = cwd or os.getcwd()
    if not os.path.isdir(cwd):
        cwd = "\0unresolvable"
    return cmd, cwd

def _reset_budgets():
    _LAST_RULE[0] = None
    guard_repo.reset_state()
    _BRACE_BUDGET[0] = MAX_BRACE_WORK

SKIP = object()

UNKNOWN = "\0unresolvable"

class _Line:

    __slots__ = ("cmd", "cwd", "segs", "piped", "shell_fed", "cwd_stack",
                 "branch_override", "virgin_dirs", "seg", "prose", "seg_cwd")

    def __init__(self, cmd, cwd):
        self.cmd = cmd
        self.cwd = cwd
        self.virgin_dirs = set()
        self.piped = _piped_segment_indices(cmd)
        self.shell_fed = _shell_fed_indices(cmd)
        self.cwd_stack = [cwd]
        self.branch_override = None
        self.segs = segments(cmd)
        if len(self.segs) > MAX_SEGMENTS:
            self.segs = _cap_segments(self.segs)
        self.seg = None
        self.prose = False
        self.seg_cwd = cwd

    @property
    def here(self):
        return self.cwd if self.seg_cwd == UNKNOWN else self.seg_cwd

    @property
    def raw(self):
        return getattr(self.seg, "raw", self.seg)

def _phase_cd(line, idx):
    seg = line.seg
    depth = getattr(seg, "subshell_depth", 0)
    while len(line.cwd_stack) <= depth:
        line.cwd_stack.append(line.cwd_stack[-1])
    del line.cwd_stack[depth + 1:]
    line.seg_cwd = line.cwd_stack[depth]

    if POPD.match(seg):
        line.cwd_stack[depth] = UNKNOWN
        line.branch_override = None
        return SKIP
    if re.match(r"^(cd|pushd)\b", seg) and not CD_PREFIX.match(seg):
        line.cwd_stack[depth] = UNKNOWN
        line.branch_override = None
        return SKIP
    m = CD_PREFIX.match(seg)
    if m:
        line.branch_override = None      # a new directory is a new repo
        d = normalize_path(m.group("dir"))
        cand = d if os.path.isabs(d) else os.path.join(line.here, d)
        cand_norm = os.path.normpath(cand)
        ahead = set()
        if not os.path.isdir(cand) and cand_norm not in line.virgin_dirs:
            for nxt in line.segs[idx + 1:]:
                _note_git_init(nxt, cand_norm, ahead)
        line.cwd_stack[depth] = cand_norm if (
            os.path.isdir(cand) or cand_norm in line.virgin_dirs
            or cand_norm in ahead) else UNKNOWN
        return SKIP
    return None

def _phase_prose(line, idx):
    line.prose = bool(MESSAGE_BEARING.search(line.seg))
    if line.prose and idx in line.shell_fed:
        line.prose = False
        seg = line.seg
        _uq = str(seg).replace(chr(34), "").replace(chr(39), "")
        _uqraw = getattr(seg, "raw", str(seg)).replace(chr(34), "").replace(chr(39), "")
        line.seg = Segment(_uq, _uqraw, getattr(seg, "subshell_depth", 0))
    return None

def _phase_secrets(line, idx):
    raw = line.raw
    hit = check_env_print(raw, line.cmd) or check_secrets_cmd(strip_quoted(raw) if line.prose else raw,
                            loose=not line.prose,
                            piped=(idx in line.piped), stripped=line.seg)
    if hit:
        return hit
    if "$(" in raw or "`" in raw:
        return check_substitutions(raw)
    return None

def _phase_git(line, idx):
    hit = check_git(line.seg, line.here,
                    None if line.seg_cwd == UNKNOWN else line.branch_override,
                    unknown_cwd=(line.seg_cwd == UNKNOWN),
                    virgin_dirs=line.virgin_dirs)
    if hit:
        return hit
    _note_git_init(line.seg, line.here, line.virgin_dirs)
    if not line.prose:
        line.branch_override = _note_checkout(
            line.seg, line.here, line.seg_cwd == UNKNOWN, line.branch_override)
    return None

def _phase_nested(line, idx):
    if depth_guard[0] != 0:
        return None
    raw = line.raw
    bodies = [p for p in fed_payloads(raw) if p.strip()]
    if "$(" in raw or "`" in raw:
        bodies += [b for b in _substitution_bodies(raw) if b.strip()]
    if not bodies:
        return None
    depth_guard[0] = 1
    try:
        for body in bodies:
            hit = check_command(body, line.seg_cwd)
            if hit:
                return hit
    finally:
        depth_guard[0] = 0
    return None

def _phase_writes(line, idx):
    for target in redirect_targets(line.raw):
        hit = check_control_path(normalize_path(target), target)
        if hit:
            return hit
    return check_guard_mutation(line.raw, line.cmd)

def _phase_rules(line, idx):
    if line.prose:
        return SKIP
    inv = Invocation(line.raw, line.seg)
    for name, rule in SEGMENT_RULES:
        hit = rule(line.seg, inv)
        if hit:
            _LAST_RULE[0] = name
            return hit
    return None

SEGMENT_PHASES = (
    _phase_cd,
    _phase_prose,
    _phase_secrets,
    _phase_git,
    _phase_nested,
    _phase_writes,
    _phase_rules,
)

def check_command(cmd, cwd=None):
    prepared = _normalise(cmd, cwd)
    if prepared is None:
        return None
    cmd, cwd = prepared
    if depth_guard[0] == 0:
        _reset_budgets()

    cmd, oversize = _oversize_verdict(cmd)
    if oversize:
        return oversize

    body = interpreter_heredoc_body(cmd)
    if body:
        hit = check_inline_code("", code=body)
        if hit:
            return hit

    cmd = re.sub(r"\$\(\s*pwd\s*\)|`\s*pwd\s*`", "$PWD", cmd)
    cmd = _resolve_dir_vars(cmd)

    cmd = blank_inert_heredocs(cmd)

    hit = check_xargs_rm(cmd)
    if hit:
        return hit

    line = _Line(cmd, cwd)
    for idx, seg in enumerate(line.segs):
        line.seg, line.prose = seg, False
        for phase in SEGMENT_PHASES:
            hit = phase(line, idx)
            if hit is SKIP:
                break
            if hit:
                return hit

    hit = _written_then_run(line.segs, line.cwd)
    if hit:
        return hit
    if "\n" in cmd or re.search(r"\|\s*\S*(?:" + FILE_FED_CLIENT + r")\b", cmd, re.I) \
            or _sql_file_written_then_run(cmd, line.segs):
        whole = re.sub(r"\s+", " ",
                       " ; ".join(getattr(s, "raw", str(s)) for s in line.segs))
        if is_sql_context(whole) or not MESSAGE_BEARING.search(whole.strip()):
            hit = check_sql(whole)
            if hit:
                return hit
            hit = check_db_wipe(whole, anchored=False)
            if hit:
                return hit
    return None
