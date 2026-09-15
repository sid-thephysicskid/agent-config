#!/usr/bin/env python3
import os
import re
import shlex

from guard_parse import (  # noqa: F401
    asks_for_help,
    GLOBBED,
    _brace_fragments,
    _is_dot_walk,
    brace_expand,
    inline_code,
    normalize_path,
    tokens,
)
from guard_secrets import (
    is_secret_candidate,
)
from guard_git import (
    _is_whole_tree,
)

# See guard_git.MIDDLE_SIGNALS for why these live next to the rules.
MIDDLE_SIGNALS = (
    r"\brm\s+-[\w-]*[rRf]",
    # `rm -rf` was here and the find spelling of the same act was not.
    r"\bfind\b[^\n]{0,120}\s-delete\b",
    r"\bfind\b[^\n]{0,120}-exec(?:dir)?\s+(?:\S*/)?rm\b",
    r"\b(terraform|tofu|terragrunt)\b[^\n]{0,40}\bdestroy\b",
    r"\bkubectl\b[^\n]{0,60}\bdelete\b",
    r"\bgh\b[^\n]{0,40}\brepo\s+delete\b",
    r"\bgh\b[^\n]{0,60}-X\s+DELETE\b",
    r"\bgh\b[^\n]{0,60}\bpr\s+merge\b[^\n]{0,40}--admin\b",
    r"\bvercel\b[^\n]{0,30}\b(rm|remove)\b",
    r"\baws\b[^\n]{0,40}\bs3\s+r[mb]\b",
    r"\b(npm|pnpm|yarn)\b[^\n]{0,40}\bpublish\b",
    r"\btwine\b[^\n]{0,40}\bupload\b",
    r"\bgem\b[^\n]{0,40}\bpush\b",
    r"\bpoetry\b[^\n]{0,40}\bpublish\b",
    r"\b(vercel|netlify)\b[^\n]{0,80}--prod(uction)?\b",
    r"\b(fly|flyctl)\b[^\n]{0,40}\bdeploy\b",
    r"\bwrangler\b[^\n]{0,40}\b(deploy|publish)\b",
    r"\brailway\b[^\n]{0,40}\b(up|redeploy)\b",
    r"\bmigrate\s+deploy\b",
    r"\bkillall\s", r"\bpkill(?![^\n]{0,80}\s-P\b)\s", r"\btaskkill\b[^\n]{0,80}/IM\b",
    r"\b(curl|wget)\b[^\n]{0,200}\bDELETE\b",
    r"\b(gcloud|az)\b[^\n]{0,80}\sdelete\b", r"\baws\b[^\n]{0,60}\s(delete|terminate)-",
    r"\bdocker\b[^\n]{0,80}(volume\s+(rm|prune)|--volumes|down\s+-v)\b",
    r"\bchmod\b[^\n]{0,40}\s0?777\b",
    r"\b(rmdir|rd)\s+/s\b",
)

_HOME = os.path.expanduser("~")

DANGEROUS_ROOTS = {"/", _HOME, os.path.dirname(_HOME), "/Users", "/home",
                   "/etc", "/var", "/usr", "/System", "/Applications"}

def _under_system_root(base):
    return (base in DANGEROUS_ROOTS
            or (base.startswith("/") and base.count("/") <= 1)
            or bool(re.match(r"^/(private|Library|System|usr|var|etc|opt)/[^/]+/?$", base))
            or bool(re.match(r"^/(Users|home)/[^/]+/?$", base)))

def check_rm(seg):
    if re.search(r"\bfind\b.*(\s-delete\b|-exec(dir)?\s+(\S*/)?rm\b)", seg):
        mm = re.search(r"\bfind\s+(?P<root>'[^']+'|\"[^\"]+\"|\S+)", seg)
        root = normalize_path(mm.group("root")) if mm else ""
        if _under_system_root(root):
            return ("a find that deletes files in bulk under a system path.",
                    "narrow the search root, or list the matches first without -delete")
        if re.search(r"-name\s+['\"]?\.git['\"]?(\s|$)", seg) or root.endswith("/.git"):
            return ("a find that deletes .git directories (destroys the repositories).",
                    "if you meant to discard a clone, delete its parent directory instead")
    toks = tokens(seg)
    def _coreutils_rm(i):
        return os.path.basename(toks[i]) == "rm" and not any(
            os.path.basename(t) == "git" for t in toks[:i])
    rm_at = [i for i in range(len(toks)) if _coreutils_rm(i)]
    if not rm_at:
        return None
    idx = rm_at[0]
    flags = "".join(t for t in toks[idx + 1:] if t.startswith("-"))
    if not re.search(r"[rRf]", flags):
        return None
    for t in toks[idx + 1:]:
        if t.startswith("-"):
            continue
        for member in (brace_expand(t) if "{" in t else [t]):
            if "{" in member or "}" in member:
                for frag in (f for f in _brace_fragments(member)
                             if len(f) < len(member) and "{" not in f and "}" not in f):
                    hit = _rm_target_verdict(frag)
                    if hit:
                        return hit
                continue
            hit = _rm_target_verdict(member)
            if hit:
                return hit
    return None

