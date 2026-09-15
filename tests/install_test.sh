#!/usr/bin/env bash
# install.sh and uninstall.sh against hostile fake HOMEs. Never touches the real HOME.
# Run: bash tests/install_test.sh   (the migration cases need git tags v0.3.1 and v0.4.2)
set -uo pipefail
REPO_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
S="$(mktemp -d)"
trap 'rm -rf "$S"' EXIT
cp -R "$REPO_SRC" "$S/repo"
rm -rf "$S/repo/.git"
export PYTHONDONTWRITEBYTECODE=1
pass=0; fail=0
chk() {
  if [[ "$2" == "$3" ]]; then pass=$((pass+1)); else echo "  FAIL $1 (got '$2' want '$3')"; fail=$((fail+1)); fi
}
yes_no() { if "$@"; then echo yes; else echo no; fi; }
install() { HOME="$H" bash "$S/repo/install.sh" "$@" >"$S/out" 2>&1; echo $?; }
uninstall() { HOME="$H" bash "$S/repo/uninstall.sh" >"$S/out" 2>&1; echo $?; }
home() { H="$S/$1"; mkdir -p "$H/.claude" "$H/.codex"; }
ours() { find "$H" -type l -lname "$1*" | wc -l | tr -d ' '; }
USER_SETTINGS='{"model":"opus","hooks":{"PreToolUse":[{"matcher":"Bash","hooks":[{"type":"command","command":"python3 ~/mine/wrap.py --after hooks/guard-files.py"}]}]}}'
USER_CODEX='{"description":"mine","hooks":{"Stop":[{"hooks":[{"type":"command","command":"python3 ~/mine/stop.py"}]}]}}'

echo "== fresh install wires both hosts and proves the guard decides"
home fresh
chk "install exits 0" "$(install)" 0
chk "three Claude hooks" "$(grep -c 'agent-config-hook-v1' "$H/.claude/settings.json")" 3
chk "one Codex hook" "$(grep -c 'guard-codex.py' "$H/.codex/hooks.json")" 1
chk "one Codex prompt hook" "$(grep -c 'guard-prompt.py' "$H/.codex/hooks.json")" 1
chk "guard linked" "$(readlink "$H/.claude/hooks/guard-bash.py")" "$S/repo/hooks/guard-bash.py"
chk "no instruction files" "$(yes_no test -e "$H/.claude/CLAUDE.md" -o -e "$H/.codex/AGENTS.md")" no
chk "check exits 0" "$(install --check)" 0
chk "unknown flag refused" "$(install --dry-run)" 1

echo "== the wired command blocks end to end, and degrades to allow when the hooks are gone"
cmd="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["hooks"]["PreToolUse"][0]["hooks"][0]["command"])' "$H/.claude/settings.json")"
run_hook() { printf '{"tool_name":"Bash","tool_input":{"command":"%s"},"cwd":"/"}' "$1" | HOME="$H" sh -c "$cmd" >/dev/null 2>&1; echo $?; }
chk "rm -rf / blocked" "$(run_hook 'rm -rf /')" 2
chk "ls allowed" "$(run_hook 'ls')" 0
pcmd="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"])' "$H/.claude/settings.json")"
chk "pasted token refused" "$(printf '{"prompt":"gh%s_%s"}' p "$(printf 'Ab3xQ9%.0s' 1 2 3 4 5 6)" | HOME="$H" sh -c "$pcmd" >/dev/null 2>&1; echo $?)" 2
mv "$H/.claude/hooks" "$H/hooks.off"
chk "missing hooks allow" "$(run_hook 'rm -rf /')" 0
mv "$H/hooks.off" "$H/.claude/hooks"

echo "== --check notices a guard that no longer decides, and a missing hooks.json"
echo 'import sys' > "$S/stub.py"
ln -sfn "$S/stub.py" "$H/.claude/hooks/guard-bash.py"
chk "check fails" "$(install --check)" 1
chk "every refusal probe reported" "$(grep -c 'did not refuse' "$S/out")" 4
chk "reinstall repairs" "$(install)" 0
ln -sfn "$S/stub.py" "$H/.claude/hooks/guard-prompt.py"
chk "check fails on a prompt guard that allows keys" "$(install --check)" 1
chk "prompt probe reported" "$(grep -c 'prompt guard did not' "$S/out")" 1
chk "reinstall repairs the prompt guard" "$(install)" 0
rm "$H/.codex/hooks.json"
chk "missing Codex hooks.json is caught" "$(install --check)" 1

