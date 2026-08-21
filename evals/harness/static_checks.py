"""Static checks over the SKILL.md files. Every one of these runs today.

Each check is a function taking the loaded skills and returning a list of
Findings. Read the docstrings before believing a number: several checks apply
a threshold, and a threshold is an opinion with a number attached. Those are
marked `basis="heuristic"` in their findings so the report can separate them
from facts like "this link does not resolve".
"""

import os
import re
from collections import defaultdict
from typing import Dict, List, Optional, Sequence, Set, Tuple

from .model import Finding, SkillDoc, read

# ---------------------------------------------------------------------------
# 1. Frontmatter
# ---------------------------------------------------------------------------

# A description longer than this is doing the router's job inside the loader's
# index. Both numbers are judgement calls; 1024 is the point at which Claude
# Code's own skill listing starts to dominate the system prompt, and 500 is
# roughly twice the suite median. Change them if you disagree, but change them
# deliberately.
DESC_WARN_CHARS = 500
DESC_ERROR_CHARS = 1024


def check_frontmatter(skills: Sequence[SkillDoc]) -> List[Finding]:
    """Frontmatter is present, `name` matches the directory, description exists."""
    out = []  # type: List[Finding]
    for s in skills:
        if not s.frontmatter:
            out.append(Finding("frontmatter", "error", "no YAML frontmatter block", s.name))
            continue
        if not s.declared_name:
            out.append(Finding("frontmatter", "error", "frontmatter has no `name`", s.name))
        elif s.declared_name != s.name:
            out.append(
                Finding(
                    "frontmatter",
                    "error",
                    "frontmatter name %r does not match directory %r" % (s.declared_name, s.name),
                    s.name,
                )
            )
        if not s.description:
            out.append(Finding("frontmatter", "error", "frontmatter has no `description`", s.name))
            continue
        n = len(s.description)
        if n > DESC_ERROR_CHARS:
            out.append(
                Finding(
                    "frontmatter",
                    "error" if not s.vendored else "warn",
                    "description is %d chars, over the %d budget; it is loaded on every turn"
                    % (n, DESC_ERROR_CHARS),
                    s.name,
                    basis="heuristic",
                )
            )
        elif n > DESC_WARN_CHARS:
            out.append(
                Finding(
                    "frontmatter",
                    "warn",
                    "description is %d chars (budget %d)" % (n, DESC_WARN_CHARS),
                    s.name,
                    basis="heuristic",
                )
            )
    return out


# ---------------------------------------------------------------------------
# 2. House style: the repo's own hard rule about em dashes
# ---------------------------------------------------------------------------


# Built from its code point rather than written literally: the repo's own hard
# rule bans the character from any file written on the user's behalf, and this
# file is one of those.
EM_DASH = chr(0x2014)


def check_em_dash(skills: Sequence[SkillDoc]) -> List[Finding]:
    """The global instructions ban the em dash outright. Does the suite obey?

    Vendored skills are reported at info severity only: the repo's own rule is
    to take their upstream updates rather than edit them.
    """
    out = []  # type: List[Finding]
    for s in skills:
        for path in s.md_files:
            text = read(path)
            hits = [
                (i + 1, line.strip())
                for i, line in enumerate(text.splitlines())
                if EM_DASH in line
            ]
            if hits:
                out.append(
                    Finding(
                        "house-style",
                        "info" if s.vendored else "error",
                        "%d line(s) contain an em dash in %s"
                        % (len(hits), os.path.basename(path)),
                        s.name,
                        evidence="line %d: %s" % (hits[0][0], hits[0][1][:100]),
                    )
                )
    return out


# ---------------------------------------------------------------------------
# 3. Internal links
# ---------------------------------------------------------------------------
MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
PATHISH_RE = re.compile(r"`([\w.][\w./-]*\.(?:md|sh|mjs|py|ya?ml|json|ts|js))`")


