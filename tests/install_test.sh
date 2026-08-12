#!/usr/bin/env bash
# Exercise install.sh against hostile fake HOMEs. Never touches the real HOME.
set -uo pipefail
# Exercises install.sh and uninstall.sh against hostile fake HOME directories.
# Never touches the real HOME. Run: bash tests/install_test.sh
S="$(mktemp -d)"
REPO_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
trap 'rm -rf "$S"' EXIT
cp -R "$REPO_SRC" "$S/repo"
rm -rf "$S/repo/.git"
pass=0; fail=0
chk() { if [[ "$2" == "$3" ]]; then echo "  ✓ $1"; pass=$((pass+1)); else echo "  ✗ $1 (got '$2' want '$3')"; fail=$((fail+1)); fi; }

echo "== 1. the public default installs only the guard =="
H="$S/h1"; mkdir -p "$H"
HOME="$H" bash "$S/repo/install.sh" >/dev/null 2>&1; chk "exit 0" "$?" "0"
chk "workflow is not installed by default" "$([ -e "$H/.claude/skills/ship" ] && echo yes || echo no)" "no"
chk "settings has hook" "$(grep -c guard-bash "$H/.claude/settings.json")" "1"

echo "== 1b. a normal install still gates on both guard suites =="
mv "$S/repo/hooks/tests.py" "$S/repo/hooks/tests.py.real"
printf '#!/usr/bin/env python3\nraise SystemExit(1)\n' > "$S/repo/hooks/tests.py"
H="$S/h1b"; mkdir -p "$H"
HOME="$H" bash "$S/repo/install.sh" full >/dev/null 2>&1
chk "a broken rule suite aborts" "$?" "1"
chk "rule failure leaves no install" "$([ -e "$H/.claude/skills/ship" ] && echo yes || echo no)" "no"
mv "$S/repo/hooks/tests.py.real" "$S/repo/hooks/tests.py"

mv "$S/repo/hooks/floor.py" "$S/repo/hooks/floor.py.real"
printf '#!/usr/bin/env python3\nraise SystemExit(1)\n' > "$S/repo/hooks/floor.py"
H="$S/h1c"; mkdir -p "$H"
HOME="$H" bash "$S/repo/install.sh" full >/dev/null 2>&1
chk "a broken floor suite aborts" "$?" "1"
chk "floor failure leaves no install" "$([ -e "$H/.claude/skills/ship" ] && echo yes || echo no)" "no"
mv "$S/repo/hooks/floor.py.real" "$S/repo/hooks/floor.py"

# Guard behavior is static across fake HOMEs. It passed in test 1, and tests
# 1b/1c proved the real installer stops when either suite fails. Keep the full
# suites for their later direct check, then make only this disposable clone's
# repeated installer calls cheap. Production install.sh has no bypass.
cp "$S/repo/hooks/tests.py" "$S/repo/hooks/tests.py.installer-full"
cp "$S/repo/hooks/floor.py" "$S/repo/hooks/floor.py.installer-full"
printf '#!/usr/bin/env python3\nprint("PASS (already proved by installer matrix)")\n' > "$S/repo/hooks/tests.py"
printf '#!/usr/bin/env python3\nprint("PASS (already proved by installer matrix)")\n' > "$S/repo/hooks/floor.py"

echo "== 2. an occupied path is refused, and nothing of theirs is touched =="
H="$S/h2"; mkdir -p "$H/.claude/skills/my-own-skill"
echo "mine" > "$H/.claude/skills/my-own-skill/SKILL.md"
echo "my personal instructions" > "$H/.claude/CLAUDE.md"
cat > "$H/.claude/settings.json" <<'EOF'
{"model":"opus","permissions":{"allow":["Bash(ls:*)"]},"hooks":{"PreToolUse":[{"matcher":"Bash","hooks":[{"type":"command","command":"my-own-hook.sh"}]}]}}
EOF
out="$(HOME="$H" bash "$S/repo/install.sh" full --baseline 2>&1)"; code=$?
chk "refuses rather than taking the path" "$code" "1"
chk "names the occupied path" "$(grep -c 'CLAUDE.md' <<<"$out")" "1"
chk "offers the mv that clears it" "$(grep -c 'mv .*CLAUDE.md .*CLAUDE.md.mine' <<<"$out")" "1"
# The point of the whole change: an install attempt must be a no-op.
chk "their CLAUDE.md is byte-identical" "$(cat "$H/.claude/CLAUDE.md")" "my personal instructions"
chk "not replaced by our symlink" "$([ -L "$H/.claude/CLAUDE.md" ] && echo yes || echo no)" "no"
chk "no backup litter left behind" \
  "$(find "$H/.claude" -maxdepth 1 -mindepth 1 \
     \( -name '*.bak-*' -o -name '*.baklink-*' \) -print | wc -l | tr -d ' ')" "0"
chk "settings.json untouched" "$(grep -c guard- "$H/.claude/settings.json")" "0"
chk "nothing installed at all" "$([ -L "$H/.claude/skills/ship" ] && echo yes || echo no)" "no"

# Their own skill is NOT a conflict: we ship no skill by that name, so it is
# left exactly where it is and keeps working.
chk "a skill of theirs we do not ship is not a conflict" \
  "$(grep -c 'my-own-skill' <<<"$out")" "0"

echo "== 2b. once they move it aside, the install goes through =="
mv "$H/.claude/CLAUDE.md" "$H/.claude/CLAUDE.md.mine"
HOME="$H" bash "$S/repo/install.sh" full --baseline >/dev/null 2>&1; chk "exit 0" "$?" "0"
chk "their moved file is still theirs" "$(cat "$H/.claude/CLAUDE.md.mine")" "my personal instructions"
chk "user model preserved" "$(python3 -c "import json;print(json.load(open('$H/.claude/settings.json'))['model'])")" "opus"
chk "user permissions preserved" "$(python3 -c "import json;print(json.load(open('$H/.claude/settings.json'))['permissions']['allow'][0])")" "Bash(ls:*)"
chk "user's own hook preserved" "$(grep -c my-own-hook "$H/.claude/settings.json")" "1"
chk "user's own skill STILL WORKS in place" "$(cat "$H/.claude/skills/my-own-skill/SKILL.md" 2>/dev/null)" "mine"
chk "our skills linked alongside" "$([ -L "$H/.claude/skills/ship" ] && echo yes || echo no)" "yes"
chk "settings.json copied once before the first change" \
  "$([ -f "$H/.claude/settings.json.before-agent-config" ] && echo yes || echo no)" "yes"

echo "== 3. idempotent: run 3x, no duplicate hook entries =="
HOME="$H" bash "$S/repo/install.sh" full >/dev/null 2>&1
HOME="$H" bash "$S/repo/install.sh" full >/dev/null 2>&1
chk "one Bash guard hook entry" "$(python3 -c "
import json;c=json.load(open('$H/.claude/settings.json'))
e=[x for x in c['hooks']['PreToolUse'] if x['matcher']=='Bash'][0]
print(len([h for h in e['hooks'] if 'guard-' in h['command']]))")" "1"
chk "user hook still there" "$(grep -c my-own-hook "$H/.claude/settings.json")" "1"

echo "== 4. malformed settings.json must ABORT, not clobber =="
H="$S/h4"; mkdir -p "$H/.claude"
printf '{"model":"opus",}\n' > "$H/.claude/settings.json"
HOME="$H" bash "$S/repo/install.sh" full >/dev/null 2>&1; chk "exits nonzero" "$([ $? -ne 0 ] && echo yes || echo no)" "yes"
chk "settings untouched" "$(cat "$H/.claude/settings.json")" '{"model":"opus",}'
chk "no partial install" "$([ -e "$H/.claude/skills" ] && echo yes || echo no)" "no"

echo "== 5. no python3 must abort before mutating =="
H="$S/h5"; mkdir -p "$H"; B="$S/nopy"; mkdir -p "$B"
for c in bash cp ln rm mkdir date dirname basename grep sed cat git readlink; do
  p=$(command -v $c 2>/dev/null) && ln -sf "$p" "$B/$c"
done
HOME="$H" PATH="$B" bash "$S/repo/install.sh" full >/dev/null 2>&1; chk "exits nonzero" "$([ $? -ne 0 ] && echo yes || echo no)" "yes"
chk "nothing installed" "$([ -e "$H/.claude/skills" ] && echo yes || echo no)" "no"

echo "== 5b. guard --check aggregates a missing Python prerequisite =="
H="$S/h5b"; mkdir -p "$H"
out="$(HOME="$H" PATH="$B" bash "$S/repo/install.sh" guard --check 2>&1)"; rc=$?
chk "check exits nonzero" "$([ $rc -ne 0 ] && echo yes || echo no)" "yes"
chk "check reaches its summary" "$(grep -c 'Check complete:' <<<"$out")" "1"
chk "check emits no shell command-not-found error" "$(grep -c 'command not found' <<<"$out")" "0"

echo "== 6. --check is read-only =="
H="$S/h6"; mkdir -p "$H"
HOME="$H" bash "$S/repo/install.sh" full --check >/dev/null 2>&1
chk "no ~/.claude created" "$([ -e "$H/.claude" ] && echo yes || echo no)" "no"

echo "== 7. repo path with a space =="
mkdir -p "$S/with space"; cp -R "$S/repo" "$S/with space/repo"
H="$S/h7"; mkdir -p "$H"
HOME="$H" bash "$S/with space/repo/install.sh" full >/dev/null 2>&1; chk "exit 0" "$?" "0"
chk "skills linked" "$([ -L "$H/.claude/skills/ship" ] && echo yes || echo no)" "yes"

echo "== 8. uninstall restores cleanly =="
H="$S/h8"; mkdir -p "$H/.claude/skills/my-own-skill"; echo mine > "$H/.claude/skills/my-own-skill/SKILL.md"
cat > "$H/.claude/settings.json" <<'EOF'
{"model":"opus","hooks":{"PreToolUse":[{"matcher":"Bash","hooks":[{"type":"command","command":"my-own-hook.sh"}]}]}}
EOF
HOME="$H" bash "$S/repo/install.sh" full >/dev/null 2>&1
HOME="$H" bash "$S/repo/uninstall.sh" >/dev/null 2>&1; chk "uninstall exit 0" "$?" "0"
chk "guard hook gone" "$(grep -c guard-bash "$H/.claude/settings.json" 2>/dev/null | head -1)" "0"
chk "user hook survived" "$(grep -c my-own-hook "$H/.claude/settings.json")" "1"
chk "model survived" "$(python3 -c "import json;print(json.load(open('$H/.claude/settings.json'))['model'])")" "opus"
chk "our skill links removed" "$([ -e "$H/.claude/skills/ship" ] && echo yes || echo no)" "no"
chk "user skill untouched by uninstall" "$(cat "$H/.claude/skills/my-own-skill/SKILL.md" 2>/dev/null)" "mine"

