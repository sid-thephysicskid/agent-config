# agent-config

Coding agents are great until one runs `docker compose down -v` on your dev database. Or force-pushes over your repo. Or `rm -rf ~/`. All of that actually happened to people.

This is a hook that stops that stuff before it runs. Everything else goes through.

```bash
npx @sid-thephysicskid/agent-config@latest install
```

Claude Code and Codex. macOS or Linux, Node 20+, Python 3.9+. No network, no model calls, no dependencies.

## What it stops

Every rule is here because an agent did it to someone:

- `rm -rf` on your home dir or `.git` ([cc#12637](https://github.com/anthropics/claude-code/issues/12637), [codex#3728](https://github.com/openai/codex/issues/3728))
- Force push over your repo ([cc#33402](https://github.com/anthropics/claude-code/issues/33402))
- `reset --hard`, `clean -f`, `git restore .` eating uncommitted work ([Cursor](https://forum.cursor.com/t/cursor-agent-just-delete-my-changes-by-git-restore-in-sandbox/154810))
- Wiping databases: `prisma db push --force-reset`, `drizzle-kit push --force`, `docker compose down -v` ([cc#36183](https://github.com/anthropics/claude-code/issues/36183), [cc#27063](https://github.com/anthropics/claude-code/issues/27063), [cc#63644](https://github.com/anthropics/claude-code/issues/63644))
- `terraform destroy`, cloud CLI deletes, `curl -X DELETE` at your provider ([DataTalks.Club](https://incidentdatabase.ai/cite/1424/), [PocketOS](https://www.theregister.com/2026/04/27/cursoropus_agent_snuffs_out_pocketos/))
- Reading or printing keys: `.env`, `~/.aws/credentials`, `printenv`, `echo $API_KEY` ([cc#9637](https://github.com/anthropics/claude-code/issues/9637), [cc#62156](https://github.com/anthropics/claude-code/issues/62156))
- `killall node` taking out your IDE ([cc#2782](https://github.com/anthropics/claude-code/issues/2782))
- `chmod -R` / `chown -R` on system dirs ([cc#168](https://github.com/anthropics/claude-code/issues/168))

Full list: [docs/guard-coverage.md](docs/guard-coverage.md).

## Pasted a key into the chat?

It spots common key formats (GitHub, OpenAI, Anthropic, AWS, Stripe, and more) and stops the agent from acting on the message. Rotate the key anyway: Claude Code still writes the message to its local log.

Next time, don't paste it:

```bash
npx @sid-thephysicskid/agent-config secret OPENAI_API_KEY        # hidden input, into .env
npx @sid-thephysicskid/agent-config secret NPM_TOKEN --github    # into GitHub Actions secrets
```

## What it won't get in the way of

Commits and pushes to `main`. Editing your settings or `CLAUDE.md`. `kill <pid>`. `docker compose down`. Normal work.

If it blocks something normal, that's a bug. [Open an issue](https://github.com/sid-thephysicskid/agent-config/issues/new?template=refused-ordinary-work.yml).

Don't want direct commits to `main` either? `export AGENT_CONFIG_BLOCK_DIRECT_COMMITS=1`.

## The honest bit

It's a seatbelt, not a vault. An agent that really wants to can get around it; known gaps are in [evals/redteam-candidates.txt](evals/redteam-candidates.txt). If a rule crashes, it fails open and your agent keeps working.

```bash
npx @sid-thephysicskid/agent-config@latest doctor      # check it still blocks
npx @sid-thephysicskid/agent-config@latest uninstall   # gone, settings restored
```

Used to be `onbelay`. `install` cleans that up. MIT.
