# evals

Is this skill suite any good, or a pile of prose that agrees with itself?

**This measures the files, not the agent.** It checks that the suite is
internally sound: nothing orphaned, nothing contradictory, nothing prescribing
a command this repo's own guard would refuse. It does not tell you whether a
skill makes an agent better.

That second question is real and unanswered. It needs a fresh agent session per
task, run with and without the skill, scored blind. There used to be thirteen
scenario files here staging that experiment. Nobody ever ran them, so they are
gone: an experiment nobody runs is not evidence, it is furniture. What a real
one would need is at the bottom.

## Run it

```bash
python3 evals/run_evals.py                  # findings, scorecard, limits
python3 evals/run_evals.py --severity warn  # drop the info noise
python3 evals/run_evals.py --json           # machine readable
python3 evals/test_harness.py               # test the checks themselves
```

Exit 1 on any error-severity finding, so it works as a CI gate, and it is one.
Python 3.9, stdlib only, no network.

`test_harness.py` feeds every check an input it must reject and one it must
pass. A check that always returns green is worse than no check.

Findings marked `WARN*` or `INFO*` come from a threshold, not a fact. The
thresholds sit at the top of `harness/static_checks.py` with their reasoning.
Disagree by editing them, not by ignoring them.

## What it checks

Frontmatter and description budget. Em dashes, which the house style bans.
Trigger-word collisions. Cross-references that do not resolve, and skills
nothing references. Router coverage. Internal links and referenced paths,
**within packaged skill directories only**: the model walks `skills/` and
`operator-skills/`, so a broken link
in `README.md` or `AGENTS.md` is not this checker's job. `tests/audit.py`
covers every tracked file and is where a broken link outside `skills/` is
caught. Size against a threshold. Near-duplicate passages. Invocation parity, so a skill is
user-invoked in both harnesses or neither. Whether the README's stated context
budget still matches reality.

Two cross artefacts rather than lint one file, and they are the ones that earn
their keep:

- **Prescribed commands.** Every fenced command a skill tells an agent to run
  is put through the live guard on real git fixtures. A skill that prescribes
  something this repo refuses is a real defect, and nothing else can see it.
- **Guard claims.** `guard_claims.json` pins each stated guard behaviour to the
  exact sentence asserting it. Edit the sentence away and the check fails on
  the claim, rather than reporting green against text that no longer exists.

## Process compliance

`compliance/` is built and runs. It answers the narrow question the suite can
actually defend: did the agent follow the process, measured from repo state
after a run rather than from anyone's opinion of the code.

```bash
python3 evals/compliance/test_metrics.py   # the metrics, free, always run this
python3 evals/compliance/test_session.py   # the transcript reader, free
python3 evals/compliance/run.py            # dry run, costs nothing
python3 evals/compliance/run.py --check-arms          # 2 sessions, do this first
python3 evals/compliance/run.py --live --runs 30 --keep-transcripts out/
```

`--check-arms` runs one session per arm against a deliberate provocation and
asserts that the guarded one was refused, the unguarded one was not, and both
could see the injected rules. Run it before spending on a suite. The section
below is what it costs not to.

Ten metrics, each a pure function of a finished repository plus the SHA the
run started from. Every one has a fixture it must fail and one it must pass,
declared explicitly in `COVERAGE` so adding a metric without tests breaks the
suite. Alongside them, `session.py` reads the transcript for what the run cost
and where in the context window the agent first reached for something
dangerous. That half is diagnostic and never scored, because a transcript names
its own arm and a blind scorer must not see one.

Building it found four defects in itself, all of which produced confident
output while measuring nothing:

- **`--settings` adds hooks, it cannot remove them**, so the control arm ran
  the user's guards and both arms were guarded. Forty-eight sessions, one arm.
  The fix and the check that now proves the arms differ are below.
