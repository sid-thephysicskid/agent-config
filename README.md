# agent-config

Guardrails and software-delivery skills for Claude Code and Codex.

Skills guide how an agent works. The guard blocks common high-impact mistakes
before a tool runs.

The package ships 13 workflow skills and 3 optional operator skills.

## Install

Choose one profile:

```bash
npx @sid-thephysicskid/agent-config@latest install guard
npx @sid-thephysicskid/agent-config@latest install workflow
npx @sid-thephysicskid/agent-config@latest install operator
npx @sid-thephysicskid/agent-config@latest install full
```

| Profile | Installs |
|---|---|
| `guard` | Safety hooks only. This is the default. |
| `workflow` | Shared agent instructions and 13 delivery skills. |
| `operator` | Three optional skills and concise output styles. |
| `full` | Everything above. |

macOS and Linux are supported. Installation requires Node 18 or newer. The
guard also requires Python 3.8 or newer. Codex asks you to approve installed
hooks in `/hooks`.

Check or remove an installation:

```bash
npx @sid-thephysicskid/agent-config@latest doctor guard
npx @sid-thephysicskid/agent-config@latest uninstall guard
```

The installer refuses occupied paths instead of overwriting them.

<details>
<summary><strong>Install from source</strong></summary>

```bash
git clone https://github.com/sid-thephysicskid/agent-config.git
cd agent-config
./install.sh guard
```

Use `workflow`, `operator`, or `full` to install another profile. Keep the
checkout in place while it is installed; the source installer uses symlinks.

</details>

## How it works

<p align="center">
  <img src="docs/assets/how-it-works.svg" width="920" alt="Project instructions and a matching skill guide the coding agent. Before a tool runs, the guard either allows it or blocks it with a safer route.">
</p>

Workflow skills shape the agent's plan. The guard checks the proposed action
immediately before execution. Either layer can be installed on its own.

## Guard

The guard blocks common high-impact mistakes involving:

- protected Git branches and destructive history changes;
- live credential files;
- broad filesystem deletion;
- destructive or production-looking database commands;
- direct production deploys and irreversible infrastructure actions;
- writes to Git internals or the guard's own files.

```console
$ git push origin main
BLOCKED: pushing directly at 'main'.

Do this instead: push your feature branch and open a PR
```

A refusal explains the problem and suggests a safer route.

The guard is a safety net, not a sandbox. It uses text analysis, fails open on
internal errors, and cannot stop deliberate evasion. Keep branch protection,
least-privilege credentials, database roles, backups, CI, and human review.

## Workflow

The agent selects the smallest skill that matches the current task:

```text
navigate → prototype → bootstrap/setup → to-spec → breakdown
         → domain-modeling → architect → tdd/diagnose → review → ship
```

`unstick` handles merge and rebase conflicts.

<details>
<summary><strong>Skills</strong></summary>

| Skill | Purpose |
|---|---|
| `navigate` | Make or challenge a decision. |
| `prototype` | Test one unresolved question. |
| `bootstrap` | Start a repository with a working delivery path. |
| `setup` | Adopt an existing repository. |
| `to-spec` | Capture decided behavior and acceptance criteria. |
| `breakdown` | Create independently shippable work items. |
| `domain-modeling` | Define business language, rules, states, and ownership. |
| `architect` | Design a module or rank architecture improvements. |
| `tdd` | Implement behavior test-first. |
| `diagnose` | Find a root cause with evidence. |
| `review` | Review correctness, requirements, security, and maintainability. |
| `unstick` | Resolve Git conflicts without discarding intent. |
| `ship` | Verify and deliver authorized work. |

The optional operator profile adds `research`, `wizard`, and `handoff`.

</details>

## Shared project instructions

The workflow profile points Claude Code and Codex at the same global
instructions. To create the same arrangement inside a project, run:

```bash
npx @sid-thephysicskid/agent-config@latest init
```

This creates a real `AGENTS.md` and a relative `CLAUDE.md -> AGENTS.md` symlink.
Existing files are preserved; conflicts are reported and left untouched.

## Verification

Run the same checks as CI:

```bash
./scripts/ci-local
./scripts/ci-local --full
```

The suite covers guard rules and nearby safe commands, isolated installs,
uninstall behavior, npm packaging, plugin contents, and skill structure. The
[evaluation plan](evals/README.md) tracks outcome testing for the skills.

## Credit

Some skills are adapted from [Matt Pocock's open-source skills](https://github.com/mattpocock/skills).
See [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md) for attribution and licenses.

## License

MIT. See [SECURITY.md](SECURITY.md) for security reports and
[CONTRIBUTING.md](CONTRIBUTING.md) for contributions.
