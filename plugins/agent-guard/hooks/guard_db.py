#!/usr/bin/env python3
"""Database rules: SQL, production targets, non-SQL wipes."""
import re

from guard_parse import (
    Invocation,
    SqlFragment,
    is_sql_context,
    strip_quoted,
    strip_sql_comments,
)

# See guard_git.MIDDLE_SIGNALS for why these live next to the rules.
MIDDLE_SIGNALS = (
    r"\bDROP\s+(TABLE|DATABASE|SCHEMA)",
    r"\bTRUNC" + r"ATE\b",
    r"\bDELETE\s+FROM\b",
    r"\bUPDATE\b[^\n]{0,40}\bSET\b",
    r"\bprisma\b[^\n]{0,40}\bmigrate\s+reset\b",
    r"\bsupabase\b[^\n]{0,40}\bdb\s+reset\b",
    r"\bFLUSH(ALL|DB)\b",
    r"\brails\b[^\n]{0,40}\bdb:drop\b",
    r"\bartisan\b[^\n]{0,40}\bmigrate:fresh\b",
    r"\bdropDatabase\s*\(",
    # NO production-host signal here, deliberately. The class stops
    # applying once a line is padded past the analysis window, which is a
    # real gap. The obvious signal is a host-flag pattern, and the one
    # tried took 11.8s against this suite's 2.0s budget: it nests
    # unbounded character classes over a 40KB middle. The hook times out
    # at 5s and a timeout fails OPEN, so that signal would have opened a
    # wider hole than it closed. The git and filesystem classes did get
    # signals because theirs are literal and cheap.
    r"\bdeleteMany\s*\(\s*\{\s*\}\s*\)",
    r"\bdb\.\w+\.drop\s*\(\s*\)",
    r"\bdropdb\b",
)


def _quoted_runs(s):
    """Each SQL statement on its own.

    `psql -c '...' -c '...'` is two statements, and so is
    `psql -c 'DELETE FROM a WHERE id=1; DELETE FROM b'`. Judging either as one
    let a WHERE in the first vouch for the second.
    """
    out = []
    for m in re.finditer(r"'([^']*)'|\"([^\"]*)\"", s):
        run = m.group(1) or m.group(2) or ""
        out.extend(part for part in run.split(";") if part.strip())
    return out