echo "== 9. the wired hook command actually BLOCKS end to end =="
# Regression guard. A `test -f X && python3 X || exit 0` wrapper looks safe but
# swallows the block: python3 exits 2, which is falsy, so `|| exit 0` fires and
# the command is ALLOWED. This runs the exact string install.sh wrote.
H="$S/h9"; mkdir -p "$H"
HOME="$H" bash "$S/repo/install.sh" full >/dev/null 2>&1
CMD=$(HOME="$H" python3 -c "
import json
c=json.load(open('$H/.claude/settings.json'))
e=[x for x in c['hooks']['PreToolUse'] if x['matcher']=='Bash'][0]
print([h['command'] for h in e['hooks'] if 'guard-' in h['command']][0])")
R=$(mktemp -d); git -C "$R" init -q; git -C "$R" symbolic-ref HEAD refs/heads/main
git -C "$R" -c user.email=t@t.t -c user.name=t commit -q --allow-empty -m init
OUT=$(echo "{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"git checkout .\"},\"cwd\":\"$R\"}" \
      | HOME="$H" sh -c "$CMD" 2>&1); RC=$?
chk "blocking command exits 2" "$RC" "2"
chk "reason reaches stderr" "$(echo "$OUT" | grep -c BLOCKED)" "1"
OUT2=$(echo "{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"ls -la\"},\"cwd\":\"$R\"}" \
       | HOME="$H" sh -c "$CMD" >/dev/null 2>&1; echo $?)
chk "safe command exits 0" "$OUT2" "0"
# repo deleted: must degrade to allow, never to block-everything
rm -rf "$H/.claude/hooks"
RC3=$(echo '{"tool_name":"Bash","tool_input":{"command":"git checkout ."}}' \
      | HOME="$H" sh -c "$CMD" >/dev/null 2>&1; echo $?)
chk "missing hooks dir degrades to allow" "$RC3" "0"
rm -rf "$R"

echo "== 10. the user's own hooks keep working =="
# Replacing ~/.claude/hooks wholesale would leave the user's own settings.json
# entry pointing at a missing script. python3 exits 2 on a missing file, and
# exit 2 in PreToolUse means BLOCK, so their hook becomes block-everything.
H="$S/h10"; mkdir -p "$H/.claude/hooks"
printf '#!/usr/bin/env python3\nimport sys\nsys.exit(0)\n' > "$H/.claude/hooks/my-guard.py"
chmod +x "$H/.claude/hooks/my-guard.py"
HOME="$H" bash "$S/repo/install.sh" full >/dev/null 2>&1
chk "user's own hook script still present" "$([ -f "$H/.claude/hooks/my-guard.py" ] && echo yes || echo no)" "yes"
chk "it still runs" "$(python3 "$H/.claude/hooks/my-guard.py" </dev/null >/dev/null 2>&1; echo $?)" "0"
chk "our hooks linked alongside" "$([ -L "$H/.claude/hooks/guard-bash.py" ] && echo yes || echo no)" "yes"

echo "== 11. an occupied CLAUDE.md is refused; uninstall is still a round trip =="
H="$S/h11"; mkdir -p "$H/.claude"
echo "my personal instructions" > "$H/.claude/CLAUDE.md"
HOME="$H" bash "$S/repo/install.sh" full --baseline >/dev/null 2>&1; chk "refused" "$?" "1"
chk "their CLAUDE.md untouched" "$(cat "$H/.claude/CLAUDE.md")" "my personal instructions"
chk "not a symlink" "$([ -L "$H/.claude/CLAUDE.md" ] && echo yes || echo no)" "no"
mv "$H/.claude/CLAUDE.md" "$H/.claude/CLAUDE.md.mine"
HOME="$H" bash "$S/repo/install.sh" full --baseline >/dev/null 2>&1; chk "installs once moved" "$?" "0"
HOME="$H" bash "$S/repo/uninstall.sh" >/dev/null 2>&1
chk "our link is gone" "$([ -L "$H/.claude/CLAUDE.md" ] && echo yes || echo no)" "no"
chk "their file was never involved" "$(cat "$H/.claude/CLAUDE.md.mine")" "my personal instructions"

echo "== 12. a colliding Codex skill name is refused, not absorbed =="
H="$S/h12"; mkdir -p "$H/.codex/skills/review"
echo "their review" > "$H/.codex/skills/review/SKILL.md"
out="$(HOME="$H" bash "$S/repo/install.sh" full 2>&1)"; chk "refused" "$?" "1"
chk "names their skill path" "$(grep -c '.codex/skills/review' <<<"$out")" "1"
chk "their review is untouched" "$(cat "$H/.codex/skills/review/SKILL.md")" "their review"
chk "nothing of ours nested inside it" "$(ls "$H/.codex/skills/review" | tr -d ' \n')" "SKILL.md"

echo "== 13. a symlinked CLAUDE.md (stow/chezmoi) round-trips =="
H="$S/h13"; mkdir -p "$H/.claude" "$H/dotfiles"
echo "managed by stow" > "$H/dotfiles/CLAUDE.md"
ln -s "$H/dotfiles/CLAUDE.md" "$H/.claude/CLAUDE.md"
HOME="$H" bash "$S/repo/install.sh" full >/dev/null 2>&1
HOME="$H" bash "$S/repo/uninstall.sh" >/dev/null 2>&1
chk "original symlink restored" "$(readlink "$H/.claude/CLAUDE.md")" "$H/dotfiles/CLAUDE.md"
chk "content reachable again" "$(cat "$H/.claude/CLAUDE.md" 2>/dev/null)" "managed by stow"

echo "== 14. tests.py is not linked as a hook =="
H="$S/h14"; mkdir -p "$H"
HOME="$H" bash "$S/repo/install.sh" full >/dev/null 2>&1
chk "tests.py not in hooks dir" "$([ -e "$H/.claude/hooks/tests.py" ] && echo yes || echo no)" "no"
chk "guard scripts are" "$([ -L "$H/.claude/hooks/guard-bash.py" ] && echo yes || echo no)" "yes"

echo "== 15. odd-but-parseable settings.json aborts before mutating =="
H="$S/h15"; mkdir -p "$H/.claude"
echo '["not", "an", "object"]' > "$H/.claude/settings.json"
HOME="$H" bash "$S/repo/install.sh" full >/dev/null 2>&1
chk "exits nonzero" "$([ $? -ne 0 ] && echo yes || echo no)" "yes"
chk "nothing installed" "$([ -e "$H/.claude/skills/ship" ] && echo yes || echo no)" "no"
chk "settings untouched" "$(cat "$H/.claude/settings.json")" '["not", "an", "object"]'

echo "== 16. a dotfile-managed HOME is refused, never unloaded =="
# stow/chezmoi point whole directories elsewhere. The old contract replaced
# them and promised to put them back; this one does not take them at all.
H="$S/h16"; mkdir -p "$H/.claude" "$H/dots/skills/mine" "$H/dots/hooks"
echo "my skill" > "$H/dots/skills/mine/SKILL.md"
echo "my hook"  > "$H/dots/hooks/my-guard.py"
ln -s "$H/dots/skills" "$H/.claude/skills"
ln -s "$H/dots/hooks"  "$H/.claude/hooks"
out="$(HOME="$H" bash "$S/repo/install.sh" full 2>&1)"; chk "refused" "$?" "1"
chk "both managed directories named" \
  "$(grep -cE 'mv .*\.claude/(skills|hooks) ' <<<"$out")" "2"
chk "skills link still theirs" "$(readlink "$H/.claude/skills")" "$H/dots/skills"
chk "hooks link still theirs" "$(readlink "$H/.claude/hooks")" "$H/dots/hooks"
chk "their skill still loads" "$(cat "$H/.claude/skills/mine/SKILL.md")" "my skill"
chk "no baklink bookkeeping was invented" \
  "$(find "$H/.claude" -maxdepth 1 -mindepth 1 -name '*baklink*' -print \
     | wc -l | tr -d ' ')" "0"

echo "== 17. a per-skill symlink of theirs is refused =="
H="$S/h17"; mkdir -p "$H/.claude/skills" "$H/dots/review"
echo "their review" > "$H/dots/review/SKILL.md"
ln -s "$H/dots/review" "$H/.claude/skills/review"
HOME="$H" bash "$S/repo/install.sh" full >/dev/null 2>&1; chk "refused" "$?" "1"
chk "their link is intact" "$(readlink "$H/.claude/skills/review")" "$H/dots/review"
chk "their skill still loads" "$(cat "$H/.claude/skills/review/SKILL.md")" "their review"

echo "== 18. existing Codex hooks survive install and uninstall =="
H="$S/h18"; mkdir -p "$H/.codex"
cat > "$H/.codex/hooks.json" <<'JSON'
{"description":"mine","hooks":{"Stop":[{"hooks":[{"type":"command","command":"python3 ~/mine/stop.py"}]}]}}
JSON
HOME="$H" bash "$S/repo/install.sh" full >/dev/null 2>&1
chk "install accepts their hooks file" "$?" "0"
chk "their description survives" \
  "$(python3 -c "import json;print(json.load(open('$H/.codex/hooks.json'))['description'])")" "mine"
chk "their hook survives install" "$(grep -cF -- 'mine/stop.py' "$H/.codex/hooks.json")" "1"
chk "our PreToolUse is wired" "$(grep -cF -- 'guard-codex.py' "$H/.codex/hooks.json")" "1"
chk "we add no Stop hook" "$(grep -cF -- 'check-docs.py' "$H/.codex/hooks.json")" "0"
chk "we add no SessionStart hook" "$(grep -cF -- 'welcome.py' "$H/.codex/hooks.json")" "0"
chk "their original file has one recovery copy" \
  "$(grep -cF -- 'mine/stop.py' "$H/.codex/hooks.json.before-agent-config")" "1"
HOME="$H" bash "$S/repo/uninstall.sh" >/dev/null 2>&1
chk "their hooks file remains" "$([ -f "$H/.codex/hooks.json" ] && echo yes || echo no)" "yes"
chk "their hook survives uninstall" "$(grep -cF -- 'mine/stop.py' "$H/.codex/hooks.json")" "1"
chk "our hooks are removed" "$(grep -cF -- "$S/repo/hooks/" "$H/.codex/hooks.json")" "0"

echo "== 18b. malformed or symlinked Codex hooks abort before mutation =="
H="$S/h18b"; mkdir -p "$H/.codex"
echo '{"hooks":{"PreToolUse":[{"hooks":["not-an-object"]}]}}' > "$H/.codex/hooks.json"
before=$(cat "$H/.codex/hooks.json")
HOME="$H" bash "$S/repo/install.sh" full >/dev/null 2>&1
chk "malformed hooks are refused" "$?" "1"
chk "malformed file is untouched" "$(cat "$H/.codex/hooks.json")" "$before"
chk "Claude half was not installed" "$([ -e "$H/.claude/skills/ship" ] && echo yes || echo no)" "no"
H="$S/h18c"; mkdir -p "$H/.codex" "$H/dots"
echo '{"hooks":{}}' > "$H/dots/hooks.json"
ln -s "$H/dots/hooks.json" "$H/.codex/hooks.json"
HOME="$H" bash "$S/repo/install.sh" full >/dev/null 2>&1
chk "dotfile-managed hooks are refused" "$?" "1"
chk "their hooks symlink survives" "$(readlink "$H/.codex/hooks.json")" "$H/dots/hooks.json"
HOME="$H" bash "$S/repo/uninstall.sh" >/dev/null 2>&1
chk "uninstall leaves their hooks symlink" "$(readlink "$H/.codex/hooks.json")" "$H/dots/hooks.json"
chk "uninstall leaves its target" "$(cat "$H/dots/hooks.json")" '{"hooks":{}}'
H="$S/h18d"; mkdir -p "$H/.codex" "$H/dots"
ln -s "$H/dots/missing.json" "$H/.codex/hooks.json"
HOME="$H" bash "$S/repo/install.sh" full >/dev/null 2>&1
chk "a dangling hooks symlink is refused" "$?" "1"
chk "the dangling symlink survives" "$(readlink "$H/.codex/hooks.json")" "$H/dots/missing.json"

echo "== 19. install x3 then uninstall leaves nothing of ours behind =="
H="$S/h19"; mkdir -p "$H/.claude"
for _ in 1 2 3; do HOME="$H" bash "$S/repo/install.sh" full >/dev/null 2>&1; done
HOME="$H" bash "$S/repo/uninstall.sh" >/dev/null 2>&1
LEFT=$(find "$H" -type l 2>/dev/null | while read -r l; do
         [[ "$(readlink "$l")" == "$S/repo"* ]] && echo "$l"; done | wc -l | tr -d ' ')
chk "no symlinks into the repo remain" "$LEFT" "0"
chk "guard hooks stripped" "$(grep -c guard-bash "$H/.claude/settings.json" 2>/dev/null | head -1)" "0"

echo "== 20. a stow-managed settings.json is refused, not dereferenced =="
# The most dangerous of the lot under the old contract: replacing the link with
# a real file left the settings looking fine while silently detaching them from
# the user's dotfiles repo, where they would never notice.
H="$S/h20"; mkdir -p "$H/.claude" "$H/dots"
echo '{"model":"opus"}' > "$H/dots/settings.json"
ln -s "$H/dots/settings.json" "$H/.claude/settings.json"
HOME="$H" bash "$S/repo/install.sh" full >/dev/null 2>&1; chk "refused" "$?" "1"
chk "dotfile source untouched" "$(cat "$H/dots/settings.json")" '{"model":"opus"}'
chk "still their symlink" "$([ -L "$H/.claude/settings.json" ] && echo yes || echo no)" "yes"
chk "still points at their tree" "$(readlink "$H/.claude/settings.json")" "$H/dots/settings.json"

echo "== 21. inner hook entries of the wrong type abort before mutating =="
H="$S/h21"; mkdir -p "$H/.claude"
echo '{"hooks":{"PreToolUse":[{"matcher":"Bash","hooks":["not-an-object"]}]}}' > "$H/.claude/settings.json"
HOME="$H" bash "$S/repo/install.sh" full >/dev/null 2>&1
chk "exits nonzero" "$([ $? -ne 0 ] && echo yes || echo no)" "yes"
chk "nothing installed" "$([ -e "$H/.claude/skills/ship" ] && echo yes || echo no)" "no"

echo "== 22. a user hook that merely MENTIONS our path survives =="
# A substring match once deleted `python3 ~/mine/wrap.py --after
# hooks/guard-files.py` on install, and uninstall removed it even on a HOME
# where we were never installed.
H="$S/h22"; mkdir -p "$H/.claude"
cat > "$H/.claude/settings.json" <<'EOF'
{"hooks":{"PreToolUse":[{"matcher":"Bash","hooks":[{"type":"command","command":"python3 ~/mine/wrap.py --after hooks/guard-files.py"}]}]}}
EOF
cp "$H/.claude/settings.json" "$S/h22-original.json"
HOME="$H" bash "$S/repo/install.sh" full >/dev/null 2>&1
chk "survives install" "$(grep -c 'mine/wrap.py' "$H/.claude/settings.json")" "1"
HOME="$H" bash "$S/repo/uninstall.sh" >/dev/null 2>&1
chk "survives uninstall" "$(grep -c 'mine/wrap.py' "$H/.claude/settings.json")" "1"
chk "our hooks are gone" "$(grep -c 'claude/hooks/guard-bash.py' "$H/.claude/settings.json" 2>/dev/null | head -1)" "0"

echo "== 23. uninstall on a never-installed HOME leaves it alone =="
H="$S/h23"; mkdir -p "$H/.claude"
cp "$S/h22-original.json" "$H/.claude/settings.json"
HOME="$H" bash "$S/repo/uninstall.sh" >/dev/null 2>&1
chk "settings.json byte-identical" "$(cmp -s "$H/.claude/settings.json" "$S/h22-original.json" && echo same || echo changed)" "same"

echo "== 24. an apostrophe in the repo path is safely quoted =="
mkdir -p "$S/it's-mine"; cp -R "$S/repo" "$S/it's-mine/repo"
H="$S/h24"; mkdir -p "$H/.codex"
HOME="$H" bash "$S/it's-mine/repo/install.sh" full >/dev/null 2>&1
chk "installs" "$?" "0"
cmd=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["hooks"]["PreToolUse"][0]["hooks"][0]["command"])' "$H/.codex/hooks.json")
chk "hook command parses" "$(bash -n -c "$cmd"; echo $?)" "0"
HOME="$H" bash -c "$cmd" <<<'{"tool_name":"Bash","tool_input":{"command":"echo safe"},"cwd":"/tmp"}' >/dev/null 2>&1
chk "hook command runs" "$?" "0"

