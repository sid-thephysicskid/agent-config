---
name: wizard
description: Prepare a safe, human-run credential or dashboard setup when an agent is blocked on API keys, CI secrets, account provisioning, or other steps only the user can complete. Use when secrets must stay out of the conversation or a third-party UI requires the human; not for work the agent can perform safely itself.
---

# Wizard

Hand the human a declarative setup plan executed by the fixed, reviewed
`scripts/wizard.py` runner. Never generate a shell script that can execute
arbitrary commands after capturing a secret.

## Build the plan

Inspect only non-secret sources:

- `.env.example` for expected local names. Never read a real environment file.
- CI workflows for referenced secrets.
- repository instructions and architecture decisions for chosen services.

For each value, identify its source URL, the exact visible steps, whether input
must be hidden, and each destination. Use `assets/plan.example.json` as the
shape. The runner accepts only instructions, allowlisted HTTPS URLs, local
environment writes, and GitHub Actions secret writes. It cannot run generated
commands or call arbitrary APIs.

Use one focused stage per dashboard task. Put every hostname used by a stage in
`allowed_hosts`; the runner rejects all other URLs and asks before opening an
allowed URL. Add a stage confirmation for paid, destructive, or otherwise
consequential human actions.

## Validate and hand over

Run only the non-interactive validator:

```sh
python3 <skill-directory>/scripts/wizard.py <plan.json> --check
```

Review the validator's destination summary against `.env.example` and the CI
workflows. Do not run the plan, capture a sample secret, inspect its output
file, or ask the user to paste a value into chat.

Tell the user:

- the exact command they should run;
- which accounts and logins they need;
- which named files and CI destinations will change;
- that the runner asks before each URL and write.

The human runs the interactive command. The runner hides secret input, writes
local environment files with mode `0600`, and sends GitHub secrets to `gh`
through standard input. If the fixed runner cannot express a required action,
leave that action as a human instruction. Do not extend the plan with code.