def check_sql(seg, local=None):
    """`local` is the ENCLOSING segment's locality, threaded into the fragment
    recursion: a SqlFragment is a bare statement with no client or host."""
    if local is None:
        local = Invocation(seg).is_local_db
    # A SQL client can carry several independent statements on one line. Judge
    # each quoted argument alone first, so a WHERE in one cannot vouch for
    # another.
    if is_sql_context(seg):
        runs = _quoted_runs(seg)
        if len(runs) > 1:
            for run in runs:
                hit = check_sql(SqlFragment(run), local=local)
                if hit:
                    return hit
            # ...then fall through and judge the unquoted remainder as usual.
    # Outside a SQL client, judge only the UNQUOTED text: a quoted argument is
    # a test filter, a JSON body, or a log line, not a statement being executed.
    in_sql = is_sql_context(seg)
    if not in_sql:
        seg = strip_quoted(seg)
    s = re.sub(r"\s+", " ", seg)
    # Comment-stripped, for the same reason the DELETE rules are: `/**/` is a
    # zero-width separator to the database, so `DROP/**/TABLE users` is a DROP
    # TABLE and was not one to a regex reading the raw text.
    s_code = strip_sql_comments(s)
    if re.search(r"\bDROP\s+(TABLE|DATABASE|SCHEMA|COLUMN|INDEX|OWNED\s+BY)\b",
                 s_code, re.I) and not local:
        return ("destructive SQL: DROP.",
                "write a reversible migration and apply it through your migration tool")
    # Needs SQL context: `truncate` is also coreutils (`truncate -s 0 app.log`)
    # and a common make target (`make truncate-logs`).
    # The name no longer has to end the statement. `TRUNCATE users CASCADE`
    # was ALLOWED while `TRUNCATE users` blocked, and CASCADE is strictly worse:
    # it truncates every foreign-key dependent table as well.
    if re.search(r"\bTRUNC" + r"ATE\s+(TABLE\b|ONLY\b|[\"'`\w.]+)", s_code, re.I) and not local:
        return ("destructive SQL: bulk table wipe.", "DELETE with an explicit WHERE, inside a transaction")
    # The WHERE must be in THIS statement. A cross-segment relaxation used to
    # be threaded in here for a statement wrapped over real newlines, but a raw
    # newline is a splitter, so no segment can ever contain one; the
    # statement-splitting above covers the case it was written for. Letting a
    # WHERE in an unrelated -c argument count would excuse a bare DELETE.
    # A WHERE inside a comment is not a WHERE clause. `DELETE FROM users
    # /*WHERE id=1*/` and `DELETE FROM users -- WHERE id=1` both delete every
    # row, and both satisfied a bare `\bWHERE\b` over the raw text. Strip what
    # the database will ignore before asking the question, rather than adding a
    # pattern per comment syntax to every rule below.
    has_where = bool(re.search(r"\bWHERE\b", s_code, re.I))
    # A tautology is not a WHERE clause. `WHERE 1=1` and `WHERE true` delete
    # every row exactly as a bare DELETE does, and people write them precisely
    # to satisfy a tool that demands a WHERE, which makes this the most likely
    # of all the shapes to arrive by accident rather than by malice. A
    # red-team pass found both allowed.
    # The terminator has to include a closing quote. `s` is the segment as
    # written, and in SQL context the quotes around the statement are still on
    # it, so anchoring at end-of-string alone matched nothing at all.
    #
    # `WHERE 1` is MySQL's canonical always-true and was missing, as were the
    # inequality forms people reach for when a tool demands a WHERE: `2>1`,
    # `id>0`, `id IS NOT NULL`. All delete every row.
    if has_where and re.search(
            r"\bWHERE\s+(?:\(\s*)?(?:"
            r"1\s*=\s*1|true|1(?!\s*=)|'([^']*)'\s*=\s*'\1'"
            r"|\d+\s*[<>]\s*\d+"
            r"|[\w.\"`]+\s*(?:>\s*0|>=\s*0|<>\s*NULL|!=\s*NULL)"
            r"|[\w.\"`]+\s+IS\s+NOT\s+NULL"
            r")(?:\s*\))?\s*(?:;|--|/\*|[\"'`]|$)", s_code, re.I):
        has_where = False
    # `DELETE FROM` is the form safe to match ANYWHERE. A bare
    # `DELETE <word>` is not: `kubectl delete namespace x` has no FROM, and
    # matching it outside a database client read every kubectl delete as SQL.
    # The looser spellings only count once a real client set the context.
    _del = r"\bDELETE\s+FROM\b"
    if in_sql:
        _del += r"|\bDELETE\s+(?:\w+\s+)?(?:FROM\s+)?[\w.\"`\[\]]+"
    # Matched against the comment-stripped text: `DELETE/**/FROM users` is a
    # DELETE FROM to the database and was not one to this regex.
    if re.search(_del, s_code, re.I) and not has_where and not local:
        return ("unqualified DELETE (no WHERE clause: deletes every row).", "add a WHERE clause")
    # `UPDATE users u SET ...` and `UPDATE users AS u SET ...` were allowed:
    # the pattern demanded SET immediately after the table name.
    if re.search(r"\bUPDATE\s+(?:ONLY\s+)?[\w.\"`\[\]]+(?:\s+(?:AS\s+)?\w+)?\s+SET\b",
                 s_code, re.I) and not has_where and not local:
        return ("unqualified UPDATE (no WHERE clause: rewrites every row).", "add a WHERE clause")
    if re.search(r"\bprisma\s+(migrate\s+reset|db\s+push\s+.*--force-reset)", s):
        return ("prisma reset (drops and recreates the database).",
                "prisma migrate dev to create a forward migration")
    if re.search(r"\bsupabase\s+db\s+reset\b", s) and not re.search(r"--local\b", s):
        return ("supabase db reset.", "write a forward migration instead")
    return None

def check_prod_db(seg, stripped=None):
    """`stripped` is the segment with wrappers and KEY=value prefixes removed.

    The URI and env-var scans want the raw text, because the credentials live
    in the prefix. DB_CLIENT wants the stripped text, because `PGPASSWORD=x
    psql -h prod` and `sudo psql -h prod` are how people really invoke it.
    """
    inv = Invocation(seg, stripped)
    if inv.prod_host:
        return ("connection to what looks like a PRODUCTION database host "
                f"({inv.prod_host}).",
                "point at a local or staging database, or use a read replica")
    if re.search(r"\b(DATABASE_URL|DB_URL)\s*=\s*\S*://(?:[^\s'\"/@]*@)?([^\s'\"/:?]*"
                 r"(prod|production)[^\s'\"/:?]*)", seg, re.I):
        return ("production database credentials on the command line.", "use a local/staging database")
    if (re.search(r"\bsupabase\s+.*--project-ref\b", seg)
            and re.search(r"\b(db\s+push|db\s+reset|migration\s+repair)\b", seg)):
        return ("writing to a remote Supabase project.", "run against the local stack: supabase start")
    # The signal can be in the variable NAME: `psql $PROD_DATABASE_URL`.
    if inv.is_db_client:
        for m in re.finditer(r"\$\{?(\w+)\}?", seg):
            if re.search(r"(^|_)(PROD|PRODUCTION|LIVE)(_|$)", m.group(1), re.I):
                return ("a database connection taken from a variable named for production "
                        f"(${m.group(1)}).",
                        "point at a local or staging database, or use a read replica")
    return None