echo "== 25. a repo path with regex metacharacters still works =="
# `[ ( + *` are legal in a path but meaningful to grep. Unescaped, both the
# install and uninstall greps missed, so hooks.json was re-backed-up every run
# and uninstall never restored the user's.
mkdir -p "$S/proj[v1]+(x)"; cp -R "$S/repo" "$S/proj[v1]+(x)/repo"
H="$S/h25"; mkdir -p "$H/.codex"
HOME="$H" bash "$S/proj[v1]+(x)/repo/install.sh" full >/dev/null 2>&1; chk "exit 0" "$?" "0"
# Assert the file exists and parses BEFORE deriving cmd. Without this the next
# two assertions pass vacuously when nothing was written at all: python errors,
# cmd is empty, and `bash -n -c ""` succeeds.
chk "codex hooks.json is valid JSON" "$(python3 -c 'import json,sys;json.load(open(sys.argv[1]));print("yes")' "$H/.codex/hooks.json" 2>/dev/null || echo no)" "yes"
cmd=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["hooks"]["PreToolUse"][0]["hooks"][0]["command"])' "$H/.codex/hooks.json" 2>/dev/null)
chk "codex hook command is non-empty" "$([ -n "$cmd" ] && echo yes || echo no)" "yes"
chk "codex hook runs our script" "$(grep -cF -- "guard-codex.py" <<<"$cmd")" "1"
chk "codex hook is valid shell" "$(bash -n -c "$cmd" 2>/dev/null && echo yes || echo no)" "yes"
HOME="$H" bash "$S/proj[v1]+(x)/repo/install.sh" full >/dev/null 2>&1
chk "no backup of a file we wrote" "$(ls "$H"/.codex/hooks.json.bak-* 2>/dev/null | wc -l | tr -d ' ')" "0"
HOME="$H" bash "$S/proj[v1]+(x)/repo/uninstall.sh" >/dev/null 2>&1
chk "uninstall removes ours" "$([ -e "$H/.codex/hooks.json" ] && echo yes || echo no)" "no"

echo "== 26. uninstall does not take a file of theirs out of our directory =="
# ~/.claude/skills is ours only in the sense that we created it. Anything the
# user puts in it afterwards is theirs, and removing our links must not take
# their file with them, nor rmdir a directory that still holds it.
H="$S/h26"; mkdir -p "$H/.claude" "$H/.codex"
HOME="$H" bash "$S/repo/install.sh" full >/dev/null 2>&1; chk "installed" "$?" "0"
echo "made while installed" > "$H/.claude/skills/mine-new.md"
mkdir -p "$H/.claude/skills/my-own"; echo "mine" > "$H/.claude/skills/my-own/SKILL.md"
HOME="$H" bash "$S/repo/uninstall.sh" >/dev/null 2>&1; chk "uninstall exit 0" "$?" "0"
chk "our links are gone" "$([ -L "$H/.claude/skills/ship" ] && echo yes || echo no)" "no"
chk "their loose file survives" "$(cat "$H/.claude/skills/mine-new.md" 2>/dev/null)" "made while installed"
chk "their own skill survives" "$(cat "$H/.claude/skills/my-own/SKILL.md" 2>/dev/null)" "mine"
chk "the directory was not removed" "$([ -d "$H/.claude/skills" ] && echo yes || echo no)" "yes"

echo "== 27. the optional baseline links only supported host paths =="
H="$S/h27"; mkdir -p "$H/.codex"
HOME="$H" bash "$S/repo/install.sh" workflow --baseline >/dev/null 2>&1
chk "home AGENTS.md is not duplicated" "$([ -e "$H/AGENTS.md" ] && echo yes || echo no)" "no"
chk "Codex AGENTS.md is linked" "$(readlink "$H/.codex/AGENTS.md")" "$S/repo/AGENTS.md"
chk "Claude CLAUDE.md is linked" "$(readlink "$H/.claude/CLAUDE.md")" "$S/repo/AGENTS.md"
HOME="$H" bash "$S/repo/uninstall.sh" workflow >/dev/null 2>&1
chk "all three gone after uninstall" \
  "$([ -e "$H/AGENTS.md" ] || [ -e "$H/.codex/AGENTS.md" ] || [ -e "$H/.claude/CLAUDE.md" ] && echo some || echo none)" "none"

echo "== 28. Codex hook merging is idempotent =="
# Re-running install must replace our own definitions rather than duplicate
# them. User-owned definitions are covered by test 18's full round trip.
H="$S/h28"; mkdir -p "$H/.codex"
HOME="$H" bash "$S/repo/install.sh" full >/dev/null 2>&1
chk "first install writes ours" "$(grep -cF -- 'guard-codex.py' "$H/.codex/hooks.json")" "1"
HOME="$H" bash "$S/repo/install.sh" full >/dev/null 2>&1
chk "re-install is fine on our own file" "$?" "0"
chk "still exactly one of ours" "$(grep -cF -- 'guard-codex.py' "$H/.codex/hooks.json")" "1"

echo "== 29. an unchanged hooks.json is not re-backed-up =="
H="$S/h29"; mkdir -p "$H/.codex"
HOME="$H" bash "$S/repo/install.sh" full >/dev/null 2>&1
HOME="$H" bash "$S/repo/install.sh" full >/dev/null 2>&1
HOME="$H" bash "$S/repo/install.sh" full >/dev/null 2>&1
chk "no backups of a file we wrote" "$(ls "$H"/.codex/hooks.json.bak-* 2>/dev/null | wc -l | tr -d ' ')" "0"
chk "no temp file left behind" "$(ls "$H"/.codex/hooks.json.tmp-* 2>/dev/null | wc -l | tr -d ' ')" "0"

echo "== 30. --check does not accept a hook that only MENTIONS our path =="
# A naive substring test called this wired and reported "all good" on a HOME
# with no guardrails running at all.
H="$S/h30"; mkdir -p "$H/.claude"
cat > "$H/.claude/settings.json" <<'EOF'
{"hooks":{"PreToolUse":[{"matcher":"Bash","hooks":[{"type":"command","command":"# TODO wire guard-bash.py someday"}]}]}}
EOF
HOME="$H" bash "$S/repo/install.sh" full --check >/dev/null 2>&1
chk "check exits nonzero" "$([ $? -ne 0 ] && echo yes || echo no)" "yes"
out=$(HOME="$H" bash "$S/repo/install.sh" full --check 2>&1)
chk "and says the hooks are missing" "$(grep -c 'guard hooks missing or not wired' <<<"$out")" "1"

