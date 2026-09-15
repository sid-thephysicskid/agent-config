#!/usr/bin/env python3
import os
import re
import shlex

# `-c` takes a COMMAND LINE, which has to be re-split into segments.
SHELL_NAMES = frozenset(("sh", "bash", "zsh", "dash", "ksh", "ash", "busybox"))
INTERPRETER_NAMES = frozenset(("python", "python2", "python3", "perl", "ruby",
                               "node", "deno", "bun"))
RUNNER_NAMES = SHELL_NAMES | INTERPRETER_NAMES

def _alt(names):
    return "|".join(sorted((re.escape(n) for n in names), key=len, reverse=True))

_RUNNERS = _alt(RUNNER_NAMES)

def asks_for_help(seg):
    toks = tokens(seg)
    for tok in toks:
        if tok == "--":
            break
        if tok == "--help":
            return True
    for i, tok in enumerate(toks):
        if os.path.basename(tok) == "git":
            for nxt in toks[i + 1:]:
                if nxt.startswith("-"):
                    continue
                return nxt == "help"
    return False

_SHELL_HEAD = re.compile(
    r"^\s*(\S*/)?(" + _RUNNERS + r")\b")

WRAPPERS = {"sudo", "env", "command", "builtin", "exec", "nohup", "time", "nice",
            "eval", "if", "while", "until", "then", "do", "else", "elif",
            "fi", "done", "!",
            "timeout", "stdbuf", "setsid", "flock", "doas", "torsocks",
            "chrt", "ionice", "unbuffer"}

_WRAPPER_VALUE_FLAGS = {
    "sudo": {"-u", "-g", "-p", "-C", "-r", "-t", "-U", "--user", "--group"},
    "nice": {"-n", "--adjustment"},
    "env": {"-u", "-C", "--chdir", "--unset"},
    "timeout": {"-s", "-k", "--signal", "--kill-after"},
    "stdbuf": {"-i", "-o", "-e", "--input", "--output", "--error"},
    "flock": {"-w", "--wait", "--timeout", "-E", "--conflict-exit-code"},
    "ionice": {"-c", "-n", "--class", "--classdata"},
    "chrt": {"-p", "--pid"},
}
_NEXT_TOKEN = re.compile(r"\s*(?P<tok>\S+)")

def strip_wrapper_prefix(text):
    i, saw, current = 0, False, None
    while True:
        m = _NEXT_TOKEN.match(text, i)
        if not m:
            break
        tok = m.group("tok")
        if tok in WRAPPERS:
            i, saw, current = m.end(), True, tok
            continue
        if "=" in tok and not tok.startswith("-"):
            i, saw = m.end(), True
            continue
        if not saw:
            break
        if tok.startswith("-"):
            i = m.end()
            if tok in _WRAPPER_VALUE_FLAGS.get(current, ()):
                nxt = _NEXT_TOKEN.match(text, i)
                if nxt:
                    i = nxt.end()
            continue
        # `nice 10 cmd` is the flagless spelling of the adjustment.
        if current == "nice" and tok.isdigit():
            i = m.end()
            continue
        break
    return text[i:] if saw else text

MAX_ANALYSED = 32 * 1024

TAIL_ANALYSED = 8 * 1024

MAX_SEGMENTS = 4000

DB_CLIENT = re.compile(
    r"^\s*\S*(psql|pg_dump|pg_restore|mysql|mysqldump|mongo|mongosh|mongodump"
    r"|redis-cli|clickhouse-client|sqlcmd|cqlsh)\b")

LOCAL_HOSTS = re.compile(
    r"^(localhost|127\.0\.0\.1|0\.0\.0\.0|::1|.*\.local|.*\.localhost|host\.docker\.internal)$", re.I)

# Bounded: unanchored, `live` matched inside `deliveroo.example.com`.
PROD_HOSTISH = re.compile(r"(^|[.\-_])(prod|production|live)([.\-_]|$)", re.I)

URI_HOST = re.compile(
    r"(postgres|postgresql|mysql|mongodb(?:\+srv)?|redis|clickhouse)://"
    r"(?:[^\s'\"/@]*@)?([^\s'\"/:?]+)", re.I)

DB_HOST_ENV = r"\b(?:PGHOST|MYSQL_HOST|MONGO_HOST|REDIS_HOST)\s*=\s*([^\s'\"]+)"