# check_sql is a SQL grammar, so clients whose destructive verbs are not SQL
# walked straight through it. All of these were reachable with the suite green.
NONPROD_ENV = re.compile(
    r"\b(RAILS_ENV|RACK_ENV|APP_ENV|DJANGO_SETTINGS_MODULE)\s*=\s*"
    r"[\w.]*\b(test|testing|dev|development|local)\b", re.I)

NONPROD_FLAG = re.compile(r"--env[=\s]+[\w.]*\b(test|testing|dev|development|local)\b", re.I)

class DbWipeRule:
    """client matches STRIPPED (basename, so `sudo mongosh` counts), verb
    matches RAW (escape hatches live in the prefix). honours_locality is False
    for framework tasks, which take their target from an env var instead."""

    __slots__ = ("name", "client", "client_loose", "verb", "honours_locality",
                 "reason", "fix")

    def __init__(self, name, client, verb, honours_locality, reason, fix):
        self.name = name
        self.client = re.compile(client, re.I)
        # Same pattern with the start anchor removed, for the whole-line
        # rescan. Built here so the two can never drift apart.
        self.client_loose = re.compile(
            re.sub(r"^\^\\s\*\\S\*", r"\\b", client), re.I)
        self.verb = re.compile(verb, re.I)
        self.honours_locality = honours_locality
        self.reason = reason
        self.fix = fix

DB_WIPE_RULES = (
    DbWipeRule(
        "mongo-drop-database",
        # `db.getSiblingDB("app").dropDatabase()` targets another database on the
        # same connection and was not matched by an anchor on `db.`.
        r"^\s*\S*(mongosh?|mongo)\b",
        r"\b(?:db|getSiblingDB\s*\([^)]*\))\s*\.\s*dropDatabase\s*\(", True,
        "MongoDB dropDatabase: destroys the entire database.",
        "drop a single collection you have named, against a local host"),
    DbWipeRule(
        "mongo-collection-drop",
        # `db["users"].drop()` is the same call through bracket indexing.
        r"^\s*\S*(mongosh?|mongo)\b",
        r"\bdb\s*(?:\.\s*[\w$]+|\[\s*['\"][^'\"]+['\"]\s*\])\s*\.\s*drop\s*\(", True,
        "MongoDB collection drop.",
        "write a reversible migration, or run it against a local host"),
    DbWipeRule(
        "mongo-empty-filter-delete",
        r"^\s*\S*(mongosh?|mongo)\b", r"\.\s*(deleteMany|remove)\s*\(\s*\{\s*\}\s*\)", True,
        "MongoDB delete with an empty filter: removes every document.",
        "pass a filter that names what to delete"),
    DbWipeRule(
        "redis-flush",
        r"\bredis-cli\b", r"\bFLUSH(ALL|DB)\b", True,
        "redis FLUSHALL/FLUSHDB: wipes the entire keyspace.",
        "DEL the keys you mean, or add -h localhost if this is your dev instance"),
    DbWipeRule(
        "rails-db-drop",
        # `db:migrate:reset` does what `db:reset` does and was not matched.
        r"\b(rails|rake)\b", r"\bdb:(drop|reset|purge)\b|\bdb:migrate:reset\b", False,
        "rails db:drop/db:reset: drops the database.",
        "run a forward migration, or name the environment: RAILS_ENV=test rails db:drop"),
    DbWipeRule(
        "artisan-wipe",
        # `migrate:refresh` is one character from `migrate:fresh` and rolls back
        # and re-runs every migration.
        r"\bartisan\b", r"\b(migrate:fresh|migrate:refresh|migrate:reset|db:wipe)\b", False,
        "artisan migrate:fresh/db:wipe: drops every table.",
        "run a forward migration, or name the environment: --env=testing"),
)

def db_wipe_rule_for(seg, stripped=None, anchored=True):
    """Which DB_WIPE_RULES row this trips, or None.

    Separate from check_db_wipe so a test can prove every row is reachable.

    `anchored=False` is for the whole-line rescan ONLY. The mongo rows anchor
    their client on the start of the segment so `echo mongosh` cannot count as
    an invocation, which is right per segment and wrong for a joined line where
    the client is never first. The caller that passes False has already proven
    the write-then-execute shape, so the anchor is protecting nothing there.
    """
    inv = Invocation(seg, stripped)
    # rails/artisan put their target in an env var, so naming a non-production
    # one is their equivalent of `-h localhost`.
    if NONPROD_ENV.search(inv.raw) or NONPROD_FLAG.search(inv.raw):
        return None
    for rule in DB_WIPE_RULES:
        pat = rule.client if anchored else rule.client_loose
        if not pat.search(inv.stripped):
            continue
        if not rule.verb.search(inv.raw):
            continue
        if rule.honours_locality and inv.is_local_db:
            continue
        return rule
    return None

def check_db_wipe(seg, stripped=None, anchored=True):
    """Destructive database commands whose verbs are not SQL."""
    rule = db_wipe_rule_for(seg, stripped, anchored)
    return (rule.reason, rule.fix) if rule else None