echo "== 31. --check notices a deleted matcher, hook script, or codex hooks.json =="
H="$S/h31"; mkdir -p "$H/.codex"
HOME="$H" bash "$S/repo/install.sh" full >/dev/null 2>&1
HOME="$H" bash "$S/repo/install.sh" full --check >/dev/null 2>&1
chk "a clean install checks out" "$?" "0"
python3 - "$H/.claude/settings.json" <<'EOF'
import json, sys
p = sys.argv[1]
c = json.load(open(p))
c["hooks"]["PreToolUse"] = [e for e in c["hooks"]["PreToolUse"]
                            if "guard-files" not in json.dumps(e)]
json.dump(c, open(p, "w"), indent=2)
EOF
HOME="$H" bash "$S/repo/install.sh" full --check >/dev/null 2>&1
chk "a missing file matcher is caught" "$([ $? -ne 0 ] && echo yes || echo no)" "yes"
HOME="$H" bash "$S/repo/install.sh" full >/dev/null 2>&1
rm -f "$H/.codex/hooks.json"
HOME="$H" bash "$S/repo/install.sh" full --check >/dev/null 2>&1
chk "a missing codex hooks.json is caught" "$([ $? -ne 0 ] && echo yes || echo no)" "yes"

echo "== 32. CLAUDE.md is not linked while the hooks are unwired =="
# AGENTS.md tells the agent the guardrails are enforced. If the settings merge
# aborts, a CLAUDE.md asserting protection that does not exist is worse than none.
H="$S/h32"; mkdir -p "$H/.claude"
printf '{"model":"opus",}\n' > "$H/.claude/settings.json"   # malformed: aborts
HOME="$H" bash "$S/repo/install.sh" full --baseline >/dev/null 2>&1
chk "no CLAUDE.md promising guardrails" "$([ -e "$H/.claude/CLAUDE.md" ] && echo yes || echo no)" "no"

echo "== 33. a tab in the repo path remains valid JSON and shell =="
mkdir -p "$S/ta	b"; cp -R "$S/repo" "$S/ta	b/repo"
H="$S/h33"; mkdir -p "$H/.codex"
HOME="$H" bash "$S/ta	b/repo/install.sh" full >/dev/null 2>&1
chk "installs" "$?" "0"
cmd=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["hooks"]["PreToolUse"][0]["hooks"][0]["command"])' "$H/.codex/hooks.json")
chk "hook command parses" "$(bash -n -c "$cmd"; echo $?)" "0"

echo "== 34. a settings.json that is a directory aborts before mutating =="
H="$S/h34"; mkdir -p "$H/.claude/settings.json"
HOME="$H" bash "$S/repo/install.sh" full --baseline >/dev/null 2>&1
chk "exits nonzero" "$([ $? -ne 0 ] && echo yes || echo no)" "yes"
chk "nothing installed" "$([ -e "$H/.claude/skills/ship" ] && echo yes || echo no)" "no"

echo "== 35. CLAUDE_CONFIG_DIR and CODEX_HOME are refused, not silently ignored =="
# Claude Code reads CLAUDE_CONFIG_DIR. Installing into ~/.claude anyway reports
# a clean "Done" and wires nothing the agent will ever read.
H="$S/h35"; mkdir -p "$H"
CLAUDE_CONFIG_DIR="$H/cfg" HOME="$H" bash "$S/repo/install.sh" full >/dev/null 2>&1
chk "CLAUDE_CONFIG_DIR aborts" "$([ $? -ne 0 ] && echo yes || echo no)" "yes"
chk "nothing installed" "$([ -e "$H/.claude/skills" ] && echo yes || echo no)" "no"
CODEX_HOME="$H/cdx" HOME="$H" bash "$S/repo/install.sh" full >/dev/null 2>&1
chk "CODEX_HOME aborts" "$([ $? -ne 0 ] && echo yes || echo no)" "yes"

echo "== 36. install.sh works when invoked through a symlink =="
H="$S/h36"; mkdir -p "$H/bin"
ln -s "$S/repo/install.sh" "$H/bin/agent-install"
HOME="$H" bash "$H/bin/agent-install" full >/dev/null 2>&1
chk "exit 0" "$?" "0"
chk "skills linked" "$([ -L "$H/.claude/skills/ship" ] && echo yes || echo no)" "yes"

echo "== 37. uninstall through a symlink removes everything =="
# install.sh got symlink resolution and uninstall.sh did not, so uninstalling
# through a wrapper stripped the settings.json hooks (which do not use $REPO)
# and left every symlink and our CLAUDE.md in place, reporting success.
H="$S/h37"; mkdir -p "$H/bin" "$H/.claude" "$H/.codex"
echo "my personal instructions" > "$H/.claude/CLAUDE.md"
ln -s "$S/repo/uninstall.sh" "$H/bin/agent-uninstall"
HOME="$H" bash "$S/repo/install.sh" full >/dev/null 2>&1
HOME="$H" bash "$H/bin/agent-uninstall" >/dev/null 2>&1; chk "exit 0" "$?" "0"
# -path prune: the wrapper in $H/bin is the test's own, not the installer's.
chk "no symlinks into the repo remain" \
  "$(find "$H" -path "$H/bin" -prune -o -type l -print0 2>/dev/null \
     | while IFS= read -r -d '' link; do readlink "$link" 2>/dev/null || true; done \
     | grep -c "$S/repo" || true)" "0"
chk "their CLAUDE.md restored" "$(cat "$H/.claude/CLAUDE.md" 2>/dev/null)" "my personal instructions"
chk "codex hooks.json removed" "$([ -e "$H/.codex/hooks.json" ] && echo yes || echo no)" "no"

echo "== 38. a dotfile-managed ~/.codex/skills is refused, not written into =="
H="$S/h38"; mkdir -p "$H/.codex" "$H/dots/codexskills/theirs"
echo "theirs" > "$H/dots/codexskills/theirs/SKILL.md"
ln -s "$H/dots/codexskills" "$H/.codex/skills"
HOME="$H" bash "$S/repo/install.sh" full >/dev/null 2>&1; chk "refused" "$?" "1"
chk "their stow tree is untouched" "$(ls "$H/dots/codexskills" | tr -d ' \n')" "theirs"
chk "no links dropped into it" "$(find "$H/dots/codexskills" -type l | wc -l | tr -d ' ')" "0"
chk "their symlink is intact" "$(readlink "$H/.codex/skills")" "$H/dots/codexskills"

echo "== 39. a hooks.json or skills path of the wrong type aborts before mutating =="
# `mv` into a DIRECTORY named hooks.json succeeded, reported success, and left
# Codex with no guardrails plus a leftover temp file.
H="$S/h39"; mkdir -p "$H/.codex/hooks.json"
HOME="$H" bash "$S/repo/install.sh" full >/dev/null 2>&1
chk "exits nonzero" "$([ $? -ne 0 ] && echo yes || echo no)" "yes"
chk "nothing installed" "$([ -e "$H/.claude/skills/ship" ] && echo yes || echo no)" "no"
chk "no temp file left behind" "$(ls "$H"/.codex/hooks.json/*.tmp-* 2>/dev/null | wc -l | tr -d ' ')" "0"
H="$S/h39b"; mkdir -p "$H/.codex"; : > "$H/.codex/skills"
HOME="$H" bash "$S/repo/install.sh" full >/dev/null 2>&1
chk "a skills FILE aborts too" "$([ $? -ne 0 ] && echo yes || echo no)" "yes"
chk "nothing installed" "$([ -e "$H/.claude/skills/ship" ] && echo yes || echo no)" "no"

echo "== 40. --check verifies where links POINT, not just that they exist =="
# Repointing a guard hook at a no-op script used to report "all good".
H="$S/h40a"; mkdir -p "$H/.codex"
HOME="$H" bash "$S/repo/install.sh" full --baseline >/dev/null 2>&1
printf '#!/usr/bin/env python3\nimport sys\nsys.exit(0)\n' > "$S/noop.py"
ln -sfn "$S/noop.py" "$H/.claude/hooks/guard-bash.py"
HOME="$H" bash "$S/repo/install.sh" full --check --baseline >/dev/null 2>&1
chk "a repointed hook is caught" "$([ $? -ne 0 ] && echo yes || echo no)" "yes"
H="$S/h40b"; mkdir -p "$H/.codex"
HOME="$H" bash "$S/repo/install.sh" full --baseline >/dev/null 2>&1
ln -sfn "$S/noop.py" "$H/.claude/skills/ship"
HOME="$H" bash "$S/repo/install.sh" full --check --baseline >/dev/null 2>&1
chk "a repointed skill is caught" "$([ $? -ne 0 ] && echo yes || echo no)" "yes"
H="$S/h40c"; mkdir -p "$H/.codex"
HOME="$H" bash "$S/repo/install.sh" full --baseline >/dev/null 2>&1
rm -f "$H/.claude/CLAUDE.md"
HOME="$H" bash "$S/repo/install.sh" full --check --baseline >/dev/null 2>&1
chk "a missing CLAUDE.md is caught" "$([ $? -ne 0 ] && echo yes || echo no)" "yes"

echo "== 41. --check rejects a codex hooks.json that only MENTIONS our path =="
H="$S/h41"; mkdir -p "$H/.codex"
HOME="$H" bash "$S/repo/install.sh" full >/dev/null 2>&1
cat > "$H/.codex/hooks.json" <<EOF
{"description":"TODO: someday wire $S/repo/hooks/guard-codex.py","hooks":{}}
EOF
HOME="$H" bash "$S/repo/install.sh" full --check >/dev/null 2>&1
chk "exits nonzero" "$([ $? -ne 0 ] && echo yes || echo no)" "yes"
out=$(HOME="$H" bash "$S/repo/install.sh" full --check 2>&1)
chk "and says why" "$(grep -c 'missing the agent-config guard' <<<"$out")" "1"

echo "== 42. --check routes hook trust through Codex's supported UI =="
H="$S/h42"; mkdir -p "$H/.codex"
HOME="$H" bash "$S/repo/install.sh" full >/dev/null 2>&1
out=$(HOME="$H" bash "$S/repo/install.sh" full --check 2>&1)
chk "says where trust is reviewed" "$(grep -c 'inspect it with /hooks' <<<"$out")" "1"
chk "but does not fail the check" "$(grep -c 'all good' <<<"$out")" "1"
printf '[hooks]\npre_tool_use = "hooks.json:pre_tool_use"\n' > "$H/.codex/config.toml"
out=$(HOME="$H" bash "$S/repo/install.sh" full --check 2>&1)
chk "does not infer trust from private config" "$(grep -c 'inspect it with /hooks' <<<"$out")" "1"

