#!/usr/bin/env python3
import re

from guard_parse import (
    GLOBBED,
    _brace_fragments,
    blank_inert_heredocs,
    brace_expand,
    normalize_path,
    tokens,
)

# See guard_git.MIDDLE_SIGNALS for why these live next to the rules.
MIDDLE_SIGNALS = (
    r"(^|[\s'\"=/(])\.env(?![\w-])",
    r"\.(ssh|aws|kube|gnupg|docker)/",
    r"id_(rsa|ed25519|ecdsa|dsa)",
    r"\.(netrc|pgpass|npmrc|pypirc|git-credentials)\b",
    r"\.(pem|p12|pfx|jks|keystore)\b",
    r"\bcredentials\.json\b",
    r"\bsecrets\.(ya?ml|json|toml)\b",
    r"/proc/[^/\s]+/environ\b",
)

# claude-code#62156, #30731, #32523
ENV_DUMP = re.compile(r"^\s*(?:printenv|env|set|export)(?:\s+-[0p])?\s*$")
_SECRET_NAME = r"[A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL)S?\b(?!:?[+?])"
SECRET_PRINT = re.compile(
    r"^\s*(?:printenv\s+" + _SECRET_NAME + r"|(?:echo|printf)\b[^\n]*\$\{?" + _SECRET_NAME + ")")

def check_env_print(raw, line):
    if ENV_DUMP.match(raw):
        return ("printing the whole environment, which holds live secrets.",
                "print the one variable you need, e.g. printenv PATH, or test it with [ -n \"$VAR\" ]")
    if re.search(r"/proc/[^/\s]+/environ\b", raw):
        return ("reading a process /environ file, which holds live secrets.",
                "print the one variable you need by name")
    # Fed to a pipe or a file, the value never reaches the transcript.
    rest = line[line.find(raw) + len(raw):]
    if SECRET_PRINT.match(re.sub(r"'[^']*'", "''", raw)) and ">" not in raw \
            and not re.match(r"\s*\|(?!\|)", rest):
        return ("printing a secret variable into the transcript.",
                "test that it is set instead: [ -n \"$VAR\" ] && echo set")
    return None

SECRET_FIX = ("use the .example variant for variable names; never read, copy, "
              "or print the real values")

SAFE_SUFFIX = re.compile(r"\.(example|sample|template|dist|tpl)$", re.I)

ENVISH = re.compile(r"(^|/)\.env(\.[\w.-]+)?$", re.I)

SECRET_FILE = re.compile(
    r"(^|/)(\.env(\.[\w.-]+)?"
    r"|\.envrc"
    r"|secrets?\.(ya?ml|json|toml)"
    r"|credentials\.json"
    r"|\.netrc|\.pgpass|\.git-credentials|\.terraformrc"
    r"|\.config/git/credentials"
    r"|\.config/gcloud/application_default_credentials\.json"
    r"|[\w.-]*\.env"
    r"|\.config/gh/hosts\.yml|\.config/gcloud/credentials\.db"
    r"|\.config/rclone/rclone\.conf|\.gem/credentials|\.cargo/credentials(\.toml)?"
    r"|serviceaccount(-[\w.-]+)?\.json|firebase-adminsdk[\w.-]*\.json"
    r"|id_(rsa|ed25519|ecdsa)"
    r"|\.aws(/(credentials|config))?"
    r"|\.kube(/config)?"
    r"|\.docker(/config\.json)?"
    r"|\.gnupg(/[\w.-]+)?"
    r"|\.ssh(/(id_[\w-]+|config|known_hosts|authorized_keys))?"
    r"|\.npmrc|\.pypirc"
    r"|.*\.(p12|pfx|keystore|jks))$",
    re.I,
)

KEYISH = re.compile(
    r"(^|/)[^/]{0,120}(private|secret|priv|signing|master|api|deploy)[^/]{0,120}\.key$", re.I)