def check_xargs_rm(cmd):
    if not re.search(r"(^|\|)\s*(xargs|parallel)\b", cmd):
        return None
    if not re.search(r"\brm\b", cmd):
        return None
    if not re.search(r"\|\s*(xargs|parallel)\b", cmd):
        return ("a bulk delete by xargs/parallel, fed from input the guard cannot see.",
                "read the list and delete the specific paths you meant")
    if any(_under_system_root(normalize_path(t)) for t in tokens(cmd)):
        return ("a bulk delete driven by xargs/parallel under a system path.",
                "narrow the producer, or list the matches first")
    if re.search(r"\bgit\b[^|]{0,60}\bls-files\b[^|]{0,60}"
                 r"(--others|(?<![\w-])-[a-zA-Z]*o[a-zA-Z]*(?=\s|$))", cmd):
        return ("a bulk delete of every untracked file, which is git clean -f "
                "by another name.",
                "delete the specific paths you meant, or use git clean -n first "
                "to see what would go")
    return None

def _glob_means_everything(comp):
    bare = re.sub(r"\[[^\]]*\]", "", comp).replace("*", "").replace("?", "")
    return bare in ("", ".")

def _rm_target_verdict(t):
    if _is_whole_tree(t) or _is_dot_walk(t):
        return ("rm -rf on the whole current directory (or its parent).",
                "name the specific subdirectory you mean, with its path")
    p = normalize_path(t)
    base = p
    if GLOBBED.search(p):
        mm = re.search(r"/([^/]*[*?\[][^/]*)/?$", p)
        if mm and _glob_means_everything(mm.group(1)):
            base = re.sub(r"/[^/]*[*?\[][^/]*/?$", "", p)
    base = normalize_path(base) if base != p else p
    if base in ("", "."):
        return ("rm -rf on the whole current directory (or the filesystem root).",
                "name the specific subdirectory you mean, with its path")
    if _under_system_root(base):
        return (f"rm -rf on '{t}', a home or system directory.",
                "delete a specific subdirectory, with the full path")
    if base == ".git" or base.endswith("/.git"):
        return ("rm -rf on a .git directory (destroys the repository).",
                "if you meant to discard a whole clone, delete its parent directory instead")
    return None

_GLOBAL_FLAGS = r"(?:\s+-{1,2}[\w-]+(?:[=\s]+[^\s-]\S*)?){0,8}"
_CMD = r"(?:^|[\s;&|(])"
_NOT_LOCAL = r"(?![^\n]{0,400}(?:localhost|127\.0\.0\.1|\[::1\])(?![\w.-]))"