HOST_FLAG = r"(?:^|\s)(?:--host[=\s]+|-h[=\s]*)([^\s'\"=]+)"

# Bounded like PROD_HOSTISH, so `latest.db` does not read as `test`.
DEV_DBISH = re.compile(
    r"(^|[/.\-_])(dev|development|test|testing|tmp|temp|scratch|fixture|sample|local)"
    r"([/.\-_]|$)", re.I)

class Segment(str):
    def __new__(cls, value, raw, subshell_depth=0):
        s = super().__new__(cls, value)
        s.raw = raw
        s.subshell_depth = subshell_depth
        return s

_SPLITTERS = ("||", "&&", ";", "|", "\n", "&", "(", ")")

def _split_unquoted(cmd):
    out, buf, quote, i, depth = [], [], None, 0, 0
    while i < len(cmd):
        ch = cmd[i]
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            elif ch == "\\" and quote == '"' and i + 1 < len(cmd):
                buf.append(cmd[i + 1]); i += 1
            i += 1
            continue
        if ch == "\\" and i + 1 < len(cmd):
            buf.append(ch); buf.append(cmd[i + 1]); i += 2; continue
        if ch in ("'", '"'):
            quote = ch; buf.append(ch); i += 1; continue
        if ch == "#" and (i == 0 or (cmd[i - 1] in " \t\n;&|("
                                     and not (i >= 2 and cmd[i - 2] == "\\"
                                              and cmd[i - 1] in " \t"))):
            j = cmd.find("\n", i)
            if j == -1:
                break
            i = j
            continue
        matched = next((s for s in _SPLITTERS if cmd.startswith(s, i)), None)
        if matched:
            out.append(("".join(buf), depth, matched))
            buf = []
            if matched == "(":
                depth += 1
            elif matched == ")":
                depth = max(0, depth - 1)
            i += len(matched)
            continue
        buf.append(ch); i += 1
    out.append(("".join(buf), depth, None))
    return out

HEREDOC_OPEN = re.compile(r"<<-?\s*(?P<q>[\\\"'])?(?P<tag>[A-Za-z_][\w]*)[\"']?")

INTERPRETER = re.compile(
    r"(^|[\s(|])(" + _alt(RUNNER_NAMES | {"osascript", "xargs", "eval"}) + r")"
    r"(?=\s|<|$)")

INLINE_CODE = re.compile(
    r"^\s*(\S*/)?(" + _alt(INTERPRETER_NAMES) + r")\b[^|;&]*?\s-(c|e)\s+(?P<q>[\"'])"
    r"(?P<code>.*?)(?P=q)", re.S)

def interpreter_heredoc_body(seg):
    if "<<" not in seg:
        return ""
    lines, out, i = seg.replace("\\\n", " ").split("\n"), [], 0
    while i < len(lines):
        m = HEREDOC_OPEN.search(lines[i])
        if not m or not INTERPRETER.search(lines[i]):
            i += 1
            continue
        tag, j = m.group("tag"), i + 1
        while j < len(lines) and lines[j].strip() != tag:
            j += 1
        out.append("\n".join(lines[i + 1:j]))
        i = j + 1
    return "\n".join(out)

def inline_code(seg):
    m = INLINE_CODE.match(seg)
    return m.group("code") if m else ""

_LEADING_ASSIGN = re.compile(
    r"^\s*[A-Za-z_][A-Za-z0-9_]*=(?:'[^']*'|\"[^\"]*\"|[^\s]*)\s*")

FED_PAYLOAD = re.compile(r"<<<\s*(?P<herestring>.+)$")

def fed_payloads(seg):
    if not INTERPRETER.search(seg.split("<")[0]):
        return []
    out = []
    for m in FED_PAYLOAD.finditer(seg):
        body = (m.group("herestring") or "").strip().strip("\"'")
        if body:
            out.append(body)
    return out

CONTENT_READER = re.compile(
    r"^\s*xargs\b"
    r"|^\s*while\s+read\b"
    r"|\{\}"
    r"|^\s*(cat|bat|head|tail|less|more|strings|xxd|od|base64|cp|mv|tee|scp"
    r"|tar|cpio|parallel)\s+(?!-)(?![0-9])\S")

SUBST_FINDER = re.compile(r"\$\(\s*(find|ls)\b")

ANY_READER = re.compile(
    r"(^|[\s;&|])(cat|bat|head|tail|less|more|strings|xxd|od|base64"
    r"|cp|mv|tee|scp|grep|awk|sed|perl|python3?)\b")

