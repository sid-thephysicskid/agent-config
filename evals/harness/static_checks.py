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

from .model import Finding, SkillDoc, normalise_tokens, read

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
# 3. Trigger words: do two skills claim the same invocation?
# ---------------------------------------------------------------------------

TRIGGER_MARKERS = (
    "use this skill whenever",
    "use this skill when",
    "use when",
    "use for",
    "triggers on:",
)

STOPWORDS = set(
    """
a an and are as at be been before but by can code do does for from get give
had has have how i if in into is it its just like make makes more most need
needs no not of on one only or other our out over run said same say says she
should so some something such take than that the their them then there these
they this those through to too under up use used user users using want wants
was way we what when where which while who why will with would you your yours
skill skills task tasks thing things work works another instead not never
""".split()
)


def _trigger_tokens(description: str) -> Set[str]:
    """Tokens from the trigger clause of a description.

    The trigger clause is the text after the first marker phrase ("Use when",
    "Triggers on:", ...). If a description has no marker the whole description
    is used, which over-counts for those skills; that is called out where the
    result is reported.
    """
    low = description.lower()
    idx = len(low)
    for marker in TRIGGER_MARKERS:
        found = low.find(marker)
        if found != -1:
            idx = min(idx, found + len(marker))
    clause = low[idx:] if idx < len(low) else low
    toks = re.findall(r"[a-z][a-z-]{2,}", clause)
    return {t for t in toks if t not in STOPWORDS}


def check_trigger_collisions(skills: Sequence[SkillDoc]) -> List[Finding]:
    """Report trigger tokens claimed by more than one skill.

    A collision is not automatically a defect: "test" belonging to both /tdd
    and /ship is fine because they sit at different points in the same flow.
    It is a defect when two skills would both plausibly fire on the same user
    sentence and the router has no tie-break. The check reports the raw
    overlap and leaves the verdict to the reader, so this is a measurement,
    not a pass/fail gate.
    """
    owners = defaultdict(set)  # type: Dict[str, Set[str]]
    for s in skills:
        for tok in _trigger_tokens(s.description):
            owners[tok].add(s.name)

    pair_overlap = defaultdict(set)  # type: Dict[Tuple[str, str], Set[str]]
    for tok, names in owners.items():
        if len(names) < 2:
            continue
        ordered = sorted(names)
        for i in range(len(ordered)):
            for j in range(i + 1, len(ordered)):
                pair_overlap[(ordered[i], ordered[j])].add(tok)

    out = []  # type: List[Finding]
    for pair, toks in sorted(pair_overlap.items(), key=lambda kv: -len(kv[1])):
        if len(toks) < 3:
            continue
        out.append(
            Finding(
                "trigger-collision",
                "warn" if len(toks) >= 5 else "info",
                "%s and %s share %d trigger tokens" % (pair[0], pair[1], len(toks)),
                pair[0],
                evidence=", ".join(sorted(toks)[:12]),
                basis="heuristic",
            )
        )
    return out


# ---------------------------------------------------------------------------
# 4. Cross-references: does every /name resolve, and who is orphaned?
# ---------------------------------------------------------------------------

# The suite's own convention for naming a sibling skill is a backticked
# slash-name: `/ship`. Anything else (a bare /ship in prose, a path like
# `/api/health`) is deliberately not matched, so this check has false
# negatives rather than false positives.
SKILL_REF_RE = re.compile(r"`/([a-z][a-z0-9-]*)`")
ENTRY_SKILLS = {"navigate", "bootstrap", "setup", "diagnose", "review",
                "ship", "unstick", "research", "handoff"}


def _refs_in(text: str) -> List[str]:
    return SKILL_REF_RE.findall(text)


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


def reference_graph(skills: Sequence[SkillDoc]) -> Tuple[Dict[str, Set[str]], Dict[str, Set[str]]]:
    names = {s.name for s in skills}
    outbound = defaultdict(set)  # type: Dict[str, Set[str]]
    inbound = defaultdict(set)  # type: Dict[str, Set[str]]
    for s in skills:
        for path in s.md_files:
            for ref in _refs_in(read(path)):
                if ref in names and ref != s.name:
                    outbound[s.name].add(ref)
                    inbound[ref].add(s.name)
    return outbound, inbound


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


ROUTING_LINE_RE = re.compile(r"^\s*-\s+(\"[^`]*?\")\s*->\s*`/([a-z][a-z0-9-]*)`", re.MULTILINE)
QUOTED_RE = re.compile(r"\"([^\"]+)\"")


