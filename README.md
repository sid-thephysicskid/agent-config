<p align="center">
  <img src="docs/assets/railway-hero.webp" width="100%" alt="A railway signal board routes one path safely to a shipped package while a red signal stops a dangerous route to production infrastructure.">
</p>

# agent-config

Guardrails and focused delivery workflows for Claude Code and Codex.

**A skill is advice. A hook is a wall.** Skills give the agent a route from an unclear request to a verified release. A local pre-tool hook blocks a short list of destructive mistakes before the command runs.

## Install

Published releases install with `npx`. Install only what you want:

```bash
npx agent-config@latest install guard
npx agent-config@latest install workflow
npx agent-config@latest install operator
npx agent-config@latest install full
```

Before the first npm release, install from a verified checkout with `./install.sh guard` or another profile. The npm package is intentionally not live until the public repository is created.

The default is `guard`. Versioned files are copied to `~/.local/share/agent-config/`, so the installation never depends on npm's temporary cache.

macOS and Linux are supported. Native Windows is not supported, and WSL is not yet verified. Node 18 or newer is required for the installer. The guard also requires Python 3.8 or newer.

Review local hooks before trusting them. Codex also requires approval in `/hooks` after installation.

| Layer | What it adds | What it does not add |
|---|---|---|
| `guard` | Deterministic checks before risky tool calls | Skills or global opinions |
| `workflow` | Thirteen software-delivery skills and shared agent instructions | Hooks |
| `operator` | Research, handoff, credential setup, and communication options | Core workflow or hooks |
| `full` | All three layers | Nothing beyond this repository |

Check or remove a profile:

```bash
npx agent-config@latest doctor guard
npx agent-config@latest uninstall guard
```

Prefer a clone? `./install.sh` and `./uninstall.sh` provide the same profiles. Both installers refuse occupied paths instead of overwriting them.

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

It inspects shell commands, file operations, Codex patches, and common MCP file-tool payloads. A refusal explains what was blocked and gives the safe route.

This is a safety net for mistakes, not a sandbox. Deliberate evasion can bypass text analysis. Anything with shell access can modify user-owned hooks. Internal errors fail open. Use protected branches, least-privilege credentials, database roles, backups, CI, and human review as the stronger controls.

## Workflow

The workflow follows the work instead of forcing every project through every step:

```text
navigate → prototype → bootstrap/setup → to-spec → breakdown
         → domain-modeling → architect → tdd/diagnose → review → ship
```

`unstick` handles merge and rebase conflicts.

<details>
<summary><strong>What each skill owns</strong></summary>

| Skill | One job |
|---|---|
| `navigate` | Reach a decision or break a weak plan. |
| `prototype` | Answer one unresolved question with disposable evidence. |
| `bootstrap` | Start a repository with a working delivery path. |
| `setup` | Adopt an existing repository without guessing its commands or tracker. |
| `to-spec` | Turn decided behavior into an acceptance contract. |
| `breakdown` | Produce independently shippable work items. |
| `domain-modeling` | Define business language, rules, states, and ownership. |
| `architect` | Design a deep module or rank architecture improvements. |
| `tdd` | Build business behavior in red, green, refactor cycles. |
| `diagnose` | Establish root cause through evidence and experiments. |
| `review` | Review standards, requirements, security, and maintainability. |
| `unstick` | Resolve a Git conflict without discarding intent. |
| `ship` | Verify, commit, open a PR, watch CI, and release with approval. |

Operator adds three optional skills: `research`, `wizard`, and `handoff`.

</details>

Skills activate from their descriptions when the current task matches. The global workflow policy makes that orchestration explicit. Across Workflow and Operator, the sixteen model-invocable descriptions total 4,125 characters of standing discovery context. Full skill instructions load only when selected.

## One project contract for every agent

Workflow installation points both global files at the same source:

```text
~/.codex/AGENTS.md   ─┐
                     ├─→ one shared AGENTS.md
~/.claude/CLAUDE.md ─┘
```

Existing instructions are preserved. If either path is occupied, automatic mode installs the skills without replacing either host's instructions.

Inside any project, run:

```bash
npx agent-config@latest init
```

That creates a real project `AGENTS.md` and a relative `CLAUDE.md -> AGENTS.md` symlink. Existing content is preserved. A conflicting `CLAUDE.md` is reported and left untouched.

## Optional: a useful mental model of coding agents

<details>
<summary><strong>Where context, instructions, skills, tools, and hooks fit</strong></summary>

<p align="center">
  <img src="docs/assets/agent-loop.svg" width="640" alt="An agent host assembles a finite context from the request, instructions, skills, and repository. The model proposes a tool call. A pre-tool guard may block it before the tool reaches Git, the filesystem, or a database. Tool output returns to the next model turn.">
</p>

- **The model** reasons over what is currently in front of it. It does not run commands itself.
- **Context** is the finite working set for this session: the request, instructions, selected files, tool results, and any skill that was loaded.
- **Memory** depends on the host. Do not assume every agent remembers another session.
- **`AGENTS.md` and `CLAUDE.md`** are operating instructions loaded by the host. They are not application code.
- **Skills** are playbooks. Hosts first see each name and description, then load the full skill when it matches the task.
- **Tools** are the agent's hands: shell, files, browsers, APIs, and other capabilities.
- **Pre-tool hooks** run after the model proposes an action but before the host executes it. That is where this guard can refuse a mistake.
- **Tests and CI** provide external evidence. They remain necessary even when the instructions and guard work perfectly.

See the official documentation for [Codex project instructions](https://learn.chatgpt.com/docs/agent-configuration/agents-md) and [Codex skills](https://learn.chatgpt.com/docs/build-skills).

</details>

## Native packages

Self-contained Claude Code and Codex plugin sources live in `plugins/`. They expose the same three layers without requiring the clone installer. Release maintainers can build clean artifacts with:

```bash
./scripts/build-plugins ./dist-plugins
```

The `npx` installer remains the simplest cross-host path because it can also establish shared global instructions and the project initializer.

## Verification and evidence

Run the same local gates as CI:

```bash
./scripts/ci-local
./scripts/ci-local --full
```

The suite checks rule behavior, nearby safe operations, tool adapters, hostile installer homes, selective uninstall, npm packaging, plugin contents, skill structure, provenance, and documentation claims.

What is not yet proven: that the skills improve agent outcomes against a control. [The evaluation plan](evals/README.md) records what would justify that claim. Until then, the narrower claim is the honest one: the executable boundaries are inspectable and tested.

## Public release

This repository can export the current clean commit without Git history:

```bash
./scripts/build-public-release ../agent-config-public
```

The export is scanned, npm-packed, and refused if it contains symlinks. Initialize the destination as a new repository only after the release commit is approved.

For the first GitHub release, confirm the npm name and package URLs. Create a short-lived granular npm token with read/write access, **All Packages**, and **Bypass 2FA**, then save it as the `NPM_TOKEN` repository secret. Revoke it immediately after publication. Next, authorize `publish.yml` as the package's [npm trusted publisher](https://docs.npmjs.com/trusted-publishers/) and delete the secret. Later releases use short-lived OIDC credentials with provenance.

## Provenance

Several skills began as adaptations of [Matt Pocock's skills](https://github.com/mattpocock/skills). Others are original or only conceptually influenced. [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md) records the lineage per skill and carries the upstream MIT notice.

Original work is MIT licensed. Security reports and supported boundaries are in [SECURITY.md](SECURITY.md). Contributions are described in [CONTRIBUTING.md](CONTRIBUTING.md).

The hero illustration was generated for this project with OpenAI image generation.