def _piped_segment_indices(cmd):
    cmd = blank_inert_heredocs(cmd.replace("\\\n", " "))
    parts = [(txt, following) for txt, _, following in _split_unquoted(cmd) if txt.strip()]
    piped = set()
    if SUBST_FINDER.search(cmd) and ANY_READER.search(cmd):
        return set(range(len(parts)))
    reader_ahead = False
    for i in range(len(parts) - 1, -1, -1):
        text, following = parts[i]
        if following != "|":
            reader_ahead = CONTENT_READER.match(text.strip()) is not None
            continue
        if reader_ahead or CONTENT_READER.match(text.strip()):
            piped.add(i)
        reader_ahead = reader_ahead or CONTENT_READER.match(text.strip()) is not None
    return piped

def _executed_names(cmd):
    names = set()
    runners = (r"(?:^|[\s;&|(])(?:\.|source|" + _RUNNERS
               + r"|osascript)(?:\s+-\S+)*\s+([^\s;&|<>]+)")
    for m in re.finditer(runners, cmd):
        names.add(m.group(1).strip("'\""))
    # `chmod +x X` is preparation to run it, and `./X` is running it.
    for m in re.finditer(r"(?:^|[\s;&|(])chmod\s+\+x\s+([^\s;&|<>]+)", cmd):
        names.add(m.group(1).strip("'\""))
    for m in re.finditer(r"(?:^|[\s;&|(])\./([^\s;&|<>]+)", cmd):
        names.add("./" + m.group(1).strip("'\""))
    for m in re.finditer(r"(?:^|[\s;&|(])(?:\.|source|" + _RUNNERS
                         + r")\b[^\n;&|]*<\s*([^\s;&|<>]+)", cmd):
        names.add(m.group(1).strip("'\""))
    if re.search(r"\|\s*\S*(" + _RUNNERS + r")\b", cmd) \
            or re.search(r"\beval\b", cmd):
        # The file is named upstream of the pipe, or inside the eval.
        for m in re.finditer(r"(?:^|[\s;&|(])(?:cat|bat|head|tail)\s+([^\s;&|<>]+)", cmd):
            names.add(m.group(1).strip("'\""))
    out = set()
    for n in names:
        if not n:
            continue
        out.add(n)
        out.add(n.lstrip("./"))
        out.add(os.path.basename(n))
    return {n for n in out if n}

def _written_then_run(opener, executed):
    if not executed:
        return False
    m = (re.search(r">>?\s*([^\s|&;<>]+)", opener)
         or re.search(r"\btee\b(?:\s+-\S+)*\s+([^\s|&;<>]+)", opener)
         or re.search(r"\bdd\b[^\n]*\bof=([^\s|&;<>]+)", opener))
    if not m:
        return False
    target = m.group(1).strip("'\"")
    if not target:
        return False
    # Compare on the basename too: `cat > ./x.sh` then `bash x.sh` is one file.
    return bool({target, target.lstrip("./"), os.path.basename(target)} & executed)

MESSAGE_FILE_OPENER = re.compile(
    r"(^|\s)git\s+(commit|tag|notes)\b[^|]*?\s(-F|--file)(=|\s*)-(?=\s|$)"
    r"|(^|\s)gh\b[^|]*?\s(--body-file|--notes-file)(=|\s*)-(?=\s|$)")

def blank_inert_heredocs(cmd):
    if "<<" not in cmd:
        return cmd
    cmd = cmd.replace("\\\n", " ")   # a continued opener is still one line
    executed = _executed_names(cmd)     # ONCE, not once per opener
    lines, i = cmd.split("\n"), 0
    while i < len(lines):
        m = HEREDOC_OPEN.search(lines[i])
        if m:
            opener = lines[i]
            tag = m.group("tag")
            j = i + 1
            while j < len(lines) and lines[j].strip() != tag:
                j += 1
            terminated = j < len(lines)
            expands = m.group("q") is None
            has_subst = expands and any(
                ("$(" in lines[k] or "$ (" in lines[k] or "`" in lines[k])
                for k in range(i + 1, j))
            inert = (terminated
                     and not has_subst
                     and not INTERPRETER.search(opener)
                     and not is_sql_context(opener)
                     and "|" not in opener
                     and (re.search(r"(^|\s)(cat|tee|dd)\b|>\s*[^\s|&]+", opener)
                          or MESSAGE_FILE_OPENER.search(opener)))
            if inert and _written_then_run(opener, executed):
                inert = False
            if inert:
                for k in range(i + 1, j):
                    lines[k] = ""
            i = j + 1
            continue
        i += 1
    return "\n".join(lines)