# ---------------------------------------------------------------------------
# 5. Internal links
# ---------------------------------------------------------------------------
MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
PATHISH_RE = re.compile(r"`([\w.][\w./-]*\.(?:md|sh|mjs|py|ya?ml|json|ts|js))`")


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


def check_size_budget(skills: Sequence[SkillDoc]) -> List[Finding]:
    """Flag SKILL.md files large enough that loading one is a real context cost.

    Thresholds are heuristics chosen so the suite median passes. The number
    that matters is not any single file but the share of the suite one file
    accounts for, which the scorecard prints.
    """
    out = []  # type: List[Finding]
    for s in skills:
        n = s.word_count
        if n > SIZE_WARN:
            sev = "warn"
        elif n > SIZE_INFO:
            sev = "info"
        else:
            continue
        out.append(
            Finding(
                "size",
                sev,
                "SKILL.md is %d words (info >%d, warn >%d)" % (n, SIZE_INFO, SIZE_WARN),
                s.name,
                basis="heuristic",
            )
        )
    return out


# ---------------------------------------------------------------------------
# 7. Duplication
# ---------------------------------------------------------------------------

SHINGLE = 12  # tokens


def _runs(tokens: List[str], shared: Set[Tuple[str, ...]]) -> List[Tuple[int, int]]:
    runs = []
    i = 0
    n = len(tokens)
    while i + SHINGLE <= n:
        if tuple(tokens[i:i + SHINGLE]) in shared:
            j = i
            while j + SHINGLE <= n and tuple(tokens[j:j + SHINGLE]) in shared:
                j += 1
            runs.append((i, j + SHINGLE - 1))
            i = j + 1
        else:
            i += 1
    return runs


def check_duplication(skills: Sequence[SkillDoc]) -> List[Finding]:
    """Find long token sequences repeated across skills, and inside one file.

    A repeated 12-token run is not proof of copy-paste, but in prose written
    by one author it is close: the odds of two independently written sentences
    agreeing on twelve consecutive normalised tokens are small. Cross-skill
    repeats are the direct measurement of "is this a spaghetti mess": they are
    the instructions that have to be updated in N places to stay consistent.
    """
    out = []  # type: List[Finding]
    tokens_by_skill = {}  # type: Dict[str, List[str]]
    for s in skills:
        tokens_by_skill[s.name] = normalise_tokens(s.body)

    index = defaultdict(set)  # type: Dict[Tuple[str, ...], Set[str]]
    for name, toks in tokens_by_skill.items():
        for i in range(len(toks) - SHINGLE + 1):
            index[tuple(toks[i:i + SHINGLE])].add(name)

    shared = {sh for sh, owners in index.items() if len(owners) > 1}
    seen = set()  # type: Set[str]
    for name, toks in sorted(tokens_by_skill.items()):
        for start, end in _runs(toks, shared):
            phrase = " ".join(toks[start:end + 1])
            others = set()  # type: Set[str]
            for i in range(start, end - SHINGLE + 2):
                others |= index[tuple(toks[i:i + SHINGLE])]
            others.discard(name)
            key = phrase
            if key in seen:
                continue
            seen.add(key)
            out.append(
                Finding(
                    "duplication",
                    "warn" if end - start >= 20 else "info",
                    "%d-token run also present in %s" % (end - start + 1, ", ".join(sorted(others))),
                    name,
                    evidence=phrase[:200],
                )
            )

    # Intra-file repeats: the same run twice inside one SKILL.md.
    for name, toks in sorted(tokens_by_skill.items()):
        positions = defaultdict(list)  # type: Dict[Tuple[str, ...], List[int]]
        for i in range(len(toks) - SHINGLE + 1):
            positions[tuple(toks[i:i + SHINGLE])].append(i)
        repeated = {sh for sh, ps in positions.items() if len(ps) > 1}
        for start, end in _runs(toks, repeated):
            phrase = " ".join(toks[start:end + 1])
            out.append(
                Finding(
                    "duplication",
                    "warn",
                    "%d-token run appears more than once inside its own SKILL.md" % (end - start + 1),
                    name,
                    evidence=phrase[:200],
                )
            )
            break  # one report per skill is enough to make the point
    return out


ALL_CHECKS = (
    check_frontmatter,
    check_em_dash,
    check_trigger_collisions,
    check_skill_references,
    check_orchestration_handoffs,
    check_invocation_parity,
    check_internal_links,
    check_referenced_paths,
    check_size_budget,
    check_duplication,
)
