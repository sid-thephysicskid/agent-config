"""Static checks over the SKILL.md files. Every one of these runs today.

Each check is a function taking the loaded skills and returning a list of
Findings. Read the docstrings before believing a number: several checks apply
a threshold, and a threshold is an opinion with a number attached. Those are
marked `basis="heuristic"` in their findings so the report can separate them
from facts like "this link does not resolve".
"""

import os
import re
from typing import List, Sequence

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
ALL_CHECKS = (
    check_frontmatter,
    check_em_dash,
    check_internal_links,
    check_referenced_paths,
)