PEMISH = re.compile(r"(^|/)[^/]{0,120}\.pem$", re.I)

PUBLIC_CERT = re.compile(
    r"(^|/)(ca|ca-bundle|ca-certificates|cacert|cert|chain|fullchain)\.(pem|crt|cer)$"
    r"|^/etc/(ssl|pki)/|^/usr/(share|local/share)/ca", re.I)

SECRET_DIR = re.compile(
    r"(^|/)\.(ssh|aws|kube|docker|gnupg)/"
    r"|^(/var)?/run/secrets(/|$)", re.I)

READ_SAFE_SECRET = re.compile(
    r"(^|/)\.ssh/(config|known_hosts(\.old)?)$"
    r"|(^|/)\.aws/config$", re.I)

# The exemption applies to these and nothing else.
PURE_READER = re.compile(
    r"^\s*\S*(cat|bat|less|more|head|tail|grep|rg|ag|egrep|fgrep|diff|wc|awk)\b")

# Trailing shell noise on an otherwise clean path: `cat .env*`, `cat .env#`.
GLOB_TRAIL = re.compile(r"[*?\[\]{}#,]+$")

GLOB_LEAD = re.compile(r"^[*?\[\]{}]+")

CANDIDATE_SPLIT = re.compile(r"""[\s'"=()<>`$;|&!,]+""")

MAX_CANDIDATES = 4000

MAX_SUBSTITUTIONS = 500

BACKUP_SUFFIX = re.compile(r"\.(bak|old|orig|save|backup|copy|[0-9]+)$", re.I)

def _is_secret_path(p):
    if SAFE_SUFFIX.search(p) or PUBLIC_CERT.search(p):
        return False
    stripped = BACKUP_SUFFIX.sub("", p)
    if stripped != p and not SAFE_SUFFIX.search(stripped) \
            and not PUBLIC_CERT.search(stripped) and _is_secret_path(stripped):
        return True
    if SECRET_DIR.search(p) and not READ_SAFE_SECRET.search(p) \
            and not p.endswith(".pub"):
        return True
    return bool(ENVISH.search(p) or SECRET_FILE.search(p) or KEYISH.search(p) or PEMISH.search(p))

_TRUNCATABLE = (".env", ".envrc", ".netrc", ".pgpass", ".git-credentials",
                "credentials", "credentials.json", "id_rsa", "id_ed25519",
                "secrets.yaml", "secrets.yml", "secrets.json")

def _is_truncated_secret(stem):
    name = stem.rsplit("/", 1)[-1]
    if len(name) < 3:
        return False
    return any(n.startswith(name) and n != name for n in _TRUNCATABLE)

UPLOAD_AT = re.compile(r"^[^=]*=?@(?=.)")

def is_secret_candidate(tok):
    tok = UPLOAD_AT.sub("", tok, count=1)
    if "{" in tok and "}" in tok:
        for part in brace_expand(tok):
            if "{" in part or "}" in part:
                if any(is_secret_candidate(f) for f in _brace_fragments(part)
                       if len(f) < len(part) and "{" not in f and "}" not in f):
                    return True
                continue
            if part != tok and is_secret_candidate(part):
                return True
        return False
    p = normalize_path(tok)
    if len(p) > 512:
        p = p[-512:]
    if _is_secret_path(p):
        return True
    stem = GLOB_LEAD.sub("", GLOB_TRAIL.sub("", p))
    if stem and stem != p and _is_secret_path(stem):
        return True
    if stem and stem != p and _is_truncated_secret(stem):
        return True
    if not GLOBBED.search(p):
        return False
    # A public key is not a secret, and `cat ~/.ssh/*.pub` is a real command.
    if p.endswith(".pub"):
        return False
    return bool(SECRET_DIR.search(p))

SAFE_COPY = re.compile(r"^\s*(cp|mv|install|cat)\b")