PROGRAM_EXECUTES = re.compile(
    r"\b(os\.(system|popen|exec\w*|spawn\w*)"
    r"|subprocess\.\w+|commands\.getoutput"
    r"|child_process|execSync|spawnSync|\bexecFile\b"
    r"|Kernel#?system|IO\.popen|%x\{"
    r"|shell_exec|passthru|proc_open"
    r"|\bsystem\s*\(|\bexec\s*\(|\beval\s*\()", re.I)

# Characters that can start a new command inside an unwrapped payload.
SPLITTER_HINT = re.compile(r"[;&|\n]")

_RUNNER_SCAN = 8

def _dash_c_payload(toks):
    start = None
    for i, tok in enumerate(toks[:_RUNNER_SCAN]):
        if os.path.basename(tok.strip("'\"")) in SHELL_NAMES | INTERPRETER_NAMES:
            start = i
            break
    if start is None:
        return None, False
    name = os.path.basename(toks[start].strip("'\""))
    is_shell = name in SHELL_NAMES
    flags = ("c",) if is_shell else ("c", "e")
    for i in range(start + 1, len(toks)):
        tok = toks[i]
        if tok == "--":
            return None, False
        if tok.startswith("--"):
            continue                      # a long option is never -c or -e
        if tok.startswith("-") and len(tok) > 1 and tok[1:].isalpha() \
                and any(f in tok[1:] for f in flags):
            return (toks[i + 1], is_shell) if i + 1 < len(toks) else (None, False)
    return None, False

def segments(cmd, _depth=0):
    cmd = cmd.replace("\\\n", " ")
    parts = _split_unquoted(cmd)
    out = []
    for p, depth, _following in parts:
        raw = p.strip()
        if not raw:
            continue
        head = raw
        while True:
            m = _LEADING_ASSIGN.match(head)
            if not m:
                break
            head = head[m.end():]
        if not head.strip():
            out.append(Segment(raw, "", depth))
            continue
        toks = strip_wrapper_prefix(head).split()
        if not toks:
            out.append(Segment(raw, raw, depth))
            continue
        s = " ".join(toks)
        unwrapped_shell = False
        for _ in range(3):
            payload, is_shell = _dash_c_payload(tokens(s))
            if payload is not None:
                s = payload.strip()
                unwrapped_shell = is_shell
                continue
            m = re.fullmatch(r"""['"](.+)['"]""", s.strip())
            if m:
                s = m.group(1).strip()
                unwrapped_shell = True
                continue
            break
        if unwrapped_shell and _depth < 2 and SPLITTER_HINT.search(s):
            for sub in segments(s, _depth + 1):
                out.append(Segment(str(sub), getattr(sub, "raw", str(sub)), depth))
            continue
        out.append(Segment(s, s if unwrapped_shell else raw, depth))
    return out

def strip_quoted(s):
    return re.sub(r"'[^']*'|\"[^\"]*\"", " ", s)

def normalize_path(tok):
    t = tok.strip().strip("'\"")
    if t.startswith("${"):
        t = re.sub(r"^\$\{(\w+)(:[^}]*)?\}", r"${\1}", t)
    elif ":" in t and "://" not in t:
        head, _, tail = t.partition(":")
        if head[:1] in ("/", "~", ".", "$"):
            t = head
        elif tail and not head.startswith("-"):
            t = tail
    t = re.sub(r"^\$\{HOME(:[^}]*)?\}|^\$HOME\b", os.path.expanduser("~"), t)
    t = re.sub(r"^~", os.path.expanduser("~"), t)
    if ".." in t or "/./" in t:
        keep_trailing = t.endswith("/")
        t = os.path.normpath(t)
        if keep_trailing and not t.endswith("/"):
            t += "/"
    if len(t) > 1:
        t = t.rstrip("/")
    return t

def tokens(seg):
    try:
        return shlex.split(seg)
    except ValueError:
        return seg.split()