DESTRUCTIVE_TOOLS = (
    (r"\bgh" + _GLOBAL_FLAGS + r"\s+repo\s+delete\b", "deleting a GitHub repository",
     "do this in the web UI, deliberately"),
    # PocketOS/Railway volume delete, theregister.com 2026/04/27
    (r"(?:\bgh" + _GLOBAL_FLAGS + r"\s+api\b|" + _CMD + r"(?:curl|wget)\s" + _NOT_LOCAL + r")"
     r"[^\n]{0,400}(?:-X\s*|--request[=\s]+|--method[=\s]+)['\"]?DELETE\b"
     r"|" + _CMD + r"(?:https?|xh)\s" + _NOT_LOCAL + r"(?:\s*-\S+)*\s*DELETE\s"
     r"|" + _CMD + r"(?:curl|wget|https?|xh)\s[^\n]{0,400}\b(?:volume|service|project|environment|database)Delete\b",
     "an API call that deletes remote resources",
     "do it in the provider's dashboard, deliberately, or target localhost"),
    # DataTalks.Club terraform (AIID 1424), Kiro (AIID 1442)
    (_CMD + r"(?:gcloud|az)(?:\s+[\w.=:/-]+){1,6}\s+delete\b"
     r"|\baws" + _GLOBAL_FLAGS + r"\s+(?:rds|ec2|dynamodb|ecs|eks|lambda|cloudformation|s3api)"
     r"\s+(?:delete|terminate)-[\w-]+(?![^\n]*--dry-run\b)",
     "deleting a cloud resource", "do this in the cloud console, deliberately"),
    # claude-code#63644
    (r"\bdocker(?:-compose\b|" + _GLOBAL_FLAGS + r"\s+compose\b)[^\n]{0,200}\sdown\b[^\n]{0,200}\s(?:-v|--volumes)\b"
     r"|\bdocker" + _GLOBAL_FLAGS + r"\s+(?:volume\s+(?:rm|remove|prune)\b|system\s+prune\b[^\n]{0,200}--volumes\b)",
     "deleting Docker volumes (the local database lives there)",
     "docker compose down without -v, or remove the one volume you named"),
    # claude-code#2782, #3068, #20718
    (_CMD + r"(?:killall\s|pkill(?![^\n]*\s-P\b)\s|taskkill\s[^\n]{0,200}/IM\b)",
     "killing processes by name (takes down every match, the agent included)",
     "kill the specific PID: kill $(lsof -ti :PORT)"),
    # claude-code#168
    (r"\b(?:chmod|chown)(?=[^\n]{0,300}\s(?:-[a-z]*R|--recursive)\b)[^\n]{0,300}\s"
     r"(?:0?777\b|[\"']?(?:/(?:usr|etc|var|bin|lib|opt|System|Library)?|~|\$HOME|\$\{HOME\})/?[\"']?(?=\s|$))",
     "a recursive permission change on a system or home root, or to 777",
     "name the project directory, with a mode narrower than 777"),
    # Google Antigravity drive wipe (techradar), openai/codex#43343
    (_CMD + r"(?:rmdir|rd)(?=\s)(?=[^\n]{0,200}\s/s\b)[^\n]{0,200}\s[\"']?(?:[a-z]:\\?|%userprofile%)[\"']?(?=\s|$)"
     r"|\bremove-item(?=[^\n]{0,200}\s-r(?:ecurse)?\b)[^\n]{0,200}\s[\"']?"
     r"(?:[a-z]:\\?|~|\$home|\$env:userprofile)[\"']?(?=\s|$)",
     "deleting a whole drive or home directory",
     "name the project subdirectory, with its full path"),
    (r"\bgh" + _GLOBAL_FLAGS + r"\s+pr\s+merge\b.*--admin\b",
     "merging a PR with --admin (bypasses required checks)",
     "let CI pass, or ask the human to override"),
    (r"\b(terraform|tofu|terragrunt)" + _GLOBAL_FLAGS + r"(\s+run-all)?" +
     _GLOBAL_FLAGS + r"\s+destroy\b",
     "terraform destroy (tears down infrastructure)",
     "run terraform plan -destroy and show it first"),
    (r"\b(terraform|tofu|terragrunt)" + _GLOBAL_FLAGS + r"(\s+run-all)?" +
     _GLOBAL_FLAGS + r"\s+apply\b.*\s-destroy\b",
     "terraform apply -destroy (tears down infrastructure)",
     "run terraform plan -destroy and show it first"),
    (r"\bkubectl" + _GLOBAL_FLAGS + r"\s+delete" + _GLOBAL_FLAGS +
     r"\s+(namespaces?|ns|deployments?|deploy|statefulsets?|sts"
     r"|pvcs?|persistentvolumeclaims?|daemonsets?|ds|replicasets?|rs)"
     r"(\b|/)"
     r"(?![^\n]*--dry-run=(client|server)\b)",
     "deleting a Kubernetes resource",
     "scale to zero first, or do it deliberately outside the agent"),
    # aws spells it `--dryrun`, one word.
    (r"\baws" + _GLOBAL_FLAGS + r"\s+s3\s+rm\b(?![^\n]*--dry-?run\b).*--recursive",
     "recursive S3 deletion", "list the keys first, then delete specific ones"),
    (r"\baws" + _GLOBAL_FLAGS + r"\s+s3\s+rb\b",
     "removing an S3 bucket and its contents", "empty it deliberately outside the agent"),
    (r"\bvercel" + _GLOBAL_FLAGS + r"\s+(rm|remove)\b",
     "removing a Vercel deployment or project", "do this in the dashboard, deliberately"),
    (r"\bdropdb\b", "dropdb", "write a forward migration instead"),
    (r"\b(npm|pnpm|bun)" + _GLOBAL_FLAGS + r"\s+publish\b(?![^\n]*--dry-run(?![-\w=]))",
     "publishing to the npm registry (irreversible)",
     "let the tag-triggered CI workflow publish, or ask the human to run it"),
    (r"\byarn" + _GLOBAL_FLAGS + r"\s+(npm\s+)?publish\b(?![^\n]*--dry-run(?![-\w=]))",
     "publishing to the npm registry via yarn (irreversible)",
     "let the tag-triggered CI workflow publish, or ask the human to run it"),
    (r"\b(twine\s+upload|gem\s+push|poetry" + _GLOBAL_FLAGS + r"\s+publish)\b"
     r"(?![^\n]*--dry-run(?![-\w=]))",
     "publishing to a package registry (irreversible)",
     "let the tag-triggered CI workflow publish, or ask the human to run it"),
)