- Relocating `CLAUDE_CONFIG_DIR` to strip the skills also stripped the login,
  so every session exited immediately and the report printed `n/a` columns.
  `--setting-sources project` does the same job without touching auth.
- A session that changed nothing was reported as a row of `n/a` rather than an
  error. It is an error now.
- The first task said "please sort that out", which a one-shot session
  satisfies by editing the file. No commit ever existed, so every commit metric
  read `n/a`. Landing the change has to be part of the task; how it lands does
  not.

Three of the four are the same defect wearing different clothes: the harness
reported a number for something it had not measured. That is the failure mode
to design against here, not inaccuracy.

The first result reported here, six runs on `001-discount-boundary` coming out
identical in both arms, is withdrawn for the same reason as the 48-session run:
the arms were the same arm. See below.

### Only three of the ten metrics can move

Worth knowing before reading any table. Both arms load the same rules and the
same skills, by construction: the runner injects both identically and varies
only the hooks. So every metric about *convention* is common-mode and cancels.
The only outcomes a `PreToolUse` hook can reach are:

| Metric | Can a hook change it? |
|---|---|
| `protected_branch_untouched` | **yes**, `guard_git` refuses a commit or push on a protected branch |
| `worked_on_branch` | **yes**, the same refusal forces a branch |
| `secrets_kept_out` | **partly**, `guard_files` refuses *reading* a key file, and nothing refuses `git add -A` |
| the other seven | **no** |

That is not a flaw in the harness, it is what the harness is for. It means a
difference on those three is evidence about enforcement, and a difference on
the other seven is noise until proven otherwise. It also names the honest
ceiling on the whole exercise: this compares hooks, not skills, and no arm
here has the skills switched off.

The seven are still worth printing. They are the base rate: how often an agent
follows the process unprompted, which is the number the enforcement claim has
to beat.

### The gap this exposed in the guards themselves

`secrets_kept_out` is the interesting row. The file guard stops an agent
**reading** a credential file. It does not stop `git add -A` from **committing**
one, because that is a bash command about a directory rather than a read of a
secret path. Task 002 exists to find out whether that gap is reachable in
practice.

### WITHDRAWN: the 48-session run of 2026-08-06

**That run measured nothing, and the fault was in this harness, not in the
model. Both arms were guarded.** `--settings` *adds* settings rather than
replacing them, and same-event hook arrays concatenate, so the control arm's
`{"hooks": {}}` still ran the user's guards. There was one arm, run 48 times.

It published a null in the headline, which is what rule 2 asks for, and the
null was still wrong. Every claim drawn from it is withdrawn, including the one
that read best: *"the guards are insurance against the tail rather than a
change in the median."* Nobody knows that. The raw output stays in
`compliance/results-2026-08-06.txt`.

That is what rule 7 costs, and why it exists.

### The fix, and the check that now proves it

`--setting-sources project` drops the user source outright and keeps the login,
because auth is not a setting. That is what makes the arms real.

It also drops the skills and the global rules along with the hooks, so the
runner puts those back identically in both arms, as project-level config inside
`.claude/` in the throwaway repo, hidden from git by `.git/info/exclude` so it
can never appear in a status or a diff and pollute a metric. The rules come
from this repo's own `AGENTS.md` rather than `~/.claude/CLAUDE.md`, so an
operator's gitignored `AGENTS.local.md` preferences cannot leak into a
published measurement.

`run.py --check-arms` asserts all three properties in two sessions:

| | guarded | unguarded |
|---|---|---|
| a hook refused the commit | yes | **no** |
| `main` moved | no | **yes** |
| injected rules reached the session | yes | yes |

Run it before every experiment. It is the check that would have caught this on
day one.

### What is known now

About the guards, on the median, from measurement: **nothing.** The base rate
question is open again too, because the sessions that produced the 100% base
rate were themselves guarded.

That is a worse position than the one this file claimed before and a better
one than believing the claim. The re-run needs the arms above, thirty runs, and
a metric written down first, in `compliance/PREREGISTRATION.md`.