echo "== 43. only --check is accepted =="
# `./install.sh --dry-run` used to perform a real install.
for a in --dry-run check -n; do
  H="$S/h43-$RANDOM"; mkdir -p "$H"
  HOME="$H" bash "$S/repo/install.sh" full "$a" >/dev/null 2>&1
  chk "'$a' exits nonzero" "$([ $? -ne 0 ] && echo yes || echo no)" "yes"
  chk "'$a' installs nothing" "$([ -e "$H/.claude/skills" ] && echo yes || echo no)" "no"
done

echo "== 44. CLAUDE_CONFIG_DIR pointing at the default is NOT refused =="
# A raw string compare refused a trailing slash and a symlink to the same place.
H="$S/h44"; mkdir -p "$H/.claude"
CLAUDE_CONFIG_DIR="$H/.claude/" HOME="$H" bash "$S/repo/install.sh" full >/dev/null 2>&1
chk "a trailing slash is fine" "$?" "0"
H="$S/h45"; mkdir -p "$H/real"; ln -s "$H/real" "$H/.claude"
CLAUDE_CONFIG_DIR="$H/real" HOME="$H" bash "$S/repo/install.sh" full >/dev/null 2>&1
chk "a symlink to the same place is fine" "$?" "0"

echo "== 47. --check rejects a settings.json where BOTH matchers only mention us =="
# Test 30's fixture had one mentioning matcher, so the set-equality rejected it
# either way and the regex it claims to test was never exercised.
H="$S/h47"; mkdir -p "$H/.claude"
cat > "$H/.claude/settings.json" <<'EOF'
{"hooks":{"PreToolUse":[
 {"matcher":"Bash","hooks":[{"type":"command","command":"# TODO wire guard-bash.py someday"}]},
 {"matcher":"Read|Edit|Write","hooks":[{"type":"command","command":"# TODO wire guard-files.py someday"}]}]}}
EOF
out=$(HOME="$H" bash "$S/repo/install.sh" full --check 2>&1)
chk "not accepted as wired" "$(grep -c 'guard hooks missing or not wired' <<<"$out")" "1"

echo "== 48. a dangling skill link does not abort the install =="
# Under `set -euo pipefail` a `grep -ix` that matched nothing killed the script
# with NO message. It fires on exactly what a moved or deleted clone leaves.
# A dangling link points at nothing, so replacing it loses nothing: refusing
# would leave a machine that re-running install could never repair.
H="$S/h48"; mkdir -p "$H/.claude/skills" "$H/.codex"
ln -s "$S/gone/skills/ship" "$H/.claude/skills/ship"
HOME="$H" bash "$S/repo/install.sh" full --baseline >/dev/null 2>&1; chk "exit 0" "$?" "0"
chk "ship relinked to this repo" "$(readlink "$H/.claude/skills/ship")" "$S/repo/skills/ship/"
chk "later skills still linked" "$([ -L "$H/.claude/skills/unstick" ] && echo yes || echo no)" "yes"
chk "settings.json still written" "$(grep -c guard-bash "$H/.claude/settings.json")" "1"
chk "CLAUDE.md still linked" "$([ -L "$H/.claude/CLAUDE.md" ] && echo yes || echo no)" "yes"
# ...but a real FILE of theirs where a skill link belongs is refused.
H="$S/h48b"; mkdir -p "$H/.claude/skills"; echo x > "$H/.claude/skills/review"
HOME="$H" bash "$S/repo/install.sh" full >/dev/null 2>&1; chk "a plain file is refused" "$?" "1"
chk "and it still says x" "$(cat "$H/.claude/skills/review")" "x"

echo "== 49. relocating the repo does not manufacture dangling symlinks =="
# install; move the clone; reinstall. Our own previous links used to be read as
# a dotfile manager's, recorded as .baklink- files pointing at the old path,
# and then faithfully restored by uninstall as 21 dangling links.
H="$S/h49"; mkdir -p "$H/.codex"
mkdir -p "$S/loc1"; cp -R "$S/repo" "$S/loc1/repo"
HOME="$H" bash "$S/loc1/repo/install.sh" full >/dev/null 2>&1
mkdir -p "$S/loc2"; mv "$S/loc1/repo" "$S/loc2/repo"
HOME="$H" bash "$S/loc2/repo/install.sh" full >/dev/null 2>&1; chk "reinstall exit 0" "$?" "0"
chk "no baklink records of our own" "$(ls "$H"/.claude/skills/*.baklink-* "$H"/.claude/*.baklink-* 2>/dev/null | wc -l | tr -d ' ')" "0"
HOME="$H" bash "$S/loc2/repo/uninstall.sh" >/dev/null 2>&1; chk "uninstall exit 0" "$?" "0"
dangling=0
while IFS= read -r l; do [ -e "$l" ] || dangling=$((dangling+1)); done < <(find "$H" -type l 2>/dev/null)
chk "no dangling symlinks left behind" "$dangling" "0"

echo "== 49b. uninstalling after moving the clone still removes everything =="
# Install from one path, move the clone, uninstall from the new path WITHOUT
# reinstalling. Every link still points at the old location, so a $REPO-prefix
# test recognises none of them and uninstall leaves the whole install in place
# while reporting success. Only the recorded origins make this work.
# Their own CLAUDE.md is parked under a name we never claim: this section is
# about the recorded origins surviving a move, not about the refusal.
H="$S/h49b"; mkdir -p "$H/.claude" "$H/.codex"
echo "my instructions" > "$H/.claude/CLAUDE.md.mine"
mkdir -p "$S/from1"; cp -R "$S/repo" "$S/from1/repo"
HOME="$H" bash "$S/from1/repo/install.sh" full >/dev/null 2>&1
mkdir -p "$S/from2"; mv "$S/from1/repo" "$S/from2/repo"
HOME="$H" bash "$S/from2/repo/uninstall.sh" >/dev/null 2>&1; chk "exit 0" "$?" "0"
chk "top-level links removed" \
  "$([ -L "$H/AGENTS.md" ] || [ -L "$H/.codex/AGENTS.md" ] && echo some || echo none)" "none"
chk "our CLAUDE.md link removed" "$([ -L "$H/.claude/CLAUDE.md" ] && echo yes || echo no)" "no"
chk "theirs was never touched" "$(cat "$H/.claude/CLAUDE.md.mine" 2>/dev/null)" "my instructions"
chk "skill links removed" "$([ -L "$H/.claude/skills/ship" ] && echo yes || echo no)" "no"
chk "guard hooks stripped" "$(grep -c guard-bash "$H/.claude/settings.json" 2>/dev/null | head -1)" "0"

echo "== 50. --check fails when a baseline link points somewhere else =="
# link()'s check-mode branches used warn, which does not increment PROBLEMS, so
# --check said "all good" while both AGENTS.md links pointed at a decoy.
H="$S/h50a"; mkdir -p "$H/.codex"
HOME="$H" bash "$S/repo/install.sh" workflow --baseline >/dev/null 2>&1
echo "decoy" > "$S/decoy.md"
ln -sfn "$S/decoy.md" "$H/.claude/CLAUDE.md"
HOME="$H" bash "$S/repo/install.sh" workflow --check --baseline >/dev/null 2>&1
chk "a repointed Claude baseline is caught" "$([ $? -ne 0 ] && echo yes || echo no)" "yes"
H="$S/h50b"; mkdir -p "$H/.codex"
HOME="$H" bash "$S/repo/install.sh" workflow --baseline >/dev/null 2>&1
ln -sfn "$S/decoy.md" "$H/.codex/AGENTS.md"
HOME="$H" bash "$S/repo/install.sh" workflow --check --baseline >/dev/null 2>&1
chk "a repointed codex AGENTS.md is caught" "$([ $? -ne 0 ] && echo yes || echo no)" "yes"

echo "== 51. a link to a skill the repo no longer ships is pruned =="
# Both link loops iterate what EXISTS in the repo, so a removed or renamed
# skill left a dangling link that both agents still scan, and --check passed.
H="$S/h51"; mkdir -p "$H/.codex"
HOME="$H" bash "$S/repo/install.sh" full >/dev/null 2>&1
ln -s "$S/repo/skills/retired-skill" "$H/.claude/skills/retired-skill"
ln -s "$S/repo/skills/retired-skill" "$H/.codex/skills/retired-skill"
HOME="$H" bash "$S/repo/install.sh" full --check >/dev/null 2>&1
chk "--check reports it" "$([ $? -ne 0 ] && echo yes || echo no)" "yes"
HOME="$H" bash "$S/repo/install.sh" full >/dev/null 2>&1
chk "install prunes it (claude)" "$([ -L "$H/.claude/skills/retired-skill" ] && echo yes || echo no)" "no"
chk "install prunes it (codex)" "$([ -L "$H/.codex/skills/retired-skill" ] && echo yes || echo no)" "no"
chk "and leaves real skills alone" "$([ -L "$H/.claude/skills/ship" ] && echo yes || echo no)" "yes"

echo "== 52. a timing budget must not abort the install =="
# The suite's wall-clock assertions gated the install, so a loaded machine
# aborted with "guard regression suite fails in this checkout" and the
# suggested command then printed PASS. --no-perf is what install.sh runs.
out=$(python3 "$S/repo/hooks/tests.py.installer-full" --no-perf 2>&1)
chk "correctness-only mode passes" "$(grep -c '^PASS' <<<"$out")" "1"
chk "and reports no timing lines" "$(grep -c 'budget' <<<"$out")" "0"
chk "install.sh uses it" "$(grep -c 'tests.py" --no-perf' "$S/repo/install.sh")" "1"

echo "== 53. a HOME with a space round-trips =="
# Seven unquoted "$var" sites survived mutation because no fixture ever used
# one. Exercises the refusal path too, which prints paths of its own.
H="$S/home with space"; mkdir -p "$H/.codex" "$H/.claude"
echo "my instructions" > "$H/.claude/CLAUDE.md"
out="$(HOME="$H" bash "$S/repo/install.sh" full --baseline 2>&1)"; chk "refused" "$?" "1"
chk "the spaced path is shell-escaped" "$(grep -c 'home\\ with\\ space/.claude/CLAUDE.md' <<<"$out")" "1"
chk "their file untouched" "$(cat "$H/.claude/CLAUDE.md")" "my instructions"
move_command="$(sed -n 's/^    \(mv .*CLAUDE\.md\.mine\)$/\1/p' <<<"$out")"
eval "$move_command"
chk "the printed remediation command works" "$([ -f "$H/.claude/CLAUDE.md.mine" ] && echo yes || echo no)" "yes"
HOME="$H" bash "$S/repo/install.sh" full --baseline >/dev/null 2>&1; chk "install exit 0" "$?" "0"
chk "skills linked" "$([ -L "$H/.claude/skills/ship" ] && echo yes || echo no)" "yes"
HOME="$H" bash "$S/repo/uninstall.sh" >/dev/null 2>&1; chk "uninstall exit 0" "$?" "0"
chk "their file still theirs" "$(cat "$H/.claude/CLAUDE.md.mine" 2>/dev/null)" "my instructions"

