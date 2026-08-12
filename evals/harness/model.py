"""Loading and parsing of the skill files. No judgement lives here.

Everything in this module is a measurement of what is on disk. Where a parse
is approximate (frontmatter is read with a deliberately tiny YAML subset, code
fences are classified by a first-token allowlist) the approximation is called
out in the relevant docstring, because a check built on a silent approximation
is worse than no check.
"""

import os
import re
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional, Tuple

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SKILLS_DIR = os.path.join(REPO_ROOT, "skills")
EVALS_DIR = os.path.join(REPO_ROOT, "evals")

SEVERITIES = ("error", "warn", "info")


@dataclass
class Finding:
    """One thing a check measured and did not like.

    `basis` is either "measured" (the check observed the fact directly, for
    example a file that does not exist) or "heuristic" (the check applied a
    threshold or a pattern that a reasonable person could set differently).
    Nothing here is an LLM judgement; those live in the scenario rubrics.
    """

    check: str
    severity: str
    message: str
    skill: Optional[str] = None
    evidence: str = ""
    basis: str = "measured"

    def __post_init__(self) -> None:
        if self.severity not in SEVERITIES:
            raise ValueError("bad severity %r" % (self.severity,))
        if self.basis not in ("measured", "heuristic"):
            raise ValueError("bad basis %r" % (self.basis,))


@dataclass
class Fence:
    """A fenced code block inside a markdown file."""

    info: str
    lines: List[str]
    start_line: int  # 1-based line number of the opening fence


@dataclass
class SkillDoc:
    name: str  # directory name
    directory: str
    skill_md: str
    frontmatter: Dict[str, str]
    body: str
    vendored: bool
    md_files: List[str] = field(default_factory=list)

    @property
    def declared_name(self) -> str:
        return self.frontmatter.get("name", "")

    @property
    def description(self) -> str:
        return self.frontmatter.get("description", "")

    @property
    def word_count(self) -> int:
        return len(self.body.split())


FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)


def parse_frontmatter(text: str) -> Tuple[Dict[str, str], str]:
    """Parse the leading YAML frontmatter block.

    Deliberately a tiny subset: top-level `key: value` pairs only, with
    surrounding quotes stripped. Nested keys (impeccable's `metadata:` tree)
    are skipped rather than half-parsed, and any key whose value we could not
    read is simply absent from the result. Callers must not treat a missing
    key as proof the key is missing from the file; the checks that care only
    look at `name` and `description`, which are always scalars in this suite.
    """
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    out = {}  # type: Dict[str, str]
    for line in m.group(1).splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        if line[:1] in (" ", "\t", "-"):
            continue  # nested or list item, out of scope for this parser
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[key.strip()] = value
    return out, text[m.end():]


def iter_fences(text: str) -> Iterator[Fence]:
    """Yield every triple-backtick fenced block, with its info string."""
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        stripped = lines[i].lstrip()
        if stripped.startswith("```"):
            info = stripped[3:].strip()
            start = i + 1
            body = []  # type: List[str]
            i += 1
            while i < len(lines) and not lines[i].lstrip().startswith("```"):
                body.append(lines[i])
                i += 1
            yield Fence(info=info, lines=body, start_line=start)
        i += 1


def load_skills(skills_dir: str = SKILLS_DIR) -> List[SkillDoc]:
    """Load every skill directory that contains a SKILL.md.

    Symlinked directories count: `skills/impeccable` and `skills/lavish` point
    into `vendor/`, and they are marked vendored so checks can hold them to a
    different standard. The repo's own rules say not to edit them.
    """
    docs = []  # type: List[SkillDoc]
    for entry in sorted(os.listdir(skills_dir)):
        directory = os.path.join(skills_dir, entry)
        skill_md = os.path.join(directory, "SKILL.md")
        if not os.path.isfile(skill_md):
            continue
        with open(skill_md, "r", encoding="utf-8") as fh:
            text = fh.read()
        fm, body = parse_frontmatter(text)
        real = os.path.realpath(directory)
        vendored = os.path.sep + "vendor" + os.path.sep in real + os.path.sep
        md_files = []
        for dirpath, dirnames, filenames in os.walk(real):
            dirnames[:] = [d for d in dirnames if d != "node_modules"]
            for fn in sorted(filenames):
                if fn.endswith(".md"):
                    md_files.append(os.path.join(dirpath, fn))
        docs.append(
            SkillDoc(
                name=entry,
                directory=directory,
                skill_md=skill_md,
                frontmatter=fm,
                body=body,
                vendored=vendored,
                md_files=sorted(md_files),
            )
        )
    return docs


def read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


WORD_RE = re.compile(r"[a-z0-9]+")


def normalise_tokens(text: str) -> List[str]:
    """Lowercase alphanumeric tokens, markdown punctuation discarded.

    This is what the duplication check compares. It is intentionally lossy:
    two sentences that differ only in emphasis markers or a comma are treated
    as the same sentence, which is the right call when the question is "did
    someone paste this paragraph twice".
    """
    return WORD_RE.findall(text.lower())