PKG_RUNNER = re.compile(
    r"^\s*(npx|pnpx|bunx"
    r"|(pnpm|yarn|bun)\s+(exec|dlx|run)"
    r"|(uv|poetry|pipenv|rye|hatch|pdm)\s+run)\s+")

SSH_KEYGEN = re.compile(r"^\s*ssh-keygen\b")

SSH_IDENTITY = re.compile(r"^\s*(ssh|scp|sftp|ssh-add|ssh-copy-id)\b")

SSH_KEY_TOOL = re.compile(r"^\s*(ssh-add|ssh-copy-id)\b")

EXISTENCE_TEST = re.compile(r"^\s*(test|\[\[?)\s+(!\s+)?-[efdrswx]\b")

# Metadata-only operations. They never read contents.
METADATA_ONLY = re.compile(r"^\s*(ls|stat|chmod|chown|mkdir|touch|file|wc|find)\b")

NON_DISCLOSING = re.compile(
    r"^\s*("
    r"rm|unlink|shred|rmdir"
    r"|vi|vim|nvim|nano|emacs|micro|hx|helix|pico|code|codium|subl|open"
    r"|direnv"
    r"|git\s+(check-ignore|status|ls-files|rm)"
    r")\b")

FIND_ACTS = re.compile(r"\s-(exec|execdir|ok|okdir|delete|fprint|fprintf|fls)\b")

EXCLUDES_CAPABLE = re.compile(
    r"^\s*(\S*/)?(rsync|tar|grep|rg|ag|ack|find|zip|aws|gsutil|rclone|diff)\b")

EXCLUDE_X_CAPABLE = re.compile(r"^\s*(\S*/)?(diff|zip)\b")

EXCLUDE_FLAG = re.compile(r"^--(exclude|ignore|exclude-from|exclude-tag)(=|$)")

def _substitution_bodies(seg, quote_aware=True):
    out, i, n = [], 0, len(seg)
    in_single = in_double = False
    while i < n and len(out) < MAX_SUBSTITUTIONS:
        if quote_aware and in_single:
            if seg[i] == "'":
                in_single = False
            i += 1
            continue
        if quote_aware and seg[i] == "'" and not in_double:
            in_single = True
            i += 1
            continue
        if quote_aware and seg[i] == '"':
            in_double = not in_double
            i += 1
            continue
        if seg.startswith("$(", i):
            depth, j = 1, i + 2
            while j < n and depth:
                if seg[j] == "(":
                    depth += 1
                elif seg[j] == ")":
                    depth -= 1
                j += 1
            out.append(seg[i + 2:j - 1 if depth == 0 else n])
            i = j
        elif seg[i] == "`":
            j = seg.find("`", i + 1)
            if j == -1:
                out.append(seg[i + 1:])
                break
            out.append(seg[i + 1:j])
            i = j + 1
        else:
            i += 1
    if quote_aware and in_single:
        return _substitution_bodies(seg, quote_aware=False)
    return out

def check_substitutions(seg):
    inner = " ".join(_substitution_bodies(seg))
    if not inner.strip():
        return None
    # A heredoc body inside a substitution is content, not a command.
    inner = blank_inert_heredocs(inner)
    for tok in CANDIDATE_SPLIT.split(inner)[:MAX_CANDIDATES]:
        if tok and is_secret_candidate(tok):
            return (f"a command substitution reading '{tok}', which holds live secrets.",
                    SECRET_FIX)
    return None

PATTERN_FIRST_OPERAND = re.compile(r"^\s*\S*(grep|rg|ag|ack|fgrep|egrep|rga)\b")

def _read_safe(head, seg, tok):
    if ">" in seg:
        return False
    if not PURE_READER.match(head):
        return False
    return bool(READ_SAFE_SECRET.search(normalize_path(tok)))

