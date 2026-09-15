# Guard coverage

## Who this is defending against

A careless agent, not an adversary. The guard reads one tool call at a time, immediately before it runs.

- Not a security boundary. It fails open on internal errors and analysis timeouts.
- Deliberate obfuscation is out of scope: encoding a command, hiding the verb in a variable, running it on a remote host. Accepted gaps are listed with reasons in [`tests/redteam-candidates.txt`](../tests/redteam-candidates.txt).
- Keep branch protection, least-privilege credentials, database roles, backups, CI, and review.

## Matched by pattern

| Category | Owner |
|---|---|
| Force pushes, including the leading-plus refspec and an unpinned lease | `hooks/guard_git.py` |
| Deleting a protected branch, or moving it with `branch -f` or `checkout -B` | `hooks/guard_git.py` |
| Plain commits, merges, and pushes on a protected branch, only with `AGENT_CONFIG_BLOCK_DIRECT_COMMITS=1` | `hooks/guard_git.py` |
| Discarding the working tree: reset, clean, checkout, restore, stash drop | `hooks/guard_git.py` |
| Reading, copying, printing or uploading a real credential or key | `hooks/guard_secrets.py` |
| A known key format pasted into a prompt | `hooks/guard-prompt.py` |
| Writing to the guard's own files, or removing its hook entries from settings | `hooks/guard_paths.py` |
| Writing into git plumbing: `.git/config`, `.git/hooks`, refs | `hooks/guard_paths.py` |
| Connecting to a host that looks like production | `hooks/guard_db.py` |
| Unqualified or tautological DELETE and UPDATE, DROP and TRUNCATE | `hooks/guard_db.py` |
| A program passed inline to an interpreter that deletes or reads secrets | `hooks/guard_rules.py` |

## Tests

- `tests/cases.py`: block and allow cases, each run by `tests/rules.py` in both string and argv form.
- `tests/ordinary.txt`: everyday commands that must never be refused.
- `tests/redteam-candidates.txt`: bypass attempts, each blocked or triaged as an accepted gap.

<!-- BEGIN GENERATED: scripts/guard-coverage -->

## What is refused

### Git

- deleting a protected branch
- dropping stashed work
- force-removing a worktree with live changes
- git branch -D (force-deletes an unmerged branch)
- git branch -f on a protected branch (moves it under everyone else)
- git checkout -B on a protected branch (resets it to wherever you are)
- git clean -f (deletes untracked files permanently)
- git push --mirror (force-updates every ref and deletes remote branches)
- git reset --hard (discards committed and staged work)
- history rewrite

### Filesystem and tooling

- a recursive permission change on a system or home root, or to 777
- an API call that deletes remote resources
- deleting Docker volumes (the local database lives there)
- deleting a GitHub repository
- deleting a Kubernetes resource
- deleting a cloud resource
- deleting a whole drive or home directory
- dropdb
- killing processes by name (takes down every match, the agent included)
- merging a PR with --admin (bypasses required checks)
- publishing to a package registry (irreversible)
- publishing to the npm registry (irreversible)
- publishing to the npm registry via yarn (irreversible)
- recursive S3 deletion
- removing a Vercel deployment or project
- removing an S3 bucket and its contents
- terraform apply -destroy (tears down infrastructure)
- terraform destroy (tears down infrastructure)

### Production deploys and publishes

- a Cloudflare Workers deploy (production by default)
- a Fly.io deploy (production by default)
- a Netlify production deploy
- a Railway deploy (production by default)
- a Vercel production deploy
- applying migrations to a live database

### Database destruction

- MongoDB collection drop
- MongoDB delete with an empty filter: removes every document
- rails db:drop/db:reset: drops the database
- redis FLUSHALL/FLUSHDB: wipes the entire keyspace

## Measured

| Measure | Count |
|---|---|
| Commands refused | 808 |
| Ordinary commands allowed | 895 |
| Path cases | 45 |
| Red-team candidates leaking untriaged | 0, or CI fails |
<!-- END GENERATED -->
