#!/usr/bin/env bash
# Remove what install.sh added, and what earlier installs left behind. Nothing else is touched.
set -euo pipefail

src="${BASH_SOURCE[0]}"
while [[ -L "$src" ]]; do
  dir="$(cd "$(dirname "$src")" && pwd)"
  src="$(readlink "$src")"
  [[ "$src" == /* ]] || src="$dir/$src"
done
REPO="$(cd "$(dirname "$src")" && pwd)"
if (( $# > 1 )) || [[ "${1:-guard}" != guard ]]; then
  echo "usage: uninstall.sh" >&2
  exit 1
fi

C="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
X="${CODEX_HOME:-$HOME/.codex}"
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$1"; }

# First, so legacy state has its current name before the strip reads it.
bash "$REPO/scripts/migrate-legacy.sh" "$C" "$X" "$REPO" | while IFS= read -r line; do ok "$line"; done

if [[ -e "$C/settings.json" ]]; then
  python3 "$REPO/scripts/install_settings.py" strip "$C/settings.json" \
    && ok "removed the guard from $C/settings.json" \
    || warn "left $C/settings.json alone"
fi
for f in "$X/hooks.json" "$HOME/.cursor/hooks.json"; do
  if [[ -e "$f" ]]; then
    python3 "$REPO/scripts/install_hooks_json.py" strip "$f" \
      && ok "removed the guard from $f" \
      || warn "left $f alone"
  fi
done

for l in "$C"/hooks/guard*.py; do
  if [[ -L "$l" && "$(readlink "$l")" == */hooks/"${l##*/}" ]]; then rm -f "$l"; fi
done
rm -f "$C"/hooks/__pycache__/guard*.pyc
rmdir "$C/hooks/__pycache__" "$C/hooks" 2>/dev/null || true
ok "removed the guard links from $C/hooks"

for f in "$C/settings.json" "$X/hooks.json" "$HOME/.cursor/hooks.json"; do
  b="$f.before-agent-config"
  [[ -e "$b" ]] || continue
  if cmp -s "$f" "$b"; then rm -f "$b"; else warn "kept $b: $f changed after install, so it was not restored"; fi
done
echo "Done. Start a new agent session."