class Invocation:

    __slots__ = ("raw", "stripped", "_memo")

    def __init__(self, raw, stripped=None):
        self.raw = str(raw)
        self.stripped = str(stripped) if stripped is not None else self.raw
        self._memo = {}

    def _c(self, key, fn):
        if key not in self._memo:
            self._memo[key] = fn()
        return self._memo[key]

    @property
    def unwrapped(self):
        return self._c("unwrapped", lambda: strip_wrapper_prefix(self.raw))

    @property
    def toks(self):
        return self._c("toks", lambda: tokens(self.stripped))

    @property
    def is_db_client(self):
        return self._c("dbc", lambda: bool(DB_CLIENT.match(self.stripped)))

    @property
    def is_sqlite(self):
        return self._c("sqlite", lambda: bool(
            re.match(r"^\s*\S*sqlite3?\b", self.stripped)))

    @property
    def is_docker_exec(self):
        return self._c("dex", lambda: bool(
            re.search(r"\bdocker\b[^|;&]*\bexec\b", self.raw, re.I)
            and not re.search(
                r"(^|\s)(-H|--host|--context)[=\s]|\bDOCKER_HOST\s*=", self.raw)))

    @property
    def all_hosts(self):
        return self._c("allh", lambda: (
            re.findall(HOST_FLAG, self.raw)
            + [m.group(2) for m in URI_HOST.finditer(self.raw)]
            + re.findall(DB_HOST_ENV, self.raw, re.I)))

    @property
    def db_hosts(self):
        def _v():
            out = ([m.group(2) for m in URI_HOST.finditer(self.raw)]
                   + re.findall(DB_HOST_ENV, self.raw, re.I))
            if self.is_db_client:
                out += re.findall(HOST_FLAG, self.raw)
                out += re.findall(r"\bhost\s*=\s*([^\s'\";]+)", self.raw, re.I)
            return out
        return self._c("dbh", _v)

    @property
    def prod_host(self):
        return self._c("prodh", lambda: next(
            (h for h in self.db_hosts
             if not LOCAL_HOSTS.match(h) and PROD_HOSTISH.search(h)), None))

    @property
    def sqlite_target(self):
        def _v():
            if not self.is_sqlite:
                return ""
            args = [a for a in self.toks[1:] if not a.startswith("-")]
            return args[0] if args else ""
        return self._c("sqt", _v)

    @property
    def is_local_db(self):
        def _v():
            if self.all_hosts:
                return all(LOCAL_HOSTS.match(h) for h in self.all_hosts)
            if self.is_docker_exec:
                return True
            t = self.sqlite_target
            return bool(self.is_sqlite and (
                t == ":memory:"
                or (DEV_DBISH.search(t) and not PROD_HOSTISH.search(t))))
        return self._c("local", _v)

SQL_CONTEXT = re.compile(
    r"\b(psql|pgcli|mysql|mycli|mysqldump|mariadb|sqlite3|litecli|duckdb|usql"
    r"|sqlcmd|snowsql|bq|wrangler|turso|trino|athena|presto|mongosh|mongo"
    r"|clickhouse-client|cockroach|redis-cli"
    r"|prisma|supabase|alembic|flyway|liquibase|knex|sequelize|rails|dbmate|atlas)\b"
    r"|<<\s*'?EOSQL"
    , re.I)

SQL_STATEMENT_FLAG = re.compile(
    r"(-c|-e|-Q|--command|--eval|--sql|--execute)[=\s]+[\"']?\s*"
    r"(SELECT|INSERT|UPDATE|DELETE|DROP|TRUNC|ALTER|CREATE)\b", re.I)

SQL_CLIENTISH = re.compile(r"\b(psql|mysql|mariadb|mongosh|mongo|redis-cli|clickhouse\w*)\b", re.I)

FILE_FED_CLIENT = r"psql|mysql|mariadb|mongosh|mongo|sqlite3?|clickhouse\w*|redis-cli"

PATTERN_TAKING_TOOL = re.compile(
    r"^\s*\S*(grep|rg|ag|ack|fgrep|egrep|sed|awk|rga)\b")

class SqlFragment(str):
    """One statement split out of a multi-statement line; SQL context is implied."""

_REDIRECT = re.compile(r"(?<![<>&\d])>>?\s*(?![&|(])([^\s;&|<>()\"']+)")

def redirect_targets(seg):
    if ">" not in seg:
        return []
    return [m.group(1) for m in _REDIRECT.finditer(strip_quoted(seg))
            if m.group(1)]

_SQL_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)