def check_secrets_cmd(seg, loose=True, piped=False, stripped=None):
    head = seg if stripped is None else stripped
    head = PKG_RUNNER.sub("", head)
    if SSH_KEYGEN.match(head) or EXISTENCE_TEST.match(head) or SSH_KEY_TOOL.match(head):
        return None
    identity_flags = set()
    if re.match(r"^\s*(kubectl|helm|k9s|aws|gcloud|az|docker)\b", head):
        identity_flags |= {"--kubeconfig", "--config", "--config-file"}
    if re.match(r"^\s*(docker|docker-compose|podman|dotenv|nx|turbo|pm2)\b", head):
        identity_flags |= {"--env-file", "--env_file", "-e", "--environment"}
    if SSH_IDENTITY.match(head):
        identity_flags |= {"-i", "-F", "--identity", "--identity-file"}
    if re.match(r"^\s*(curl|wget)\b", head):
        identity_flags |= {"--cacert", "--capath",
                           "--ca-certificate", "--ca-directory"}
        for flag in ("--key", "--cert"):
            identity_flags.discard(flag)
    if METADATA_ONLY.match(head) and not FIND_ACTS.search(seg) and not piped:
        return None
    if NON_DISCLOSING.match(head) and not piped:
        return None
    search_pattern = None
    if PATTERN_FIRST_OPERAND.match(head):
        for tok in tokens(seg)[1:]:
            if tok.startswith("-"):
                continue
            search_pattern = tok
            break
    if SAFE_COPY.match(head):
        args = [normalize_path(x) for x in tokens(seg)[1:]
                if not x.startswith("-") and x not in (">", ">>", "<", "|")]
        if len(args) >= 2 and SAFE_SUFFIX.search(args[-2]) \
                and not any(_is_secret_path(a) for a in args[:-1]) \
                and (ENVISH.search(args[-1]) or not _is_secret_path(args[-1])):
            return None
    toks = tokens(seg)
    for i, tok in enumerate(toks):
        p = normalize_path(tok)
        if len(p) > 512:
            p = p[-512:]
        if i and toks[i - 1] in identity_flags:
            continue
        if "=" in tok and tok.split("=", 1)[0] in identity_flags:
            continue
        # the value of an exclude flag, in either `--exclude=X` or `--exclude X`
        if EXCLUDES_CAPABLE.match(head) and (
                EXCLUDE_FLAG.match(tok)
                or (i and EXCLUDE_FLAG.match(toks[i - 1]) and "=" not in toks[i - 1])
                or (i and toks[i - 1] == "-x" and EXCLUDE_X_CAPABLE.match(head))):
            continue
        if is_secret_candidate(tok):
            if _read_safe(head, seg, tok):
                continue
            if search_pattern is not None and tok == search_pattern:
                continue        # the pattern being searched for, not a file
            return (f"a command touching '{tok}', which holds live secrets.",
                    SECRET_FIX)
    loose_seg = seg
    if EXCLUDES_CAPABLE.match(head):
        loose_seg = re.sub(r"--(exclude|ignore|exclude-from|exclude-tag)(=|\s+)\S+", " ", seg)
    if EXCLUDE_X_CAPABLE.match(head):
        loose_seg = re.sub(r"(^|\s)-x(=|\s+)\S+", " ", loose_seg)
    if identity_flags:
        loose_seg = re.sub(
            r"(^|\s)(" + "|".join(re.escape(f) for f in sorted(identity_flags))
            + r")(=|\s+)\S+", " ", loose_seg)
    if re.match(r"^\s*(dotenv|docker|docker-compose|podman|pm2)\b", head):
        loose_seg = re.sub(r"(^|\s)-e(=|\s+)\S+", " ", loose_seg)
    if loose:
        for cand in CANDIDATE_SPLIT.split(loose_seg)[:MAX_CANDIDATES]:
            if cand and is_secret_candidate(cand):
                if _read_safe(head, seg, cand):
                    continue
                return (f"a command touching '{cand}', which holds live secrets.",
                        SECRET_FIX)
    return None