echo "== 54. a user path that merely shares a prefix with the clone is NOT ours =="
# `$t == "$REPO"*` had no path boundary, so a stow file at `.../repo-dots/x`
# next to a clone at `.../repo` was treated as ours. Under refuse-first the
# consequence is different but the test is the same: theirs must survive.
mkdir -p "$S/pfx"; cp -R "$S/repo" "$S/pfx/repo"
mkdir -p "$S/pfx/repo-dots/skills/mine"
echo "their instructions" > "$S/pfx/repo-dots/CLAUDE.md"
echo "their skill" > "$S/pfx/repo-dots/skills/mine/SKILL.md"
H="$S/h54"; mkdir -p "$H/.claude/skills" "$H/.codex"
ln -s "$S/pfx/repo-dots/CLAUDE.md" "$H/.claude/CLAUDE.md"
ln -s "$S/pfx/repo-dots/skills/mine" "$H/.claude/skills/mine"
HOME="$H" bash "$S/pfx/repo/install.sh" full --baseline >/dev/null 2>&1; chk "refused" "$?" "1"
chk "their CLAUDE.md survives" "$(cat "$H/.claude/CLAUDE.md" 2>/dev/null)" "their instructions"
chk "their skill link survives" "$(readlink "$H/.claude/skills/mine")" "$S/pfx/repo-dots/skills/mine"
chk "their skill still loads" "$(cat "$H/.claude/skills/mine/SKILL.md" 2>/dev/null)" "their skill"

echo "== 55. ...and the same via a recorded ORIGIN prefix =="
# Install from `.../ac`, move the clone, and a user path at `.../acme-skills`
# prefix-matched the recorded origin `.../ac`.
mkdir -p "$S/o1/ac"; cp -R "$S/repo/." "$S/o1/ac/"
mkdir -p "$S/o1/acme-skills/mine"; echo "theirs" > "$S/o1/acme-skills/mine/SKILL.md"
H="$S/h55"; mkdir -p "$H/.claude/skills" "$H/.codex"
HOME="$H" bash "$S/o1/ac/install.sh" full >/dev/null 2>&1
ln -s "$S/o1/acme-skills/mine" "$H/.claude/skills/mine"
mkdir -p "$S/o2"; mv "$S/o1/ac" "$S/o2/ac"
HOME="$H" bash "$S/o2/ac/uninstall.sh" >/dev/null 2>&1
chk "their skill link survives the origin match" "$(readlink "$H/.claude/skills/mine")" "$S/o1/acme-skills/mine"
chk "and still loads" "$(cat "$H/.claude/skills/mine/SKILL.md" 2>/dev/null)" "theirs"

echo "== 56. an ORIGINS file with no trailing newline is still read =="
H="$S/h56"; mkdir -p "$H/.codex"
mkdir -p "$S/n1"; cp -R "$S/repo" "$S/n1/repo"
HOME="$H" bash "$S/n1/repo/install.sh" full >/dev/null 2>&1
printf '%s' "$S/n1/repo" > "$H/.claude/.agent-config-origins"   # no newline
mkdir -p "$S/n2"; mv "$S/n1/repo" "$S/n2/repo"
HOME="$H" bash "$S/n2/repo/uninstall.sh" >/dev/null 2>&1
left=0
while IFS= read -r l; do [ -e "$l" ] || left=$((left+1)); done < <(find "$H" -type l 2>/dev/null)
chk "no dangling links left" "$left" "0"

echo "== 57. an aborted install does not record an origin =="
# ORIGINS used to be written during preflight, so an install that aborted at a
# later gate still widened _is_our_target permanently.
H="$S/h57"; mkdir -p "$H/.claude"
printf '{"model":"opus",}\n' > "$H/.claude/settings.json"    # malformed: aborts
HOME="$H" bash "$S/repo/install.sh" full >/dev/null 2>&1
chk "exits nonzero" "$([ $? -ne 0 ] && echo yes || echo no)" "yes"
chk "no origins file written" "$([ -e "$H/.claude/.agent-config-origins" ] && echo yes || echo no)" "no"
# ...and --check must not write it either: it is documented as changing nothing,
# and a recorded origin permanently widens what uninstall will delete.
# ~/.claude must EXIST, or removing the guard fails for want of a parent
# directory and this passes for the wrong reason.
H="$S/h57b"; mkdir -p "$H/.claude"
HOME="$H" bash "$S/repo/install.sh" full --check >/dev/null 2>&1
chk "--check writes no origins file" "$([ -e "$H/.claude/.agent-config-origins" ] && echo yes || echo no)" "no"
H="$S/h57c"; mkdir -p "$H"
HOME="$H" bash "$S/repo/install.sh" full --check >/dev/null 2>&1
chk "--check creates no ~/.claude at all" "$([ -e "$H/.claude" ] && echo yes || echo no)" "no"

echo "== 58. prune_stale finds a link left by a PREVIOUS location =="
# It matched the raw $REPO prefix, so it missed exactly the relocation case
# the origins file exists for.
H="$S/h58"; mkdir -p "$H/.codex"
mkdir -p "$S/p1"; cp -R "$S/repo" "$S/p1/repo"
HOME="$H" bash "$S/p1/repo/install.sh" full >/dev/null 2>&1
ln -s "$S/p1/repo/skills/retired" "$H/.claude/skills/retired"
mkdir -p "$S/p2"; mv "$S/p1/repo" "$S/p2/repo"
HOME="$H" bash "$S/p2/repo/install.sh" full --check >/dev/null 2>&1
chk "--check reports the stale link" "$([ $? -ne 0 ] && echo yes || echo no)" "yes"
HOME="$H" bash "$S/p2/repo/install.sh" full >/dev/null 2>&1
chk "install prunes it" "$([ -L "$H/.claude/skills/retired" ] && echo yes || echo no)" "no"

echo "== 59. skills are self-contained and survive archive installs =="
# Two skills used to be symlinks into vendor/, which made a ZIP download
# silently install a partial suite and forced an Apache-2.0 redistribution
# obligation onto this repo. Both are gone: companions are recommended, not
# shipped. These assertions stop either coming back by accident.
chk "no vendor tree" "$([ -e "$S/repo/vendor" ] && echo yes || echo no)" "no"
chk "every skill is a real directory" \
  "$(find "$S/repo/skills" -maxdepth 1 -mindepth 1 -type l | wc -l | tr -d ' ')" "0"
chk "no third-party licence files" \
  "$(find "$S/repo" -maxdepth 1 -type f \
     \( -name 'LICENSE-ehmo*' -o -name 'LICENSE-modern-screenshot*' \) -print \
     | wc -l | tr -d ' ')" "0"

echo "== 61. an ORIGINS file with no trailing newline survives a re-install =="
# Round 16 fixed the READ side and left the WRITE: appending to an unterminated
# line concatenated the two paths into one bogus origin, destroying the older
# one, after which uninstall restored every link as dangling and reported success.
H="$S/h61"; mkdir -p "$H/.codex"
mkdir -p "$S/w1"; cp -R "$S/repo" "$S/w1/repo"
HOME="$H" bash "$S/w1/repo/install.sh" full >/dev/null 2>&1
printf '%s' "$S/w1/repo" > "$H/.claude/.agent-config-origins"    # strip the newline
mkdir -p "$S/w2"; mv "$S/w1/repo" "$S/w2/repo"
HOME="$H" bash "$S/w2/repo/install.sh" full >/dev/null 2>&1
chk "the old origin survives" "$(grep -cxF -- "$S/w1/repo" "$H/.claude/.agent-config-origins")" "1"
chk "no baklink records of our own" \
  "$(find "$H/.claude/skills" -maxdepth 1 -mindepth 1 -name '*baklink-*' -print \
     2>/dev/null | wc -l | tr -d ' ')" "0"
HOME="$H" bash "$S/w2/repo/uninstall.sh" >/dev/null 2>&1
left=0
while IFS= read -r l; do [ -e "$l" ] || left=$((left+1)); done < <(find "$H" -type l 2>/dev/null)
chk "no dangling links after uninstall" "$left" "0"

echo "== 62. a clone at a dotfiles root does not claim the user's own tree =="
# The boundary fix said "anything under the clone is ours". If the repo is
# cloned at a dotfiles root that also holds the user's stow tree, that claimed
# their links: no backup recorded, and uninstall deleted them.
mkdir -p "$S/dots"; cp -R "$S/repo" "$S/dots/repo"
mkdir -p "$S/dots/repo/claude/skills/mine"; echo "theirs" > "$S/dots/repo/claude/skills/mine/SKILL.md"
H="$S/h62"; mkdir -p "$H/.claude/skills" "$H/.codex"
ln -s "$S/dots/repo/claude/skills/mine" "$H/.claude/skills/mine"
HOME="$H" bash "$S/dots/repo/install.sh" full >/dev/null 2>&1
HOME="$H" bash "$S/dots/repo/uninstall.sh" >/dev/null 2>&1
chk "their link survives" "$(readlink "$H/.claude/skills/mine")" "$S/dots/repo/claude/skills/mine"
chk "and still loads" "$(cat "$H/.claude/skills/mine/SKILL.md" 2>/dev/null)" "theirs"

echo "== 63. a fork may add its own files under skills/ =="
# The ZIP preflight refused ANY regular file there and told the adopter their
# symlinks were broken. The README invites a fork to add skills.
mkdir -p "$S/fork"; cp -R "$S/repo" "$S/fork/repo"
echo "notes" > "$S/fork/repo/skills/NOTES.md"
H="$S/h63"; mkdir -p "$H"
HOME="$H" bash "$S/fork/repo/install.sh" full >/dev/null 2>&1; chk "exit 0" "$?" "0"
chk "skills still linked" "$([ -L "$H/.claude/skills/ship" ] && echo yes || echo no)" "yes"
# ...and an empty skills directory is still refused, which is the remaining
# way a truncated checkout can present itself.
mkdir -p "$S/empty"; cp -R "$S/repo" "$S/empty/repo"; rm -rf "$S/empty/repo/skills"
mkdir -p "$S/empty/repo/skills"
H="$S/h63b"; mkdir -p "$H"
out=$(HOME="$H" bash "$S/empty/repo/install.sh" workflow 2>&1); rc=$?
chk "an empty skills dir aborts" "$([ $rc -ne 0 ] && echo yes || echo no)" "yes"
chk "and says which required skill is missing" "$([ "$(grep -c 'missing workflow skill' <<<"$out")" -ge 1 ] && echo 1 || echo 0)" "1"

echo "== 64. a stale link in ~/.claude/hooks is pruned too =="
# prune_stale was skills-only, so a guard script renamed across a pull left a
# dangling link that survived a repair install and --check reported all good.
H="$S/h64"; mkdir -p "$H/.codex"
HOME="$H" bash "$S/repo/install.sh" full >/dev/null 2>&1
ln -s "$S/repo/hooks/guard-retired.py" "$H/.claude/hooks/guard-retired.py"
HOME="$H" bash "$S/repo/install.sh" full --check >/dev/null 2>&1
chk "--check reports it" "$([ $? -ne 0 ] && echo yes || echo no)" "yes"
HOME="$H" bash "$S/repo/install.sh" full >/dev/null 2>&1
chk "install prunes it" "$([ -L "$H/.claude/hooks/guard-retired.py" ] && echo yes || echo no)" "no"
chk "real hooks untouched" "$([ -L "$H/.claude/hooks/guard-bash.py" ] && echo yes || echo no)" "yes"

echo "== 65. workflow and operator skills are separate products =="
chk "thirteen workflow skills ship" \
  "$(find "$S/repo/skills" -mindepth 2 -maxdepth 2 -name SKILL.md | wc -l | tr -d ' ')" "13"