INLINE_DESTRUCTIVE = re.compile(
    r"\b(shutil\s*\.\s*rmtree|os\s*\.\s*(remove|unlink|rmdir)"
    r"|Path\s*\([^)]*\)\s*\.\s*unlink|unlink\s+glob|File\s*\.\s*delete"
    r"|rmSync|rmdirSync|unlinkSync"
    r"|FileUtils\s*\.\s*rm_rf|Dir\s*\.\s*rmdir)", re.I)

def check_inline_code(seg, code=None):
    code = inline_code(seg) if code is None else code
    if not code:
        return None
    literals = re.findall(r"['\"]([^'\"]{1,300})['\"]", code)
    if INLINE_DESTRUCTIVE.search(code):
        for lit in literals:
            t = normalize_path(lit)
            stem = re.sub(r"/?\*+$", "", t) or t
            if _is_dot_walk(lit) or _under_system_root(t) or _under_system_root(stem) \
                    or check_rm("rm -rf " + shlex.quote(lit)):
                return ("an inline program deleting a system or home directory.",
                        "name the specific subdirectory, and run it as a script you can read")
    for lit in literals:
        if is_secret_candidate(lit):
            return (f"an inline program reading '{lit}', which holds live secrets.",
                    "use the .example variant; never read or print the real values")
    return None

_DEPLOY_FIX = ("merge the PR and let the pipeline deploy, or run this yourself")

_READ_ONLY_SUB = (r"(?![^\n]{0,40}(?<![-\w])(logs?|ls|list|inspect|env|whoami|domains|"
                  r"certs|alias|link|pull|build|status|open|sites|dev)\b)")

PRODUCTION_DEPLOYS = (
    # Needs a production flag; without it these deploy a preview.
    (r"\bvercel\b" + _READ_ONLY_SUB + r"[^\n]{0,80}--prod(uction)?\b",
     "a Vercel production deploy"),
    (r"\bnetlify\b" + _READ_ONLY_SUB + r"[^\n]{0,80}--prod(uction)?\b",
     "a Netlify production deploy"),
    # Ships to production by default. The bare verb is the dangerous one.
    (r"\b(fly|flyctl)" + _GLOBAL_FLAGS + r"\s+deploy\b", "a Fly.io deploy (production by default)"),
    (r"\bwrangler" + _GLOBAL_FLAGS + r"\s+(deploy|publish)\b",
     "a Cloudflare Workers deploy (production by default)"),
    (r"\brailway" + _GLOBAL_FLAGS + r"\s+(up|redeploy)\b", "a Railway deploy (production by default)"),
    (r"\bprisma\b[^\n]{0,40}\bmigrate\s+deploy\b",
     "applying migrations to a live database"),
)

NON_PRODUCTION = re.compile(
    r"--(env|environment|stage)[=\s]+(?!\S*(prod|production|live))\S+",
    re.I)

NON_PROD_NAMED = re.compile(
    r"--(config|profile)[=\s]+\S*"
    r"(staging|stage|dev|develop|test|preview|sandbox|local|qa|ephemeral)",
    re.I)

EXPLICIT_PROD = re.compile(r"--prod(uction)?\b", re.I)

def check_deploy(seg):
    if not EXPLICIT_PROD.search(seg) and (
            NON_PRODUCTION.search(seg) or NON_PROD_NAMED.search(seg)):
        return None
    for pat, what in PRODUCTION_DEPLOYS:
        if re.search(pat, seg, re.I):
            return (what + ", which skips CI, review and branch protection.", _DEPLOY_FIX)
    return None

def check_tools(seg):
    if asks_for_help(seg):
        return None
    hit = check_deploy(seg)
    if hit:
        return hit
    for pat, what, fix in DESTRUCTIVE_TOOLS:
        if re.search(pat, seg, re.I):
            return (what, fix)
    return None
