# agent-config

Guardrails for Claude Code and Codex. A hook that stops force pushes, secret reads, and destructive commands before they run, and tells the agent what to do instead.

```bash
npx @sid-thephysicskid/agent-config@latest install
```

Restart your agent. Codex asks you to approve the new hooks in `/hooks`. macOS or Linux, Node 20+, Python 3.9+.

<p align="center">
  <img src="docs/assets/how-it-works.svg" width="900" alt="Three ordinary commands run. A force push is stopped, and the message names the safe alternative.">
</p>

## What it blocks

- Force pushes to `main`, `master`, `trunk`, `release`, `production`, `prod`, and deleting those branches
- `reset --hard`, `clean -f`, and discarding the working tree
- `rm -rf` on home, system, or `.git` directories
- Reading or copying `.env` files, SSH keys, and cloud credentials
- `DROP`, `TRUNCATE`, `DELETE` or `UPDATE` without `WHERE`, and connections to production database hosts
- Publishes and production deploys that skip CI
- Edits that remove the guard itself

Everything else goes through, including commits and pushes to `main` and edits to your own settings and `CLAUDE.md`. No network, no model call, about 50ms per check. Full list: [docs/guard-coverage.md](docs/guard-coverage.md).

## Options

Set in your shell profile.

| Variable | Effect |
|---|---|
| `AGENT_CONFIG_PROTECTED_BRANCHES` | Comma-separated list replacing the default protected branches. Empty turns branch rules off. |
| `AGENT_CONFIG_BLOCK_DIRECT_COMMITS=1` | Also refuse plain commits, merges, and pushes on protected branches. |

## Commands

```bash
npx @sid-thephysicskid/agent-config@latest doctor      # prove the guard still blocks
npx @sid-thephysicskid/agent-config@latest uninstall   # remove it, settings restored
```

## Limits

It is a safety net, not a security boundary. It stops a careless agent, not a determined one; known gaps are listed with reasons in [evals/redteam-candidates.txt](evals/redteam-candidates.txt). It fails open: if a rule crashes, your agent keeps working and `doctor` reports it. Keep branch protection, backups, and least-privilege credentials.

## Blocked something safe?

[Open an issue](https://github.com/sid-thephysicskid/agent-config/issues/new?template=refused-ordinary-work.yml) with the exact command. False positives are bugs.

## Upgrading from On Belay

This package was briefly published as `@sid-thephysicskid/onbelay`. Running `install` removes the old hooks, skills, and instruction block. Workflow skills were dropped in 0.5.0; [mattpocock/skills](https://github.com/mattpocock/skills) covers that ground.

MIT. [SECURITY.md](SECURITY.md) for bypass reports, [CONTRIBUTING.md](CONTRIBUTING.md) to contribute.