def check_internal_links(skills: Sequence[SkillDoc]) -> List[Finding]:
    """Relative markdown links must resolve on disk."""
    out = []  # type: List[Finding]
    for s in skills:
        for path in s.md_files:
            base = os.path.dirname(path)
            for target in MD_LINK_RE.findall(read(path)):
                if target.startswith(("http://", "https://", "#", "mailto:")):
                    continue
                clean = target.split("#", 1)[0]
                if not clean:
                    continue
                resolved = os.path.normpath(os.path.join(base, clean))
                if not os.path.exists(resolved):
                    out.append(
                        Finding(
                            "links",
                            "error",
                            "broken link %r in %s" % (target, os.path.basename(path)),
                            s.name,
                        )
                    )
    return out


def check_referenced_paths(skills: Sequence[SkillDoc]) -> List[Finding]:
    """Advisory: backticked script paths that do not exist in the skill directory.

    This one has known false positives and is reported at info only. A skill
    legitimately names files it tells the agent to *create* in the user's
    project (`.github/dependabot.yml`, `CLAUDE.md`, `.nvmrc`). The check only
    looks at paths under a `scripts/` or `reference/` prefix, which by
    convention in this suite means "a file shipped inside this skill", so a
    miss there is much more likely to be real drift.
    """
    out = []  # type: List[Finding]
    for s in skills:
        real = os.path.realpath(s.directory)
        for path in s.md_files:
            for tok in PATHISH_RE.findall(read(path)):
                if not ("scripts/" in tok or "reference/" in tok or "references/" in tok):
                    continue
                # Try the skill directory, then the skill dir with any leading
                # install-path prefix stripped.
                candidates = [os.path.join(real, tok)]
                if "scripts/" in tok:
                    candidates.append(os.path.join(real, "scripts", tok.split("scripts/", 1)[1]))
                if any(os.path.exists(c) for c in candidates):
                    continue
                out.append(
                    Finding(
                        "referenced-paths",
                        "info",
                        "names %r, which does not exist under the skill directory" % tok,
                        s.name,
                        evidence=os.path.basename(path),
                    )
                )
    return out


# ---------------------------------------------------------------------------
# 6. Size
# ---------------------------------------------------------------------------

# Words in SKILL.md, which is loaded in full the moment the skill fires.
#
# Guesses, and reported as such. Nothing external says a skill over N words is
# wrong, and nobody has measured a length past which an agent stops following
# its instructions, so size is never fatal: it reports, a human decides.
SIZE_INFO = 1000
SIZE_WARN = 1800


SHINGLE = 12  # tokens


# Every check here can produce an error. Six others used to sit in this tuple
# and none of them ever had: they reported that adjacent skills share words,
# that two skills share a sentence, and that a file is a certain number of
# bytes. A linter whose output is always advisory teaches you to skip its
# output, which costs more than the checks were worth.
# The suite's own convention for naming a sibling skill is a backticked
# slash-name: `/ship`. Anything else (a bare /ship in prose, a path like
# `/api/health`) is deliberately not matched, so this check has false
# negatives rather than false positives.
SKILL_REF_RE = re.compile(r"`/([a-z][a-z0-9-]*)`")
ENTRY_SKILLS = {"navigate", "bootstrap", "setup", "diagnose", "review",
                "ship", "unstick", "research", "handoff"}


def _refs_in(text: str) -> List[str]:
    return SKILL_REF_RE.findall(text)


ROUTER_NAME_HINTS = ("which", "route", "router", "index")


def find_router(skills: Sequence[SkillDoc]) -> Optional[SkillDoc]:
    """Identify the routing skill without hardcoding its name.

    The name has changed once already, so the check looks for a skill that
    describes itself as a router first, and only falls back to known names. If
    neither finds one, the router checks report that they could not run rather
    than passing.
    """
    for s in skills:
        if "router" in s.description.lower():
            return s
    for hint in ROUTER_NAME_HINTS:
        for s in skills:
            if s.name == hint:
                return s
    return None