def strip_sql_comments(s):
    s = _SQL_BLOCK_COMMENT.sub(" ", s)
    out, i, quote = [], 0, None
    while i < len(s):
        ch = s[i]
        if quote:
            if ch == quote:
                quote = None
                out.append(ch)
            elif ch == "-" and s[i + 1:i + 2] == "-":
                nl = s.find("\n", i)
                end = s.find(quote, i)
                stop = min(x for x in (nl, end, len(s)) if x != -1)
                i = stop
                continue
            else:
                out.append(ch)
            i += 1
            continue
        if ch in ("'", '"'):
            quote = ch
        out.append(ch)
        i += 1
    return "".join(out)

def is_sql_context(s):
    if isinstance(s, SqlFragment):
        return True
    if PATTERN_TAKING_TOOL.match(s):
        return False
    return bool(SQL_CONTEXT.search(s)
                or (SQL_STATEMENT_FLAG.search(s) and SQL_CLIENTISH.search(s)))

GLOBBED = re.compile(r"[*?\[{]")

def _is_dot_walk(tok):
    tok = tok.strip("'\"")
    if re.fullmatch(r"\$\{?PWD\}?|\$\(\s*pwd\s*\)|`\s*pwd\s*`", tok):
        return True
    return bool(re.fullmatch(r"\.{1,2}(/\.{1,2})*/?\*?", tok))

MAX_BRACE_WORK = 4000

_BRACE_BUDGET = [MAX_BRACE_WORK]

def _brace_fragments(tok, cap=256):
    out = []
    lo, hi = tok.find("{"), tok.rfind("}")
    if lo == -1 or hi == -1 or hi < lo:
        return []
    head, tail = tok[:lo], tok[hi + 1:]
    for frag in re.split(r"[{},]+", tok):
        if not frag:
            out.append(head + tail)
            continue
        out.append(frag)
        out.append(head + frag + tail)
        if len(out) >= cap:
            break
    # ...and the empty-member case again, since re.split drops a trailing one.
    if re.search(r"[{,]\s*[},]", tok) or tok.rstrip().endswith(",}"):
        out.append(head + tail)
    return [x for x in ((y.replace("{", "").replace("}", "")) for y in out) if x][:cap]

def brace_expand(tok, limit=64):
    tok = tok.strip("'\"")
    if _BRACE_BUDGET[0] <= 0:
        return [tok]        # budget spent; callers fall back to the fragments
    out = [tok]
    truncated = False
    for _ in range(4):
        nxt = []
        grew = False
        for item in out:
            m = re.search(r"\{([^{}]*)\}", item)
            if not m or len(nxt) >= limit:
                if m:
                    truncated = True
                nxt.append(item)
                continue
            grew = True
            head, tail = item[:m.start()], item[m.end():]
            # `{,.config}` has an empty member, which means the prefix alone.
            for part in m.group(1).split(","):
                nxt.append(head + part.strip() + tail)
                if len(nxt) >= limit:
                    truncated = True
                    break
        out = nxt
        _BRACE_BUDGET[0] -= len(out)
        if not grew:
            break
        if _BRACE_BUDGET[0] <= 0:
            truncated = True
            break
        if truncated:
            break
    res = [x for x in out if x]
    if truncated and "{" in tok:
        res.append(tok)
    return res

def _shell_fed_indices(cmd):
    parts = [(txt, following) for txt, _d, following in _split_unquoted(
        blank_inert_heredocs(cmd.replace("\\\n", " "))) if txt.strip()]
    out = set()
    fed_or_shell = False
    for i in range(len(parts) - 1, -1, -1):
        txt, following = parts[i]
        if following == "|" and fed_or_shell:
            out.add(i)
        fed_or_shell = bool(_SHELL_HEAD.match(txt)) or i in out
    return out

def _cap_segments(segs):
    seen, deduped = set(), []
    for s in segs:
        k = " ".join(str(s).split())[:200]
        if k in seen:
            continue
        seen.add(k)
        deduped.append(s)
    keep = MAX_SEGMENTS * 4
    if len(deduped) > keep:
        deduped = deduped[:keep - MAX_SEGMENTS] + deduped[-MAX_SEGMENTS:]
    return deduped

def split_oversize(cmd):
    if len(cmd) <= MAX_ANALYSED:
        return cmd, ""
    return (cmd[:MAX_ANALYSED] + "\n" + cmd[-TAIL_ANALYSED:],
            cmd[MAX_ANALYSED:-TAIL_ANALYSED])