echo "== user config survives, re-install is idempotent, uninstall is byte-identical"
home roundtrip
printf '%s\n' "$USER_SETTINGS" > "$H/.claude/settings.json"
printf '%s\n' "$USER_CODEX" > "$H/.codex/hooks.json"
cp "$H/.claude/settings.json" "$S/settings.orig"; cp "$H/.codex/hooks.json" "$S/codex.orig"
mkdir -p "$H/.claude/hooks"; echo 'import sys' > "$H/.claude/hooks/my-guard.py"
for _ in 1 2 3; do chk "install exits 0" "$(install)" 0; done
chk "user hook kept" "$(grep -c 'mine/wrap.py' "$H/.claude/settings.json")" 1
chk "no duplicate hooks" "$(grep -c 'agent-config-hook-v1' "$H/.claude/settings.json")" 3
chk "model kept" "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["model"])' "$H/.claude/settings.json")" opus
chk "codex hook kept" "$(grep -c 'mine/stop.py' "$H/.codex/hooks.json")" 1
chk "uninstall exits 0" "$(uninstall)" 0
chk "settings.json byte-identical" "$(yes_no cmp -s "$H/.claude/settings.json" "$S/settings.orig")" yes
chk "hooks.json byte-identical" "$(yes_no cmp -s "$H/.codex/hooks.json" "$S/codex.orig")" yes
chk "their hook script kept" "$(ls "$H/.claude/hooks")" my-guard.py
chk "no litter" "$(ls -A "$H/.claude" "$H/.codex" | tr '\n' ' ')" "$H/.claude: hooks settings.json  $H/.codex: hooks.json "

echo "== uninstall on a never-installed HOME changes nothing"
home never
printf '%s\n' "$USER_SETTINGS" > "$H/.claude/settings.json"
chk "uninstall exits 0" "$(uninstall)" 0
chk "settings.json byte-identical" "$(yes_no cmp -s "$H/.claude/settings.json" "$S/settings.orig")" yes
chk "nothing created" "$(ls -A "$H/.claude" "$H/.codex" | tr '\n' ' ')" "$H/.claude: settings.json  $H/.codex: "

echo "== malformed or occupied config aborts before anything is written"
for bad in '{"model":"opus",}' '["not","an","object"]' '{"hooks":{"PreToolUse":[{"hooks":["x"]}]}}'; do
  home malformed; printf '%s' "$bad" > "$H/.claude/settings.json"
  chk "refused: $bad" "$(install)" 1
  chk "untouched: $bad" "$(cat "$H/.claude/settings.json")" "$bad"
  chk "no hooks dir: $bad" "$(yes_no test -e "$H/.claude/hooks")" no
  rm -rf "$H"
done
home badcodex; echo '{"hooks":{"PreToolUse":"x"}}' > "$H/.codex/hooks.json"
chk "malformed Codex hooks refused" "$(install)" 1
chk "Claude side not wired" "$(yes_no test -e "$H/.claude/settings.json")" no
home occupied; mkdir -p "$H/.claude/hooks"; echo mine > "$H/.claude/hooks/guard-bash.py"
chk "a file of theirs at our hook path is refused" "$(install)" 1
chk "their file untouched" "$(cat "$H/.claude/hooks/guard-bash.py")" mine
home nopy; mkdir -p "$S/nopy"
for c in bash dirname readlink git; do ln -sf "$(command -v "$c")" "$S/nopy/$c"; done
chk "no python3 refused" "$(HOME="$H" PATH="$S/nopy" bash "$S/repo/install.sh" >/dev/null 2>&1; echo $?)" 1
chk "nothing written" "$(ls -A "$H/.claude")" ""