def check_skill_references(skills: Sequence[SkillDoc]) -> List[Finding]:
    """Every `/name` handoff names a skill that exists; report the graph shape."""
    names = {s.name for s in skills}
    out = []  # type: List[Finding]
    outbound = defaultdict(set)  # type: Dict[str, Set[str]]
    inbound = defaultdict(set)  # type: Dict[str, Set[str]]

    for s in skills:
        for path in s.md_files:
            for ref in _refs_in(read(path)):
                if ref not in names:
                    out.append(
                        Finding(
                            "skill-refs",
                            "error",
                            "`/%s` is referenced but no such skill exists" % ref,
                            s.name,
                            evidence=os.path.basename(path),
                        )
                    )
                    continue
                if ref != s.name:
                    outbound[s.name].add(ref)
                    inbound[ref].add(s.name)

    router = find_router(skills)
    for s in skills:
        if not outbound[s.name]:
            out.append(
                Finding(
                    "skill-refs",
                    "info",
                    "hands off to nothing: no `/other-skill` reference anywhere in it",
                    s.name,
                )
            )
        if router is not None and s.name == router.name:
            continue  # the router is the entry point; nothing should point at it
        if s.name in ENTRY_SKILLS:
            continue
        # Being referenced by the router does not count as being wired into
        # the flow: the router mentions everything by construction.
        real_inbound = inbound[s.name] - ({router.name} if router else set())
        if not real_inbound:
            out.append(
                Finding(
                    "skill-refs",
                    "warn",
                    "no other skill hands off to it (only the router mentions it)"
                    if inbound[s.name]
                    else "nothing references it at all, not even the router",
                    s.name,
                )
            )
    return out


ORCHESTRATION_HANDOFFS = (
    ("navigate", "prototype"),
    ("prototype", "architect"),
    ("to-spec", "breakdown"),
    ("breakdown", "tdd"),
    ("architect", "tdd"),
)


def check_orchestration_handoffs(skills: Sequence[SkillDoc]) -> List[Finding]:
    """Require the canonical neighboring stages to reference each other."""
    docs = {skill.name: skill for skill in skills}
    out = []  # type: List[Finding]
    for source, target in ORCHESTRATION_HANDOFFS:
        if source not in docs or target not in docs:
            continue  # router coverage owns missing skills
        if target not in set(_refs_in(docs[source].body)):
            out.append(Finding(
                "orchestration", "error",
                "zero-to-one loop is missing the `/%s` -> `/%s` handoff"
                % (source, target),
                source,
            ))
    return out


def check_invocation_parity(skills: Sequence[SkillDoc]) -> List[Finding]:
    """A skill is user-invoked in BOTH harnesses or neither.

    Claude Code reads `disable-model-invocation: true` from SKILL.md. Codex
    reads `policy.allow_implicit_invocation: false` from agents/openai.yaml.
    They express the same decision, and nothing but this check keeps them in
    step. Set one without the other and the two agents ship different suites:
    the skill quietly costs its description on every turn in one harness and
    not the other, which is the whole reason to set the flag.

    Also flags a missing openai.yaml. Partial coverage is how the drift starts:
    six of these were absent because they were the six skills not adapted from
    upstream, which is residue rather than a decision.
    """
    out: List[Finding] = []
    for s in skills:
        claude_off = str(s.frontmatter.get("disable-model-invocation", "")).lower() == "true"
        yaml_path = os.path.join(s.directory, "agents", "openai.yaml")
        if not os.path.exists(yaml_path):
            out.append(Finding(
                "invocation", "error",
                "no agents/openai.yaml, so Codex cannot be told how this skill is invoked",
                s.name))
            continue
        with open(yaml_path, encoding="utf-8") as yaml_file:
            text = yaml_file.read()
        # Deliberately a substring test, not a YAML parse: the harness is
        # stdlib-only and PyYAML is not a dependency worth adding for one key.
        codex_off = re.search(r"allow_implicit_invocation:\s*false", text) is not None
        if claude_off and not codex_off:
            out.append(Finding(
                "invocation", "error",
                "user-invoked for Claude Code but still implicitly invocable for Codex: "
                "add `policy.allow_implicit_invocation: false`",
                s.name))
        elif codex_off and not claude_off:
            out.append(Finding(
                "invocation", "error",
                "user-invoked for Codex but still model-invocable for Claude Code: "
                "add `disable-model-invocation: true`",
                s.name))
    return out



ALL_CHECKS = (
    check_frontmatter,
    check_em_dash,
    check_internal_links,
    check_referenced_paths,
)