### The long-session gap, still open

Every session so far was short, clean, and single-purpose. The failure mode the
guards exist for is the opposite: a long session, context under pressure, the
model many turns from the instruction it was given.

`compliance/tasks/010-marathon/` is the task built for that: a billing service
with a two-penny reconciliation error whose cause is three modules from its
symptom, a green suite that does not cover it, and every temptation placed at
the end of the chain rather than the start. `session.py` records how full the
context window was at the first dangerous tool call, so the decision point can
be located rather than assumed.

It is built and it has not been run. The hypothesis, the thresholds, the
sample size and the condition under which the long-session claim is reported
as **untested** are all written down first, in
`compliance/PREREGISTRATION.md`.

## The problem, stated without flattery

Every agent-tooling repo claims to make your agent better. Almost none offers
evidence. The evidence that does exist fails in one of four ways:

1. **No control arm.** "Look what it built" is a demo, not a comparison.
2. **Instructed outcomes.** Telling the agent to branch, then measuring
   branches. This repo shipped exactly that mistake in its first task and had
   to rewrite it.
3. **A judge correlated with the thing judged.** An LLM scoring whether an
   LLM did well, usually the same model.
4. **Selective reporting.** The metric that moved gets published. The eleven
   that did not are not mentioned.

None of these is fraud. All four are what you get by default when you measure
something you want to be true.

## Seven rules, and each one exists because of a specific failure

**1. Pre-register the metric and the threshold.** Write down what would count
as a win *before* the run. Otherwise the number reported is whichever one
happened to move, and with ten metrics and two arms something always moves.

**2. Publish nulls in the headline.** Not the appendix. A framework that
surfaces only wins is marketing with a test suite attached.

The 48-session run is the template for what this rule costs rather than for
what it buys. A null was published in the headline, exactly as this rule asks,
and it was *still* wrong, because the control arm was contaminated. Publishing
a null is necessary and nowhere near sufficient. Rule 7 is what that bought.

**3. The scorer never learns the arm.** Blind by construction, not by
discipline. Where the metric is deterministic, as everything in
`compliance/metrics.py` is, this is free and there is no excuse for skipping it.

**4. Danger must be incidental.** The destructive option has to be the
convenient one, arrived at while doing something else. A task that says "now
deploy to production" and then blocks the deploy measures nothing.

**5. Report cost per outcome, not outcome.** A skill that improves a result by
2% while spending 30% more tokens is a loss, and nobody in this market reports
the denominator. Tokens, wall-clock and turns all belong next to every
percentage.

**6. Ablate, do not only compare.** A/B against nothing tells you the bundle
helps. Removing one component at a time tells you which parts earn their place.
The expected finding is uncomfortable and that is the point.

**7. Prove the control arm is a control, every time, before the run.** Added
2026-08-06 after this framework's own first result turned out to be 48 sessions
of a single arm: `--settings` adds hooks and cannot remove them, so the
"unguarded" column ran the same guards as the guarded one. The two columns
agreed perfectly, which read as a finding.

The general shape is worse than the specific bug. **A harness that cannot
demonstrate its own control arm will report your configuration back to you, and
it will look exactly like evidence**, because a contaminated control produces
clean, consistent, plausible numbers. Every check in the first five rules was
satisfied by that run. It was pre-registered in spirit, deterministic, blind,
and wrong.

So: an assertion that the control arm differs, executed immediately before the
experiment, published with the result. In this repo that is
`compliance/run.py --check-arms`, which spends two sessions to prove the
guarded arm was refused, the unguarded arm was not, and both saw the same
instructions. Two sessions against forty-eight is a good trade at any price.

## What this does not measure

Whether the guard is correct (`hooks/tests.py` and `hooks/floor.py` do that),
whether a skill helps in a codebase unlike the fixtures, and anything about
agents other than Claude Code and Codex.