echo "== CLAUDE_CONFIG_DIR and CODEX_HOME are respected"
home custom; mkdir -p "$S/cc" "$S/cx"
export CLAUDE_CONFIG_DIR="$S/cc" CODEX_HOME="$S/cx"
chk "install exits 0" "$(install)" 0
chk "Claude settings in custom dir" "$(grep -c 'agent-config-hook-v1' "$S/cc/settings.json")" 3
chk "Codex hooks in custom dir" "$(grep -c 'guard-codex.py' "$S/cx/hooks.json")" 1
chk "default dirs untouched" "$(ls -A "$H/.claude" "$H/.codex" | tr '\n' ' ')" "$H/.claude:  $H/.codex: "
chk "check exits 0" "$(install --check)" 0
echo x > "$S/cc/guard-failopen.log"
install --check >/dev/null
chk "fail-open log read from custom dir" "$(grep -c "$S/cc/guard-failopen.log is not empty" "$S/out")" 1
rm "$S/cc/guard-failopen.log"
chk "uninstall exits 0" "$(uninstall)" 0
chk "custom dirs emptied" "$(ls -A "$S/cc" "$S/cx" | tr '\n' ' ')" "$S/cc:  $S/cx: "
unset CLAUDE_CONFIG_DIR CODEX_HOME

echo "== a dotfile-managed settings.json stays a link"
home dots; mkdir -p "$H/dots"; printf '{"model":"opus"}' > "$H/dots/settings.json"
ln -s "$H/dots/settings.json" "$H/.claude/settings.json"
chk "install exits 0" "$(install)" 0
chk "still a link" "$(readlink "$H/.claude/settings.json")" "$H/dots/settings.json"
chk "target wired" "$(grep -c 'agent-config-hook-v1' "$H/dots/settings.json")" 3
chk "uninstall exits 0" "$(uninstall)" 0
chk "link kept" "$(readlink "$H/.claude/settings.json")" "$H/dots/settings.json"
chk "target restored" "$(cat "$H/dots/settings.json")" '{"model":"opus"}'

echo "== invoked through a symlink, from a path with a space and an apostrophe"
mkdir -p "$S/it's mine"; cp -R "$S/repo" "$S/it's mine/repo"; ln -s "$S/it's mine/repo/install.sh" "$S/inst"
home odd
chk "install exits 0" "$(HOME="$H" bash "$S/inst" >/dev/null 2>&1; echo $?)" 0
chk "links into the real repo" "$(readlink "$H/.claude/hooks/guard-bash.py")" "$S/it's mine/repo/hooks/guard-bash.py"
cmd="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["hooks"]["PreToolUse"][0]["hooks"][0]["command"])' "$H/.codex/hooks.json")"
chk "Codex command runs the guard" "$(printf '{"tool_name":"Bash","tool_input":{"command":"rm -rf /"},"cwd":"/"}' | sh -c "$cmd" >/dev/null 2>&1; echo $?)" 2

echo "== an upgrade prunes the superseded payload"
home upgrade
old="$H/.local/share/agent-config/0.0.1"; new="$H/.local/share/agent-config/$(cat "$S/repo/VERSION")"
mkdir -p "$(dirname "$old")"; cp -R "$S/repo" "$old"; echo 0.0.1 > "$old/VERSION"
chk "old install" "$(HOME="$H" bash "$old/install.sh" >/dev/null 2>&1; echo $?)" 0
cp -R "$S/repo" "$new"
chk "new install" "$(HOME="$H" bash "$new/install.sh" >"$S/out" 2>&1; echo $?)" 0
chk "old payload removed" "$(yes_no test -e "$old")" no
chk "no link into it" "$(ours "$old/")" 0
chk "Codex points at new" "$(grep -c "$new/hooks/guard-codex.py" "$H/.codex/hooks.json")" 1

