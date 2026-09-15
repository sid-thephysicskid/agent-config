#!/usr/bin/env python3
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
    r"\b(drizzle-kit|prisma)\b[^\n]{0,40}--(force|accept-data-loss)\b",
    r"\bdeleteMany\s*\(\s*\{\s*\}\s*\)",
    r"\bdb\.\w+\.drop\s*\(\s*\)",
    r"\bdropdb\b",
)

def _quoted_runs(s):
    out = []
    for m in re.finditer(r"'([^']*)'|\"([^\"]*)\"", s):
        run = m.group(1) or m.group(2) or ""
        out.extend(part for part in run.split(";") if part.strip())
    return out

def check_sql(seg, local=None):
    if local is None:
        local = Invocation(seg).is_local_db
    if is_sql_context(seg):
        runs = _quoted_runs(seg)
        if len(runs) > 1:
            for run in runs:
                hit = check_sql(SqlFragment(run), local=local)
                if hit:
                    return hit
    in_sql = is_sql_context(seg)
    if not in_sql:
        seg = strip_quoted(seg)
    s = re.sub(r"\s+", " ", seg)
    s_code = strip_sql_comments(s)
    if re.search(r"\bDROP\s+(TABLE|DATABASE|SCHEMA|COLUMN|INDEX|OWNED\s+BY)\b",
                 s_code, re.I) and not local:
        return ("destructive SQL: DROP.",
                "write a reversible migration and apply it through your migration tool")
    if re.search(r"\bTRUNC" + r"ATE\s+(TABLE\b|ONLY\b|[\"'`\w.]+)", s_code, re.I) and not local:
        return ("destructive SQL: bulk table wipe.", "DELETE with an explicit WHERE, inside a transaction")
    has_where = bool(re.search(r"\bWHERE\b", s_code, re.I))
    if has_where and re.search(
            r"\bWHERE\s+(?:\(\s*)?(?:"
            r"1\s*=\s*1|true|1(?!\s*=)|'([^']*)'\s*=\s*'\1'"
            r"|\d+\s*[<>]\s*\d+"
            r"|[\w.\"`]+\s*(?:>\s*0|>=\s*0|<>\s*NULL|!=\s*NULL)"
            r"|[\w.\"`]+\s+IS\s+NOT\s+NULL"
            r")(?:\s*\))?\s*(?:;|--|/\*|[\"'`]|$)", s_code, re.I):
        has_where = False
    _del = r"\bDELETE\s+FROM\b"
    if in_sql:
        _del += r"|\bDELETE\s+(?:\w+\s+)?(?:FROM\s+)?[\w.\"`\[\]]+"
    if re.search(_del, s_code, re.I) and not has_where and not local:
        return ("unqualified DELETE (no WHERE clause: deletes every row).", "add a WHERE clause")
    if re.search(r"\bUPDATE\s+(?:ONLY\s+)?[\w.\"`\[\]]+(?:\s+(?:AS\s+)?\w+)?\s+SET\b",
                 s_code, re.I) and not has_where and not local:
        return ("unqualified UPDATE (no WHERE clause: rewrites every row).", "add a WHERE clause")
    if re.search(r"\bprisma\s+(migrate\s+reset|db\s+push\s+.*--force-reset)", s):
        return ("prisma reset (drops and recreates the database).",
                "prisma migrate dev to create a forward migration")
    if re.search(r"\bsupabase\s+db\s+reset\b", s) and not re.search(r"--local\b", s):
        return ("supabase db reset.", "write a forward migration instead")
    # claude-code#27063, #36183
    if re.search(r"\b(drizzle-kit\s+push|prisma\s+db\s+push)\b[^\n]*--(force|accept-data-loss)\b", s):
        return ("a schema push that accepts data loss.",
                "generate a migration and review it: drizzle-kit generate or prisma migrate dev")
    return None

def check_prod_db(seg, stripped=None):
    inv = Invocation(seg, stripped)
    if inv.prod_host:
        return ("connection to what looks like a PRODUCTION database host "
                f"({inv.prod_host}).",
                "point at a local or staging database, or use a read replica")
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

NONPROD_ENV = re.compile(
    r"\b(RAILS_ENV|RACK_ENV|APP_ENV|DJANGO_SETTINGS_MODULE)\s*=\s*"
    r"[\w.]*\b(test|testing|dev|development|local)\b", re.I)

class DbWipeRule:

    __slots__ = ("name", "client", "client_loose", "verb", "honours_locality",
                 "reason", "fix")

    def __init__(self, name, client, verb, honours_locality, reason, fix):
        self.name = name
        self.client = re.compile(client, re.I)
        self.client_loose = re.compile(
            re.sub(r"^\^\\s\*\\S\*", r"\\b", client), re.I)
        self.verb = re.compile(verb, re.I)
        self.honours_locality = honours_locality
        self.reason = reason
        self.fix = fix

DB_WIPE_RULES = (
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
)

def db_wipe_rule_for(seg, stripped=None, anchored=True):
    inv = Invocation(seg, stripped)
    if NONPROD_ENV.search(inv.raw):
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
    rule = db_wipe_rule_for(seg, stripped, anchored)
    return (rule.reason, rule.fix) if rule else None
