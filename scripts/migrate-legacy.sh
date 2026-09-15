#!/usr/bin/env bash
# Remove what 0.3.x (agent-config) and 0.4.x (onbelay) installs left behind, and superseded payloads.
# Usage: migrate-legacy.sh <claude root> <codex root> <payload to keep>
# Prints one line per change. Hook entries in settings.json and hooks.json are handled by the merge/strip helpers.
set -uo pipefail
C="$1" X="$2" KEEP="${3%/}"
SHARE="$HOME/.local/share"

roots=()
for f in "$C/.onbelay-origins" "$C/.agent-config-origins"; do
  [[ -f "$f" ]] || continue
  while IFS= read -r o || [[ -n "$o" ]]; do
    [[ -n "$o" ]] && roots+=("${o%/}")
  done < "$f"
done
for d in "$SHARE"/onbelay/*/ "$SHARE"/agent-config/*/; do
  [[ -f "$d/VERSION" ]] && roots+=("${d%/}")
done

# Only link shapes old installs created, so a dotfiles tree listed as an origin is not claimed.
old_link() {
  local t="${1%/}" r
  for r in ${roots[@]+"${roots[@]}"}; do
    [[ "$r" == "$KEEP" ]] && continue
    case "$t" in
      "$r"/skills/*|"$r"/operator-skills/*|"$r"/hooks/*|"$r"/output-styles/*|\
      "$r"/templates/AGENTS.global.md|"$r"/scripts/agent-init|"$r"/AGENTS.md|"$r"/how-to-use.html)
        return 0 ;;
    esac
  done
  return 1
}

n=0
for l in "$C"/skills/* "$X"/skills/* "$C"/output-styles/* "$C"/hooks/* \
         "$C/CLAUDE.md" "$X/AGENTS.md" "$HOME/AGENTS.md" "$C/how-to-use.html" \
         "$HOME/.local/bin/agent-init"; do
  if [[ -L "$l" ]] && old_link "$(readlink "$l")"; then
    rm -f "$l" && n=$((n+1))
  fi
done
if (( n )); then echo "removed $n links left by an earlier install"; fi
if (( ${#roots[@]} )); then rmdir "$C/output-styles" "$C/skills" "$X/skills" 2>/dev/null; fi

# The managed instruction block, byte for byte as the old merge appended it.
for f in "$C/CLAUDE.md" "$X/AGENTS.md"; do
  [[ -f "$f" ]] && grep -qE '<!-- (onbelay|agent-config):start -->' "$f" || continue
  python3 - "$f" <<'PY' && echo "removed the old instruction block from $f"
import os, re, sys
link = sys.argv[1]
path = os.path.realpath(link)
with open(path, newline="") as fh:
    text = re.sub(r"<!-- (onbelay|agent-config):start -->.*?<!-- \1:end -->", "", fh.read(), flags=re.S)
if not text and not os.path.islink(link) and not any(
        os.path.exists(link + ".before-" + n) for n in ("onbelay", "agent-config")):
    os.unlink(path)
else:
    with open(path, "w", newline="") as fh:
        fh.write(text)
PY
  for b in "$f.before-onbelay" "$f.before-agent-config"; do
    if [[ -f "$b" ]] && cmp -s "$f" "$b"; then rm -f "$b"; fi
  done
done

# Skills an old install moved aside, now that our links no longer occupy their paths.
for f in "$SHARE/onbelay/conflicts.json" "$SHARE/agent-config/conflicts.json"; do
  [[ -f "$f" ]] || continue
  python3 - "$f" <<'PY' && echo "restored skills moved aside by an earlier install"
import json, os, shutil, sys
state = sys.argv[1]
with open(state) as fh:
    entries = json.load(fh)
left = []
for e in entries:
    if not os.path.lexists(e["backup"]):
        continue
    if os.path.lexists(e["path"]):
        left.append(e)
        continue
    os.makedirs(os.path.dirname(e["path"]), exist_ok=True)
    os.rename(e["backup"], e["path"])
if left:
    with open(state, "w") as fh:
        json.dump(left, fh, indent=2)
else:
    os.unlink(state)
    shutil.rmtree(state + ".d", ignore_errors=True)
PY
done

# Old names of state the current helpers own.
rename() {
  [[ -e "$1" ]] || return 0
  if [[ -e "$2" ]]; then rm -f "$1"; else mv "$1" "$2"; fi
  echo "renamed $(basename "$1")"
}
settings="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$C/settings.json")"
rename "$C/settings.json.before-onbelay" "$C/settings.json.before-agent-config"
rename "$settings.onbelay-deny.json" "$settings.agent-config-deny.json"
rename "$X/hooks.json.before-onbelay" "$X/hooks.json.before-agent-config"
rm -f "$C/.onbelay-origins" "$C/.agent-config-origins"

for r in ${roots[@]+"${roots[@]}"}; do
  [[ -d "$r" && "$r" != "$KEEP" ]] || continue
  [[ "$r" == "$SHARE"/onbelay/* || "$r" == "$SHARE"/agent-config/* ]] || continue
  # find exits 1 on a missing dir, which pipefail would read as "no links".
  if { find "$C" "$X" "$HOME/.local/bin" -maxdepth 2 -type l -lname "$r/*" 2>/dev/null || true; } | grep -q .; then
    echo "kept $r: something still links into it"
  else
    rm -rf "$r" && echo "removed payload $r"
  fi
done
rmdir "$SHARE/onbelay" "$SHARE/agent-config" 2>/dev/null
exit 0