# An old release installed the way its npx CLI did: staged under ~/.local/share/<name>/<version>.
legacy() {  # legacy <version> <share name>
  local p="$H/.local/share/$2/$1"
  mkdir -p "$p" "$H/.claude/skills/review" "$H/dots/theirs"
  git -C "$REPO_SRC" archive "v$1" | tar -x -C "$p" || return 1
  printf 'user instructions\n' > "$H/.claude/CLAUDE.md"
  printf '{"model":"opus"}\n' > "$H/.claude/settings.json"
  echo mine > "$H/.claude/skills/review/SKILL.md"
  ln -s "$H/dots/theirs" "$H/.claude/skills/theirs"
  (cd "$p" && HOME="$H" ONBELAY_NONINTERACTIVE=1 AGENT_CONFIG_NONINTERACTIVE=1 \
    bash install.sh full --replace-conflicts </dev/null >/dev/null 2>&1)
}
clean_after_legacy() {  # clean_after_legacy <payload>
  chk "no link into the old payload" "$(ours "$1/")" 0
  chk "old payload removed" "$(yes_no test -e "$1")" no
  chk "no onbelay share" "$(yes_no test -e "$H/.local/share/onbelay")" no
  chk "CLAUDE.md is theirs again" "$(cat "$H/.claude/CLAUDE.md")" "user instructions"
  chk "Codex AGENTS.md link removed" "$(yes_no test -L "$H/.codex/AGENTS.md")" no
  chk "moved-aside skill restored" "$(cat "$H/.claude/skills/review/SKILL.md")" mine
  chk "their skill link kept" "$(readlink "$H/.claude/skills/theirs")" "$H/dots/theirs"
  chk "no legacy state files" "$(find "$H/.claude" -maxdepth 1 \( -name '*origins' -o -name '*onbelay*' -o -name 'CLAUDE.md.before*' -o -name output-styles \) | wc -l | tr -d ' ')" 0
  chk "no legacy hook tags" "$(grep -c 'onbelay-hook-v1' "$H/.claude/settings.json" "$H/.codex/hooks.json" 2>/dev/null | grep -vc ':0$')" 0
}
if ! git -C "$REPO_SRC" rev-parse -q --verify v0.4.2 >/dev/null || ! git -C "$REPO_SRC" rev-parse -q --verify v0.3.1 >/dev/null; then
  echo "  FAIL the migration cases need tags v0.3.1 and v0.4.2 (fetch with tags)"; fail=$((fail+1))
else
  for spec in 0.4.2:onbelay 0.3.1:agent-config; do
    v="${spec%%:*}"; name="${spec#*:}"
    echo "== $v ($name) upgrades to only the new guard"
    home "up-$v"
    chk "old release installed" "$(legacy "$v" "$name"; echo $?)" 0
    chk "old release wired skills" "$(yes_no test -L "$H/.claude/skills/ship")" yes
    chk "install exits 0" "$(install)" 0
    clean_after_legacy "$H/.local/share/$name/$v"
    chk "three new Claude hooks" "$(grep -c 'agent-config-hook-v1' "$H/.claude/settings.json")" 3
    chk "one Codex hook" "$(grep -c 'guard-codex.py' "$H/.codex/hooks.json")" 1
    chk "check exits 0" "$(install --check)" 0
    chk "uninstall exits 0" "$(uninstall)" 0
    chk "settings.json back to the pre-$v bytes" "$(cat "$H/.claude/settings.json")" '{"model":"opus"}'
    chk "only their files remain" "$(ls -A "$H/.claude" "$H/.codex" | tr '\n' ' ')" "$H/.claude: CLAUDE.md settings.json skills  $H/.codex: "

    echo "== $v ($name) uninstalls directly"
    home "down-$v"
    chk "old release installed" "$(legacy "$v" "$name"; echo $?)" 0
    chk "uninstall exits 0" "$(uninstall)" 0
    clean_after_legacy "$H/.local/share/$name/$v"
    chk "settings.json back to the pre-$v bytes" "$(cat "$H/.claude/settings.json")" '{"model":"opus"}'
    chk "only their files remain" "$(ls -A "$H/.claude" "$H/.codex" | tr '\n' ' ')" "$H/.claude: CLAUDE.md settings.json skills  $H/.codex: "
  done
fi

echo
echo "$pass passed, $fail failed"
(( fail == 0 ))