chk "three optional operator skills ship" \
  "$(find "$S/repo/operator-skills" -mindepth 2 -maxdepth 2 -name SKILL.md | wc -l | tr -d ' ')" "3"
for optional in handoff research wizard; do
  chk "$optional is not in workflow" \
    "$([ -e "$S/repo/skills/$optional/SKILL.md" ] && echo yes || echo no)" "no"
  chk "$optional is in operator" \
    "$([ -e "$S/repo/operator-skills/$optional/SKILL.md" ] && echo yes || echo no)" "yes"
done
for retired in teach which; do
  chk "$retired is not shipped" \
    "$([ -e "$S/repo/skills/$retired/SKILL.md" ] || [ -e "$S/repo/operator-skills/$retired/SKILL.md" ] && echo yes || echo no)" "no"
done

echo "== 66. guard and workflow are independently installable =="
H="$S/h66g"; mkdir -p "$H/.codex"
HOME="$H" bash "$S/repo/install.sh" guard >/dev/null 2>&1
chk "guard installs Claude hooks" "$([ -L "$H/.claude/hooks/guard-bash.py" ] && echo yes || echo no)" "yes"
chk "guard installs no skills" "$(find "$H" -path '*/skills/*' -type l | wc -l | tr -d ' ')" "0"
chk "guard installs no global instructions" "$([ -e "$H/AGENTS.md" ] && echo yes || echo no)" "no"
H="$S/h66w"; mkdir -p "$H/.codex"
HOME="$H" bash "$S/repo/install.sh" workflow >/dev/null 2>&1
chk "workflow installs skills" "$([ -L "$H/.claude/skills/ship" ] && echo yes || echo no)" "yes"
chk "workflow excludes operator skills" "$([ -e "$H/.claude/skills/wizard" ] && echo yes || echo no)" "no"
chk "workflow excludes output styles" "$([ -e "$H/.claude/output-styles/terse.md" ] && echo yes || echo no)" "no"
chk "workflow links Claude orchestration by default" "$(readlink "$H/.claude/CLAUDE.md")" "$S/repo/AGENTS.md"
chk "workflow links Codex orchestration by default" "$(readlink "$H/.codex/AGENTS.md")" "$S/repo/AGENTS.md"
chk "both hosts share one instruction source" \
  "$([ "$(readlink "$H/.claude/CLAUDE.md")" = "$(readlink "$H/.codex/AGENTS.md")" ] && echo yes || echo no)" "yes"
chk "workflow installs project initializer" "$(readlink "$H/.local/bin/agent-init")" "$S/repo/scripts/agent-init"
chk "workflow does not duplicate instructions at HOME" "$([ -e "$H/AGENTS.md" ] && echo yes || echo no)" "no"
chk "workflow changes no Claude settings" "$([ -e "$H/.claude/settings.json" ] && echo yes || echo no)" "no"
chk "workflow changes no Codex hooks" "$([ -e "$H/.codex/hooks.json" ] && echo yes || echo no)" "no"
H="$S/h66skills"; mkdir -p "$H/.codex"
HOME="$H" bash "$S/repo/install.sh" workflow --skills-only >/dev/null 2>&1
chk "skills-only still installs skills" "$([ -L "$H/.claude/skills/ship" ] && echo yes || echo no)" "yes"
chk "skills-only still installs project initializer" "$([ -L "$H/.local/bin/agent-init" ] && echo yes || echo no)" "yes"
chk "skills-only omits Claude orchestration" "$([ -e "$H/.claude/CLAUDE.md" ] && echo yes || echo no)" "no"
chk "skills-only omits Codex orchestration" "$([ -e "$H/.codex/AGENTS.md" ] && echo yes || echo no)" "no"
H="$S/h66converge"; mkdir -p "$H/.codex"
HOME="$H" bash "$S/repo/install.sh" workflow >/dev/null 2>&1
HOME="$H" bash "$S/repo/install.sh" workflow --skills-only --check >/dev/null 2>&1; rc=$?
chk "skills-only check rejects installed baselines" "$([ $rc -ne 0 ] && echo yes || echo no)" "yes"
HOME="$H" bash "$S/repo/install.sh" workflow --skills-only >/dev/null 2>&1
chk "skills-only removes installed Claude baseline" "$([ -e "$H/.claude/CLAUDE.md" ] && echo yes || echo no)" "no"
chk "skills-only removes installed Codex baseline" "$([ -e "$H/.codex/AGENTS.md" ] && echo yes || echo no)" "no"
H="$S/h66bline"; mkdir -p "$H/.codex"
HOME="$H" bash "$S/repo/install.sh" workflow --baseline >/dev/null 2>&1
chk "baseline links Claude instructions" "$([ -L "$H/.claude/CLAUDE.md" ] && echo yes || echo no)" "yes"
chk "baseline links Codex instructions" "$([ -L "$H/.codex/AGENTS.md" ] && echo yes || echo no)" "yes"
chk "baseline does not duplicate at HOME" "$([ -e "$H/AGENTS.md" ] && echo yes || echo no)" "no"
H="$S/h66o"; mkdir -p "$H/.codex"
HOME="$H" bash "$S/repo/install.sh" operator >/dev/null 2>&1
chk "operator installs wizard" "$([ -L "$H/.claude/skills/wizard" ] && echo yes || echo no)" "yes"
chk "operator installs Claude styles" "$([ -L "$H/.claude/output-styles/terse.md" ] && echo yes || echo no)" "yes"
chk "operator excludes workflow skills" "$([ -e "$H/.claude/skills/ship" ] && echo yes || echo no)" "no"
chk "operator installs no global instructions" "$([ -e "$H/AGENTS.md" ] && echo yes || echo no)" "no"
chk "operator changes no hook config" \
  "$([ -e "$H/.claude/settings.json" ] || [ -e "$H/.codex/hooks.json" ] && echo yes || echo no)" "no"

H="$S/h66existing"; mkdir -p "$H/.claude" "$H/.codex"
printf '%s\n' "mine" > "$H/.claude/CLAUDE.md"
out="$(HOME="$H" bash "$S/repo/install.sh" workflow 2>&1)"; rc=$?
chk "automatic baseline preserves existing instructions" "$rc" "0"
chk "existing Claude instructions survive" "$(cat "$H/.claude/CLAUDE.md")" "mine"
chk "automatic fallback does not install only one host baseline" "$([ -e "$H/.codex/AGENTS.md" ] && echo yes || echo no)" "no"
chk "automatic fallback explains skills-only mode" "$(grep -c 'installing skills only' <<<"$out")" "1"
chk "automatic fallback still installs initializer" "$([ -L "$H/.local/bin/agent-init" ] && echo yes || echo no)" "yes"

H="$S/h66split"; mkdir -p "$H/.claude" "$H/.codex"
ln -s "$S/repo/AGENTS.md" "$H/.codex/AGENTS.md"
printf '%s\n' "mine" > "$H/.claude/CLAUDE.md"
HOME="$H" bash "$S/repo/install.sh" workflow --check >/dev/null 2>&1; rc=$?
chk "check rejects split host instructions" "$([ $rc -ne 0 ] && echo yes || echo no)" "yes"
HOME="$H" bash "$S/repo/install.sh" workflow >/dev/null 2>&1; rc=$?
chk "automatic fallback repairs split state" "$rc" "0"
chk "automatic fallback removes our orphaned baseline" "$([ -e "$H/.codex/AGENTS.md" ] && echo yes || echo no)" "no"
chk "split repair preserves their instructions" "$(cat "$H/.claude/CLAUDE.md")" "mine"

H="$S/h66flags"; mkdir -p "$H"
HOME="$H" bash "$S/repo/install.sh" workflow --baseline --skills-only >/dev/null 2>&1; rc=$?
chk "baseline and skills-only are mutually exclusive" "$([ $rc -ne 0 ] && echo yes || echo no)" "yes"
chk "invalid baseline flags mutate nothing" "$(find "$H" -type l | wc -l | tr -d ' ')" "0"

H="$S/h66bindot"; mkdir -p "$H/.local" "$H/dotfiles/bin"
ln -s "$H/dotfiles/bin" "$H/.local/bin"
HOME="$H" bash "$S/repo/install.sh" workflow --skills-only >/dev/null 2>&1; rc=$?
chk "dotfile-managed local bin is refused" "$([ $rc -ne 0 ] && echo yes || echo no)" "yes"
chk "dotfile-managed local bin remains empty" "$(find "$H/dotfiles/bin" -mindepth 1 | wc -l | tr -d ' ')" "0"
chk "local bin conflict leaves no workflow links" "$(find "$H" -type l ! -path "$H/.local/bin" | wc -l | tr -d ' ')" "0"

H="$S/h66codexfile"; mkdir -p "$H"
printf '%s\n' "mine" > "$H/.codex"
HOME="$H" bash "$S/repo/install.sh" workflow --skills-only >/dev/null 2>&1; rc=$?
chk "Codex home file is refused before mutation" "$([ $rc -ne 0 ] && echo yes || echo no)" "yes"
chk "Codex home file is untouched" "$(cat "$H/.codex")" "mine"
chk "Codex home file leaves no workflow links" "$(find "$H" -type l | wc -l | tr -d ' ')" "0"
chk "Codex home file records no origin" "$([ -e "$H/.claude/.agent-config-origins" ] && echo yes || echo no)" "no"

H="$S/h66localfile"; mkdir -p "$H"
printf '%s\n' "mine" > "$H/.local"
HOME="$H" bash "$S/repo/install.sh" workflow --skills-only >/dev/null 2>&1; rc=$?
chk "local parent file is refused before mutation" "$([ $rc -ne 0 ] && echo yes || echo no)" "yes"
chk "local parent file is untouched" "$(cat "$H/.local")" "mine"
chk "local parent file leaves no workflow links" "$(find "$H" -type l | wc -l | tr -d ' ')" "0"
chk "local parent file records no origin" "$([ -e "$H/.claude/.agent-config-origins" ] && echo yes || echo no)" "no"

H="$S/h66localsymlink"; mkdir -p "$H/dotfiles/local"
ln -s "$H/dotfiles/local" "$H/.local"
HOME="$H" bash "$S/repo/install.sh" workflow --skills-only >/dev/null 2>&1; rc=$?
chk "dotfile-managed local parent is refused" "$([ $rc -ne 0 ] && echo yes || echo no)" "yes"
chk "dotfile-managed local parent stays empty" "$(find "$H/dotfiles/local" -mindepth 1 | wc -l | tr -d ' ')" "0"
chk "dotfile-managed local parent records no origin" "$([ -e "$H/.claude/.agent-config-origins" ] && echo yes || echo no)" "no"

