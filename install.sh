#!/usr/bin/env bash
# Install the guard hooks into Claude Code, Codex, and Cursor. Re-run to repair or upgrade.
#   ./install.sh           install
#   ./install.sh --check   verify and prove the guard decides; change nothing
# To remove: ./uninstall.sh
set -euo pipefail

src="${BASH_SOURCE[0]}"
while [[ -L "$src" ]]; do
  dir="$(cd "$(dirname "$src")" && pwd)"
  src="$(readlink "$src")"
  [[ "$src" == /* ]] || src="$dir/$src"
done
REPO="$(cd "$(dirname "$src")" && pwd)"

CHECK=0
for arg in "$@"; do
  case "$arg" in
    --check) CHECK=1 ;;
    guard) ;;
    *) echo "usage: install.sh [--check]" >&2; exit 1 ;;
  esac
done

C="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
X="${CODEX_HOME:-$HOME/.codex}"
SETTINGS="$C/settings.json"
# host:hooks.json for each host that is installed. Cursor has no config dir variable.
HOSTS=()
if [[ -d "$X" ]]; then HOSTS+=("codex:$X/hooks.json"); fi
if [[ -d "$HOME/.cursor" ]]; then HOSTS+=("cursor:$HOME/.cursor/hooks.json"); fi
PROBLEMS=0
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$1"; }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$1"; PROBLEMS=$((PROBLEMS+1)); }
die()  { printf 'agent-config: %s\n' "$1" >&2; exit 1; }

python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>/dev/null \
  || die "python3 3.9 or newer is required."
command -v git >/dev/null || die "git is required: the guard reads branch state with it."

if (( ! CHECK )); then
  [[ ! -e "$C/hooks" || -d "$C/hooks" ]] || die "$C/hooks is not a directory. Nothing was changed."
  for f in "$REPO"/hooks/guard*.py; do
    if [[ -e "$C/hooks/${f##*/}" && ! -L "$C/hooks/${f##*/}" ]]; then
      die "$C/hooks/${f##*/} is not ours. Move it aside first. Nothing was changed."
    fi
  done
  msg="$(python3 "$REPO/scripts/install_settings.py" validate "$SETTINGS" 2>&1)" \
    || die "$msg. Fix or move it first. Nothing was changed."
  for h in ${HOSTS[@]+"${HOSTS[@]}"}; do
    msg="$(python3 "$REPO/scripts/install_hooks_json.py" validate "${h#*:}" 2>&1)" \
      || die "$msg. Fix or move it first. Nothing was changed."
  done

  bash "$REPO/scripts/migrate-legacy.sh" "$C" "$X" "$REPO" | while IFS= read -r line; do ok "$line"; done

  mkdir -p "$C/hooks"
  for l in "$C"/hooks/guard*.py; do
    # A module an earlier install linked and this one no longer ships.
    if [[ -L "$l" && ! -e "$l" && "$(readlink "$l")" == */hooks/"${l##*/}" ]]; then rm -f "$l"; fi
  done
  for f in "$REPO"/hooks/guard*.py; do ln -sfn "$f" "$C/hooks/${f##*/}"; done
  ok "linked the guard into $C/hooks"

  # One copy of the user's own file, taken before we first touch it; uninstall restores it.
  for f in "$SETTINGS" "$X/hooks.json" "$HOME/.cursor/hooks.json"; do
    if [[ -f "$f" && ! -e "$f.before-agent-config" ]] && ! grep -q -- '-hook-v1:' "$f"; then
      cp "$f" "$f.before-agent-config"
    fi
  done
  python3 "$REPO/scripts/install_settings.py" merge "$SETTINGS" "$C/hooks"
  ok "merged hooks and deny rules into $SETTINGS"
  for h in ${HOSTS[@]+"${HOSTS[@]}"}; do
    python3 "$REPO/scripts/install_hooks_json.py" merge "${h%%:*}" "${h#*:}" "$REPO"
    ok "merged the guard into ${h#*:}"
  done
fi

for f in "$REPO"/hooks/guard*.py; do
  [[ "$(readlink "$C/hooks/${f##*/}" || true)" == "$f" ]] || bad "$C/hooks/${f##*/} does not link to $f"
done
python3 "$REPO/scripts/install_settings.py" check "$SETTINGS" "$C/hooks" \
  || bad "$SETTINGS does not wire the guard hooks"
for h in ${HOSTS[@]+"${HOSTS[@]}"}; do
  python3 "$REPO/scripts/install_hooks_json.py" check "${h%%:*}" "${h#*:}" "$REPO" \
    || bad "${h#*:} does not wire the guard hooks"
done

# Wiring is not enforcement: prove each rule module refuses, and that ordinary work passes.
probe() {
  local rc=0
  printf '{"tool_name":"Bash","tool_input":{"command":"%s"},"cwd":"/"}' "$1" \
    | PYTHONDONTWRITEBYTECODE=1 python3 "$C/hooks/guard-bash.py" >/dev/null 2>&1 || rc=$?
  echo "$rc"
}
before=$PROBLEMS
if [[ -f "$C/hooks/guard-bash.py" ]]; then
  for cmd in 'rm -rf /' 'git push --force origin main' 'cat ~/.aws/credentials' 'psql -h db.prod.example.com'; do
    [[ "$(probe "$cmd")" == 2 ]] || bad "the guard did not refuse: $cmd"
  done
  [[ "$(probe 'git status')" == 0 ]] || bad "the guard refused ordinary work: git status"
else
  bad "$C/hooks/guard-bash.py is missing"
fi
(( PROBLEMS > before )) || ok "the guard refuses destructive commands and allows git status"
before=$PROBLEMS
for want in 2:"gh%s_%s" 0:hello; do
  [[ "$(printf "{\"prompt\":\"${want#*:}\"}" p "$(printf 'Ab3xQ9%.0s' 1 2 3 4 5 6)" | PYTHONDONTWRITEBYTECODE=1 python3 "$C/hooks/guard-prompt.py" >/dev/null 2>&1; echo $?)" == "${want%%:*}" ]] \
    || bad "the prompt guard did not return ${want%%:*} for a ${want#*:} prompt"
done
(( PROBLEMS > before )) || ok "the prompt guard refuses a pasted token and allows hello"
if [[ -d "$HOME/.cursor" ]]; then
  before=$PROBLEMS
  cursor() { PYTHONDONTWRITEBYTECODE=1 python3 "$REPO/hooks/$1" 2>/dev/null; }
  shell() { printf '{"tool_name":"Shell","tool_input":{"command":"%s","cwd":""},"workspace_roots":["/"]}' "$1"; }
  [[ "$(shell 'git push --force origin main' | cursor guard-cursor.py)" == *'"permission": "deny"'* ]] \
    || bad "the Cursor hook did not refuse: git push --force origin main"
  [[ "$(shell 'git status' | cursor guard-cursor.py)" == '{"permission": "allow"}' ]] \
    || bad "the Cursor hook refused ordinary work: git status"
  [[ "$(printf '{"hook_event_name":"beforeSubmitPrompt","prompt":"gh%s_%s"}' p "$(printf 'Ab3xQ9%.0s' 1 2 3 4 5 6)" | cursor guard-prompt.py)" == *'"continue": false'* ]] \
    || bad "the Cursor prompt hook did not refuse a pasted token"
  (( PROBLEMS > before )) || ok "the Cursor hooks refuse a force push and a pasted token, and allow git status"
fi

if [[ -n "${AGENT_CONFIG_PROTECTED_BRANCHES+set}" ]]; then
  warn "AGENT_CONFIG_PROTECTED_BRANCHES is set: protected branches are '$AGENT_CONFIG_PROTECTED_BRANCHES'"
fi
if [[ -s "$C/guard-failopen.log" ]]; then
  warn "$C/guard-failopen.log is not empty: the guard has failed open before."
fi

if (( PROBLEMS )); then
  echo "$PROBLEMS problem(s). Re-run install to repair."
  exit 1
fi
if (( CHECK )); then
  echo "All good."
else
  echo "Done. Start a new agent session. In Codex, trust the new hook with /hooks. Cursor reloads hooks.json itself; restart it if the hooks do not show up."
fi