echo "== 66a. partial uninstall removes only the selected product =="
H="$S/h66u"; mkdir -p "$H/.codex"
HOME="$H" bash "$S/repo/install.sh" full >/dev/null 2>&1
HOME="$H" bash "$S/repo/uninstall.sh" operator >/dev/null 2>&1
chk "operator skill removed" "$([ -e "$H/.claude/skills/wizard" ] && echo yes || echo no)" "no"
chk "operator style removed" "$([ -e "$H/.claude/output-styles/terse.md" ] && echo yes || echo no)" "no"
chk "workflow skill preserved" "$([ -L "$H/.claude/skills/ship" ] && echo yes || echo no)" "yes"
chk "guard hook preserved" "$([ -L "$H/.claude/hooks/guard-bash.py" ] && echo yes || echo no)" "yes"
HOME="$H" bash "$S/repo/uninstall.sh" workflow >/dev/null 2>&1
chk "workflow skill removed" "$([ -e "$H/.claude/skills/ship" ] && echo yes || echo no)" "no"
chk "workflow initializer removed" "$([ -e "$H/.local/bin/agent-init" ] && echo yes || echo no)" "no"
chk "workflow Claude baseline removed" "$([ -e "$H/.claude/CLAUDE.md" ] && echo yes || echo no)" "no"
chk "workflow Codex baseline removed" "$([ -e "$H/.codex/AGENTS.md" ] && echo yes || echo no)" "no"
chk "guard survives workflow uninstall" "$([ -L "$H/.claude/hooks/guard-bash.py" ] && echo yes || echo no)" "yes"
HOME="$H" bash "$S/repo/uninstall.sh" guard >/dev/null 2>&1
chk "guard removed last" "$([ -e "$H/.claude/hooks/guard-bash.py" ] && echo yes || echo no)" "no"
chk "last partial uninstall removes ownership state" "$([ -e "$H/.claude/.agent-config-origins" ] && echo yes || echo no)" "no"

echo "== 66b. workflow has no executable guard dependencies =="
H="$S/h66b"; F="$S/fakebin66b"; mkdir -p "$H" "$F"
for cmd in bash basename chmod cp dirname ln mkdir mktemp mv pwd readlink rm touch; do
  ln -s "$(command -v "$cmd")" "$F/$cmd"
done
PATH="$F" HOME="$H" /bin/bash "$S/repo/install.sh" workflow >/dev/null 2>&1
chk "workflow installs without Python or Git on PATH" "$([ $? -eq 0 ] && echo yes || echo no)" "yes"
chk "workflow still links skills" "$([ -L "$H/.claude/skills/ship" ] && echo yes || echo no)" "yes"
mkdir -p "$H/project"
PATH="$F" HOME="$H" "$H/.local/bin/agent-init" "$H/project" >/dev/null 2>&1
chk "project initializer runs without Python or Git" "$([ $? -eq 0 ] && echo yes || echo no)" "yes"
chk "dependency-free initializer creates relative link" "$(readlink "$H/project/CLAUDE.md")" "AGENTS.md"

echo "== 67. retired lifecycle hooks disappear and user hooks survive =="
# Touching a hook the user already had is the one thing an installer must never
# do. This asserts both directions with a Stop hook of theirs already present.
H="$S/h67"; mkdir -p "$H/.claude"
cat > "$H/.claude/settings.json" <<'JSON'
{
  "hooks": {
    "Stop": [{"hooks": [{"type": "command", "command": "python3 ~/mine/my-own-stop.py"}]}],
    "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "bash ~/mine/my-guard.sh"}]}]
  },
  "model": "claude-opus-5"
}
JSON
HOME="$H" bash "$S/repo/install.sh" full >/dev/null 2>&1
_hookcmds() {  # _hookcmds <settings> <event>
  python3 -c "
import json,sys
h=json.load(open(sys.argv[1])).get('hooks',{}).get(sys.argv[2],[])
print(' '.join(c.get('command','') for e in h for c in e.get('hooks',[])))" "$1" "$2"
}
chk "we add no Stop hook" \
  "$(_hookcmds "$H/.claude/settings.json" Stop | grep -c 'check-docs')" "0"
chk "their Stop hook survives install" \
  "$(_hookcmds "$H/.claude/settings.json" Stop | grep -c 'my-own-stop')" "1"
chk "their PreToolUse survives install" \
  "$(_hookcmds "$H/.claude/settings.json" PreToolUse | grep -c 'my-guard.sh')" "1"
chk "unrelated settings keys survive" \
  "$(python3 -c "import json;print(json.load(open('$H/.claude/settings.json')).get('model'))")" "claude-opus-5"
HOME="$H" bash "$S/repo/uninstall.sh" --apply >/dev/null 2>&1 \
  || HOME="$H" bash "$S/repo/uninstall.sh" >/dev/null 2>&1
chk "no retired Stop hook appears after uninstall" \
  "$(_hookcmds "$H/.claude/settings.json" Stop | grep -c 'check-docs')" "0"
chk "their Stop hook survives uninstall" \
  "$(_hookcmds "$H/.claude/settings.json" Stop | grep -c 'my-own-stop')" "1"
chk "their PreToolUse survives uninstall" \
  "$(_hookcmds "$H/.claude/settings.json" PreToolUse | grep -c 'my-guard.sh')" "1"

echo "== 60. every third-party licence travels with the repo =="
for f in LICENSE THIRD-PARTY-NOTICES.md; do
  chk "$f present" "$([ -s "$S/repo/$f" ] && echo yes || echo no)" "yes"
done
chk "LICENSE points to third-party notices" "$(grep -c 'THIRD-PARTY-NOTICES.md' "$S/repo/LICENSE")" "1"
chk "third-party notice names navigate" "$([ "$(grep -c 'navigate' "$S/repo/THIRD-PARTY-NOTICES.md")" -ge 1 ] && echo yes || echo no)" "yes"

echo "== 68. every malformed hook event aborts before mutation =="
H="$S/h68"; mkdir -p "$H/.claude"
printf '%s\n' '{"hooks":{"Stop":"not-a-list"}}' > "$H/.claude/settings.json"
before="$(cat "$H/.claude/settings.json")"
HOME="$H" bash "$S/repo/install.sh" full >/dev/null 2>&1
rc=$?
chk "malformed Stop exits nonzero" "$([ $rc -ne 0 ] && echo yes || echo no)" "yes"
chk "malformed Stop settings untouched" "$(cat "$H/.claude/settings.json")" "$before"
chk "malformed Stop leaves no links" "$(find "$H" -type l | wc -l | tr -d ' ')" "0"

echo "== 69. every requested baseline path is checked before mutation =="
H="$S/h69"; mkdir -p "$H/.claude"
printf '%s\n' 'mine' > "$H/.claude/CLAUDE.md"
HOME="$H" bash "$S/repo/install.sh" full --baseline >/dev/null 2>&1
rc=$?
chk "baseline conflict exits nonzero" "$([ $rc -ne 0 ] && echo yes || echo no)" "yes"
chk "baseline occupant untouched" "$(cat "$H/.claude/CLAUDE.md")" "mine"
chk "baseline conflict leaves no links" "$(find "$H" -type l | wc -l | tr -d ' ')" "0"

echo "== 70. selective installs prune only their own product =="
H="$S/h70"; mkdir -p "$H/.claude/skills" "$H/.codex/skills"
old="$S/old-agent-config"
printf '%s\n' "$old" > "$H/.claude/.agent-config-origins"
ln -s "$old/operator-skills/wizard" "$H/.claude/skills/wizard"
ln -s "$old/operator-skills/wizard" "$H/.codex/skills/wizard"
HOME="$H" bash "$S/repo/install.sh" workflow >/dev/null 2>&1
chk "workflow preserves stale Claude operator link" "$([ -L "$H/.claude/skills/wizard" ] && echo yes || echo no)" "yes"
chk "workflow preserves stale Codex operator link" "$([ -L "$H/.codex/skills/wizard" ] && echo yes || echo no)" "yes"
ln -s "$old/skills/ship" "$H/.claude/skills/old-ship"
ln -s "$old/skills/ship" "$H/.codex/skills/old-ship"
HOME="$H" bash "$S/repo/install.sh" operator >/dev/null 2>&1
chk "operator preserves stale Claude workflow link" "$([ -L "$H/.claude/skills/old-ship" ] && echo yes || echo no)" "yes"
chk "operator preserves stale Codex workflow link" "$([ -L "$H/.codex/skills/old-ship" ] && echo yes || echo no)" "yes"

echo "== 71. one missing canonical skill aborts before mutation =="
mkdir -p "$S/truncated"; cp -R "$S/repo" "$S/truncated/repo"
rm -rf "$S/truncated/repo/skills/review"
H="$S/h71"; mkdir -p "$H/.codex"
out="$(HOME="$H" bash "$S/truncated/repo/install.sh" workflow 2>&1)"; rc=$?
chk "truncated workflow exits nonzero" "$([ $rc -ne 0 ] && echo yes || echo no)" "yes"
chk "truncated workflow names the missing skill" "$(grep -c 'missing workflow skill review' <<<"$out")" "1"
chk "truncated workflow leaves no links" "$(find "$H" -type l | wc -l | tr -d ' ')" "0"

echo "== 72. --baseline requires its source before mutation =="
mkdir -p "$S/no-baseline"; cp -R "$S/repo" "$S/no-baseline/repo"
rm "$S/no-baseline/repo/AGENTS.md"
H="$S/h72"; mkdir -p "$H/.codex"
out="$(HOME="$H" bash "$S/no-baseline/repo/install.sh" workflow --baseline 2>&1)"; rc=$?
chk "missing baseline exits nonzero" "$([ $rc -ne 0 ] && echo yes || echo no)" "yes"
chk "missing baseline explains the source" "$(grep -c 'missing AGENTS.md' <<<"$out")" "1"
chk "missing baseline leaves no links" "$(find "$H" -type l | wc -l | tr -d ' ')" "0"

echo "== 73. read-only nested destinations abort before mutation =="
H="$S/h73"; mkdir -p "$H/.codex" "$H/.claude/output-styles"
chmod 0555 "$H/.claude/output-styles"
out="$(HOME="$H" bash "$S/repo/install.sh" operator 2>&1)"; rc=$?
chk "read-only output styles exits nonzero" "$([ $rc -ne 0 ] && echo yes || echo no)" "yes"
chk "read-only destination is named" "$(grep -c 'output-styles is not writable' <<<"$out")" "1"
chk "read-only destination leaves no skill links" "$(find "$H" -type l | wc -l | tr -d ' ')" "0"
chk "read-only destination records no origin" "$([ -e "$H/.claude/.agent-config-origins" ] && echo yes || echo no)" "no"
chmod 0755 "$H/.claude/output-styles"

echo "== 74. uninstall preserves preexisting matching deny rules =="
H="$S/h74"; mkdir -p "$H/.claude" "$H/.codex"
printf '%s\n' '{"permissions":{"deny":["Bash(git reset --hard:*)","Bash(mine:*)"]}}' > "$H/.claude/settings.json"
HOME="$H" bash "$S/repo/install.sh" guard >/dev/null 2>&1
HOME="$H" bash "$S/repo/uninstall.sh" guard >/dev/null 2>&1
chk "preexisting matching deny survives" \
  "$(python3 -c "import json; print('Bash(git reset --hard:*)' in json.load(open('$H/.claude/settings.json'))['permissions']['deny'])")" "True"
chk "unrelated deny survives" \
  "$(python3 -c "import json; print('Bash(mine:*)' in json.load(open('$H/.claude/settings.json'))['permissions']['deny'])")" "True"
chk "deny ownership state is removed" "$([ -e "$H/.claude/settings.json.agent-config-deny.json" ] && echo yes || echo no)" "no"

echo
echo "PASS $pass  FAIL $fail"
[[ $fail -eq 0 ]] || exit 1
