#!/usr/bin/env bash
# Wire this repo into Claude Code and Codex.
#
#   ./install.sh guard             safety hooks only
#   ./install.sh workflow          skills, orchestration, and project init
#   ./install.sh operator          optional human-in-the-loop utilities
#   ./install.sh full              all three products
#   ./install.sh workflow --skills-only  omit global orchestration instructions
#   ./install.sh workflow --baseline  require global orchestration or refuse
#   ./install.sh <profile> --check report state, change nothing
#
# Idempotent, and it never takes a path that is already someone else's. If one
# is occupied it refuses before writing a byte, names every path in the way, and
# prints the `mv` that clears each. It never edits a file it cannot parse. All
# preflight checks run before any mutation, so neither a missing dependency nor
# an occupied path can leave a half-install.
#
# The two files it writes into rather than claims are shared configuration:
# ~/.claude/settings.json and ~/.codex/hooks.json. Existing keys and hooks are
# preserved, and one recovery copy of each pre-existing file is kept.
#
# To remove: ./uninstall.sh
set -euo pipefail

# Resolve through symlinks. `dirname "${BASH_SOURCE[0]}"` alone means running
# this via `~/bin/agent-install -> .../install.sh` aborts with "is this a
# complete clone?", which sends you hunting for the wrong problem.
# Plain `cd`, not `cd -P`: uninstall.sh resolves $REPO the same logical way and
# compares link targets against it as a string, and on macOS -P would turn
# /var into /private/var and stop every one of those comparisons matching.
_SRC="${BASH_SOURCE[0]}"
while [[ -L "$_SRC" ]]; do
  _DIR="$(cd "$(dirname "$_SRC")" && pwd)"
  _SRC="$(readlink "$_SRC")"
  [[ "$_SRC" != /* ]] && _SRC="$_DIR/$_SRC"
done
REPO="$(cd "$(dirname "$_SRC")" && pwd)"
CHECK=0
PROBLEMS=0
PROFILE="guard"
BASELINE_MODE="auto"
_baseline_seen=0
_skills_only_seen=0
_profile_seen=0
_bad_arg() {
  printf '\n  \033[31mABORTED:\033[0m %s\n' "$1" >&2
  printf '  Usage: ./install.sh [guard|workflow|operator|full] [--check] [--baseline|--skills-only]\n\n' >&2
  exit 1
}
# `--dry-run` used to perform a real install, so unknown flags remain fatal.
for _arg in "$@"; do
  case "$_arg" in
    guard|workflow|operator|full)
      (( _profile_seen )) && _bad_arg "more than one profile was supplied."
      PROFILE="$_arg"; _profile_seen=1
      ;;
    --check)
      (( CHECK )) && _bad_arg "--check was supplied more than once."
      CHECK=1
      ;;
    --baseline)
      (( _baseline_seen )) && _bad_arg "--baseline was supplied more than once."
      (( _skills_only_seen )) && _bad_arg "--baseline and --skills-only cannot be combined."
      _baseline_seen=1
      BASELINE_MODE="required"
      ;;
    --skills-only)
      (( _skills_only_seen )) && _bad_arg "--skills-only was supplied more than once."
      (( _baseline_seen )) && _bad_arg "--baseline and --skills-only cannot be combined."
      _skills_only_seen=1
      BASELINE_MODE="off"
      ;;
    *) _bad_arg "unknown argument: $_arg" ;;
  esac
done
if [[ $# -gt 3 ]]; then _bad_arg "too many arguments."; fi
INSTALL_GUARD=0
INSTALL_WORKFLOW=0
INSTALL_OPERATOR=0
[[ "$PROFILE" == guard || "$PROFILE" == full ]] && INSTALL_GUARD=1
[[ "$PROFILE" == workflow || "$PROFILE" == full ]] && INSTALL_WORKFLOW=1
[[ "$PROFILE" == operator || "$PROFILE" == full ]] && INSTALL_OPERATOR=1
(( (_baseline_seen || _skills_only_seen) && ! INSTALL_WORKFLOW )) \
  && _bad_arg "--baseline and --skills-only require the workflow or full profile."
INSTALL_BASELINE=0
REMOVE_AUTO_BASELINE=0
SKILL_ROOTS=()
(( INSTALL_WORKFLOW )) && SKILL_ROOTS+=("$REPO/skills")
(( INSTALL_OPERATOR )) && SKILL_ROOTS+=("$REPO/operator-skills")
WORKFLOW_SKILLS=(navigate prototype bootstrap setup to-spec breakdown domain-modeling architect tdd diagnose review unstick ship)
OPERATOR_SKILLS=(research wizard handoff)

# Claude Code reads CLAUDE_CONFIG_DIR and Codex reads CODEX_HOME. Installing
# into ~/.claude regardless would report a clean "Done" while wiring nothing
# the agent will ever read. Refusing is the honest failure: supporting them
# properly means deriving the paths baked into the hook commands too, and a
# silently unguarded install is the worst of the three outcomes.
# Resolved, not compared as strings: a trailing slash, or a symlinked path
# that lands in the same place, is the same directory and must not be refused.
_same_dir() {
  local a b
  a="$(cd "$1" 2>/dev/null && pwd -P)" || a="$1"
  b="$(cd "$2" 2>/dev/null && pwd -P)" || b="$2"
  [[ "${a%/}" == "${b%/}" ]]
}
for _v in CLAUDE_CONFIG_DIR:.claude CODEX_HOME:.codex; do
  _name="${_v%%:*}"; _dir="$HOME/${_v##*:}"
  _val="$(eval "printf '%s' \"\${$_name:-}\"")"
  if [[ -n "$_val" ]] && ! _same_dir "$_val" "$_dir"; then
    printf '\n  \033[31mABORTED:\033[0m %s points at %s, and this script only installs into %s.\n' \
      "$_name" "$_val" "$_dir" >&2
    printf '  Unset %s and run again. (Supporting it properly means deriving the paths\n' "$_name" >&2
    printf '  baked into the hook commands too, and an install that reports success while\n' >&2
    printf '  wiring nothing your agent reads is the worst of the three outcomes.)\n\n' >&2
    exit 1
  fi
done

ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$1"; }
err()  { printf '  \033[31m✗\033[0m %s\n' "$1"; PROBLEMS=$((PROBLEMS+1)); }
die()  {
  if (( CHECK )); then printf '  \033[31m✗\033[0m %s\n' "$1"; PROBLEMS=$((PROBLEMS+1)); return 0; fi
  printf '\n  \033[31mABORTED:\033[0m %s\n\n' "$1" >&2; exit 1
}

# Every path this repo has ever been installed from. Without it, moving or
# re-cloning the repo makes the NEXT install read our own previous symlinks as
# a dotfile manager's and record 21 `.baklink-` files pointing at the old path;
# uninstall then dutifully restores all 21 as dangling links, which is worse
# than doing nothing, and reports success.
ORIGINS="$HOME/.claude/.agent-config-origins"
_is_our_target() {
  # PATH BOUNDARY, not a bare prefix. `$t == "$REPO"*` also matched any path
  # that merely shares a string prefix with the clone, so a user's own
  # `.../repo-dots/CLAUDE.md` next to `.../repo` was treated as ours: install
  # recorded no backup and uninstall deleted it. Deleting a symlink it did not
  # create is the one thing an uninstaller must never do.
  local t="${1%/}" o
  # Only shapes current or older releases create, not "anything under the
  # clone". A repo cloned at a dotfiles root also contains the user's own stow
  # tree, and claiming all of it meant uninstall deleted their links with no
  # backup recorded. Current releases install skills, guard hooks, and
  # AGENTS.md and the project initializer. Output-style and how-to shapes remain
  # only so upgrades recognize links created by older releases. A new link shape must be added here and to
  # uninstall.sh or the uninstaller will not own it.
  _ours_under() {
    [[ "$t" == "$1"/skills/* || "$t" == "$1"/operator-skills/* \
       || "$t" == "$1"/hooks/* || "$t" == "$1"/AGENTS.md \
       || "$t" == "$1"/scripts/agent-init \
       || "$t" == "$1"/output-styles/* || "$t" == "$1"/how-to-use.html ]]
  }
  _ours_under "$REPO" && return 0
  [[ -f "$ORIGINS" ]] || return 1
  # `|| [[ -n "$o" ]]` so a final line with no trailing newline is still read.
  # Without it an ORIGINS file written by an editor that strips the newline
  # left uninstall recognising nothing and reporting success.
  while IFS= read -r o || [[ -n "$o" ]]; do
    o="${o%/}"
    [[ -n "$o" ]] && _ours_under "$o" && return 0
  done < "$ORIGINS"
  return 1
}

# A clean workflow install gets the small always-loaded orchestration layer.
# Existing user instructions are never partially replaced: auto mode installs
# neither host baseline when either path is occupied. --baseline is the strict
# form for users who want a collision to stop the install instead.
_baseline_available() {
  local p
  for p in "$HOME/.claude/CLAUDE.md" "$HOME/.codex/AGENTS.md"; do
    [[ -e "$p" || -L "$p" ]] || continue
    if [[ -L "$p" ]] && _is_our_target "$(readlink "$p")"; then
      continue
    fi
    return 1
  done
  return 0
}
_baseline_has_owned_link() {
  local p
  for p in "$HOME/.claude/CLAUDE.md" "$HOME/.codex/AGENTS.md"; do
    [[ -L "$p" ]] && _is_our_target "$(readlink "$p")" && return 0
  done
  return 1
}
if (( INSTALL_WORKFLOW )); then
  case "$BASELINE_MODE" in
    required) INSTALL_BASELINE=1 ;;
    off)
      INSTALL_BASELINE=0
      _baseline_has_owned_link && REMOVE_AUTO_BASELINE=1
      ;;
    auto)
      if _baseline_available; then
        INSTALL_BASELINE=1
      else
        INSTALL_BASELINE=0
        _baseline_has_owned_link && REMOVE_AUTO_BASELINE=1
        warn "existing global agent instructions detected; preserving both hosts and installing skills only. Reconcile them, then rerun with --baseline to require shared orchestration."
      fi
      ;;
  esac
fi

# Paths we want that are occupied by something the user owns. Collected by the
# preflight and printed together: finding out about them one `mv` at a time,
# across three runs, is its own kind of hostile.
OCCUPIED=()

claim() {  # claim <path> -- free, or already ours, or record it
  local p="$1"
  [[ -e "$p" || -L "$p" ]] || return 0            # free
  if [[ -L "$p" ]]; then
    # Ours, from this clone or a previous location.
    _is_our_target "$(readlink "$p")" && return 0
    # Dangling: the target is gone, so the link points at nothing and there is
    # nothing to lose by replacing it. Refusing here would mean a moved or
    # deleted clone leaves a machine that re-running install can never repair.
    [[ -e "$p" ]] || { warn "replacing a broken link at $p (its target is gone)"; return 0; }
  fi
  OCCUPIED+=("$p")
  return 1
}

claim_shared_file() {  # claim_shared_file <path> -- every symlink is occupied
  local p="$1"
  [[ -L "$p" ]] || return 0
  OCCUPIED+=("$p")
  return 1
}

# Everything install writes, checked BEFORE anything is written. The list has
# to be exhaustive: a path that installs without being claimed here is a path
# that can still clobber something.
preflight_paths() {
  local d name f root
  if (( INSTALL_BASELINE )); then
    claim "$HOME/.claude/CLAUDE.md" || true
    claim "$HOME/.codex/AGENTS.md" || true
  fi
  if (( INSTALL_GUARD )); then
    # Shared JSON files are merged rather than claimed. Symlinks are refused,
    # because an atomic rewrite would silently detach a dotfile manager.
    claim_shared_file "$HOME/.claude/settings.json" || true
    claim_shared_file "$HOME/.codex/hooks.json" || true
  fi
  # A container directory is only a conflict when it is a SYMLINK: a real
  # directory is where we put our links, alongside whatever else is in it.
  if (( INSTALL_WORKFLOW || INSTALL_OPERATOR )); then
    for d in "$HOME/.claude/skills" "$HOME/.codex/skills"; do
      [[ -L "$d" ]] && { claim "$d" || true; }
    done
    for root in "${SKILL_ROOTS[@]}"; do
      for d in "$root"/*/; do
        [[ -f "$d/SKILL.md" ]] || continue
        name="$(basename "$d")"
        claim "$HOME/.claude/skills/$name" || true
        [[ -d "$HOME/.codex" ]] && { claim "$HOME/.codex/skills/$name" || true; }
      done
    done
  fi
  if (( INSTALL_WORKFLOW )); then
    [[ -L "$HOME/.local" ]] && { claim "$HOME/.local" || true; }
    [[ -L "$HOME/.local/bin" ]] && { claim "$HOME/.local/bin" || true; }
    claim "$HOME/.local/bin/agent-init" || true
  fi
  if (( INSTALL_OPERATOR )); then
    [[ -L "$HOME/.claude/output-styles" ]] && { claim "$HOME/.claude/output-styles" || true; }
    for f in "$REPO"/output-styles/*.md; do
      [[ -f "$f" ]] && { claim "$HOME/.claude/output-styles/$(basename "$f")" || true; }
    done
  fi
  if (( INSTALL_GUARD )); then
    [[ -L "$HOME/.claude/hooks" ]] && { claim "$HOME/.claude/hooks" || true; }
    for f in "$REPO"/hooks/guard*.py; do
      [[ -f "$f" ]] && { claim "$HOME/.claude/hooks/$(basename "$f")" || true; }
    done
  fi
}

refuse_if_occupied() {
  (( ${#OCCUPIED[@]} )) || return 0
  printf '\n  \033[31mABORTED:\033[0m %d path(s) are occupied by something that is not ours.\n\n' \
    "${#OCCUPIED[@]}" >&2
  printf '  Nothing has been changed. This installer will not move, copy or delete\n' >&2
  printf '  a file it did not create, because an installer that can do that quietly\n' >&2
  printf '  is how people lose configuration they cannot get back.\n\n' >&2
  local p
  for p in "${OCCUPIED[@]}"; do
    printf '    mv ' >&2
    printf '%q ' "$p" >&2
    printf '%q\n' "$p.mine" >&2
  done
  printf '\n  Run those, then ./install.sh again.\n' >&2
  printf '  (Using stow or chezmoi? Unstow these paths first.)\n\n' >&2
  exit 1
}

# Prune links to skills this repo no longer ships. Both loops above iterate
# what EXISTS in the repo, so a renamed or deleted skill leaves a dangling
# symlink that both agents still scan, and --check called it "all good".
# It is also what sets up the silent-abort case: a dangling entry whose name
# later comes back is what used to crash the installer.
prune_stale() {  # prune_stale <dir> <display-kind> <source-root>...
  local dir="$1" kind="$2" l source_root matches
  shift 2
  [[ -d "$dir" && ! -L "$dir" ]] || return 0
  for l in "$dir"/*; do
    [[ -L "$l" ]] || continue
    _t="$(readlink "$l")"
    # _is_our_target, not a raw $REPO prefix: a link left by a PREVIOUS
    # location is exactly the stale one worth pruning, and matching only the
    # current path missed it.
    matches=0
    for source_root in "$@"; do
      [[ "$_t" == */"$source_root"/* ]] && { matches=1; break; }
    done
    (( matches )) || continue
    _is_our_target "$_t" || continue
    [[ -e "$l" ]] && continue
    if (( CHECK )); then
      err "stale ${kind%s} link $(basename "$l"): this repo no longer ships it"
    else
      rm -f "$l"; warn "removed stale ${kind%s} link $(basename "$l")"
    fi
  done
}

prune_selected_skills() {  # prune_selected_skills <host skill dir>
  local dir="$1"
  (( INSTALL_WORKFLOW )) && prune_stale "$dir" skills skills
  (( INSTALL_OPERATOR )) && prune_stale "$dir" skills operator-skills
  return 0
}

link() {  # link <target> <linkname>
  # The preflight has already refused anything here that is not ours, so the
  # only thing this can replace is one of our own links from an earlier run.
  local target="$1" name="$2"
  if [[ -L "$name" ]]; then
    if [[ "$(readlink "$name")" == "$target" ]]; then ok "$name"; return; fi
    (( CHECK )) && { err "$name points at $(readlink "$name")"; return; }
    rm "$name"
  elif [[ -e "$name" ]]; then
    # Unreachable after preflight. Refuse rather than assume: a path that got
    # here is a hole in preflight_paths, and deleting it would be the exact
    # behaviour this design removed.
    (( CHECK )) && { err "$name exists and is not a symlink"; return; }
    printf '\n  \033[31mABORTED:\033[0m %s exists and preflight did not claim it.\n' "$name" >&2
    printf '  That is a bug in preflight_paths. Nothing was changed.\n\n' >&2
    exit 1
  else
    (( CHECK )) && { err "$name missing"; return; }
  fi
  ln -s "$target" "$name"
  ok "$name -> $target"
}

# ---------------------------------------------------------------- preflight
# Everything that could fail is checked BEFORE anything is written. A
# half-install is worse than no install: it can leave CLAUDE.md promising
# guardrails that were never wired.
echo "agent-config $PROFILE profile at $REPO"
(( CHECK )) && echo "(check only, nothing will change)"
echo
echo "Preflight"

GUARD_READY=1
if (( INSTALL_GUARD )); then
  if command -v python3 >/dev/null 2>&1; then
    PYV="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
    if python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,8) else 1)'; then
      ok "python3 $PYV"
    else
      die "python3 is $PYV; 3.8 or newer is required."
      GUARD_READY=0
    fi
  else
    die "python3 not found on PATH. The guard hooks are Python; install it first."
    GUARD_READY=0
  fi

  if ! command -v git >/dev/null 2>&1; then
    die "git not found on PATH. The guard rules shell out to git, and without it a branch lookup fails, which the guard treats as protected. Install git first."
    GUARD_READY=0
  fi
fi

# Anything we WRITE must be a regular file, and anything we fill with symlinks
# must be a directory. Each of these otherwise aborts partway with a bare
# `mkdir:`/`IsADirectoryError`, leaving a half-install, or worse: a hooks.json
# that is a directory makes `mv` move the temp file INTO it and report success
# while Codex ends up with no guardrails at all.
if (( INSTALL_GUARD )); then
  for f in "$HOME/.claude/settings.json" "$HOME/.codex/hooks.json"; do
    if [[ -e "$f" && ! -f "$f" ]]; then
      die "$f exists but is not a regular file. Move it aside first."
    fi
  done
  if [[ -e "$HOME/.claude/hooks" && ! -d "$HOME/.claude/hooks" ]]; then
    die "$HOME/.claude/hooks exists but is not a directory. Move it aside first."
  fi
  for f in hooks/guard_rules.py hooks/guard_parse.py hooks/guard_git.py \
           hooks/guard_repo.py hooks/guard_paths.py \
           hooks/guard_secrets.py hooks/guard_db.py hooks/guard_tools.py \
           hooks/guard-bash.py hooks/guard-files.py hooks/guard-codex.py \
           hooks/tests.py hooks/floor.py scripts/install_settings.py \
           scripts/install_codex_hooks.py; do
    [[ -f "$REPO/$f" ]] || die "missing $f. Is this a complete clone?"
  done
  ok "guard scripts present"
fi
if (( INSTALL_WORKFLOW || INSTALL_OPERATOR )); then
  if [[ -e "$HOME/.codex" && ! -d "$HOME/.codex" ]]; then
    die "$HOME/.codex exists but is not a directory. Move it aside first."
  fi
  for d in "$HOME/.claude/skills" "$HOME/.codex/skills"; do
    if [[ -e "$d" && ! -d "$d" ]]; then
      die "$d exists but is not a directory. Move it aside first."
    fi
  done
fi
if (( INSTALL_WORKFLOW )); then
  if [[ -e "$HOME/.local" && ! -d "$HOME/.local" ]]; then
    die "$HOME/.local exists but is not a directory. Move it aside first."
  fi
  if [[ -d "$HOME/.local" && ! -e "$HOME/.local/bin" && ! -w "$HOME/.local" ]]; then
    die "$HOME/.local is not writable. Nothing has been changed."
  fi
  if [[ -e "$HOME/.local/bin" && ! -d "$HOME/.local/bin" ]]; then
    die "$HOME/.local/bin exists but is not a directory. Move it aside first."
  fi
  for f in scripts/agent-init templates/AGENTS.project.md; do
    [[ -f "$REPO/$f" ]] || die "missing $f. Is this a complete clone?"
  done
  ok "project instruction initializer present"
fi
if (( INSTALL_OPERATOR )) && [[ -e "$HOME/.claude/output-styles" && ! -d "$HOME/.claude/output-styles" ]]; then
  die "$HOME/.claude/output-styles exists but is not a directory. Move it aside first."
fi
if (( INSTALL_OPERATOR )); then
  for f in output-styles/eli5.md output-styles/terse.md \
           operator-profiles/codex/eli5.AGENTS.md \
           operator-profiles/codex/terse.AGENTS.md; do
    [[ -f "$REPO/$f" ]] || die "missing $f. Is this a complete clone?"
  done
  ok "operator communication profiles present"
fi
if (( INSTALL_BASELINE )) && [[ ! -f "$REPO/AGENTS.md" ]]; then
  die "missing AGENTS.md required by --baseline. Is this a complete clone?"
fi

# Existing destination containers must be writable before the first link or
# ownership record is created. Checking only ~/.claude missed a read-only
# output-styles directory and left a partial operator installation behind.
DESTINATION_DIRS=()
if (( INSTALL_WORKFLOW || INSTALL_OPERATOR )); then
  DESTINATION_DIRS+=("$HOME/.claude/skills")
  [[ -d "$HOME/.codex" ]] && DESTINATION_DIRS+=("$HOME/.codex/skills")
fi
(( INSTALL_WORKFLOW )) && DESTINATION_DIRS+=("$HOME/.local/bin")
(( INSTALL_OPERATOR )) && DESTINATION_DIRS+=("$HOME/.claude/output-styles")
(( INSTALL_GUARD )) && DESTINATION_DIRS+=("$HOME/.claude/hooks")
for d in "${DESTINATION_DIRS[@]}"; do
  if [[ -d "$d" && ! -w "$d" ]]; then
    die "$d is not writable. Nothing has been changed."
  fi
done

# Codex hooks.json is shared configuration, just like Claude settings.json.
# Validate it before any mutation so a malformed user file cannot leave a
# half-install after the Claude half has already been wired.
if (( INSTALL_GUARD && GUARD_READY )) && [[ -f "$HOME/.codex/hooks.json" ]]; then
  python3 "$REPO/scripts/install_codex_hooks.py" validate "$HOME/.codex/hooks.json" \
    || die "$HOME/.codex/hooks.json is not valid hook configuration. Fix or move it first; this script will not rewrite a file whose shape it does not understand."
  ok "existing Codex hooks.json parses and has the expected shape"
fi

# Nothing has been written yet, and nothing will be if any path we want is
# occupied by something the user owns. --check reports instead: it is
# read-only by contract, so it must not abort on a state it is meant to
# describe.
if (( ! CHECK )); then
  preflight_paths
  refuse_if_occupied
fi

# Every skill is a real directory now; nothing here is a symlink into a vendor
# tree, so a ZIP download or a clone with core.symlinks=false can no longer
# silently produce a half-installed suite. Count them so a truncated checkout
# is still obvious.
# `|| true` is load-bearing: with `set -euo pipefail`, a glob that matches
# nothing makes ls exit non-zero, pipefail propagates it, and the script died
# SILENTLY before it could say what was wrong. An installer that aborts with no
# message is worse than one that aborts.
if (( INSTALL_WORKFLOW )); then
  for _skill in "${WORKFLOW_SKILLS[@]}"; do
    [[ -f "$REPO/skills/$_skill/SKILL.md" ]] \
      || die "missing workflow skill $_skill. Is this a complete clone?"
  done
  ok "${#WORKFLOW_SKILLS[@]} required workflow skills present"
fi
if (( INSTALL_OPERATOR )); then
  for _skill in "${OPERATOR_SKILLS[@]}"; do
    [[ -f "$REPO/operator-skills/$_skill/SKILL.md" ]] \
      || die "missing operator skill $_skill. Is this a complete clone?"
  done
  ok "${#OPERATOR_SKILLS[@]} required operator skills present"
fi

if (( ! CHECK )); then
  mkdir -p "$HOME/.claude" 2>/dev/null || die "cannot create $HOME/.claude (is HOME read-only?)"
  touch "$HOME/.claude/.agent-config-write-test" 2>/dev/null \
    || die "$HOME/.claude is not writable. Nothing has been changed."
  rm -f "$HOME/.claude/.agent-config-write-test"
  touch "$HOME/.agent-config-write-test" 2>/dev/null \
    || die "$HOME is not writable. Nothing has been changed."
  rm -f "$HOME/.agent-config-write-test"
  # ~/.codex too, or the Claude half completes and the Codex half aborts under
  # set -e, which is exactly the half-install the preflight promises to prevent.
  if [[ -d "$HOME/.codex" ]]; then
    touch "$HOME/.codex/.agent-config-write-test" 2>/dev/null \
      || die "$HOME/.codex is not writable. Nothing has been changed."
    rm -f "$HOME/.codex/.agent-config-write-test"
  fi
  ok "HOME is writable"
fi

if (( INSTALL_GUARD )) && [[ -L "$HOME/.claude/settings.json" && ! -e "$HOME/.claude/settings.json" ]]; then
  die "$HOME/.claude/settings.json is a symlink pointing at something that does not exist. Fix or remove it first; installing over it would leave the hooks unwired."
fi

if (( INSTALL_GUARD && GUARD_READY )); then
  python3 "$REPO/scripts/install_settings.py" validate "$HOME/.claude/settings.json" 2>/dev/null \
    || die "$HOME/.claude/settings.json or its agent-config ownership state is invalid. Fix or move it first; this script will not rewrite state whose shape it does not understand."
  [[ -f "$HOME/.claude/settings.json" ]] \
    && ok "existing settings.json parses and has the expected shape"
fi

# Correctness gates the install. The wall-clock budgets do not: they flake on
# a loaded machine, and aborting there told the adopter the checkout was broken
# when re-running the suggested command immediately printed PASS.
if (( INSTALL_GUARD && GUARD_READY )) && ! SUITE_OUT="$(python3 "$REPO/hooks/tests.py" --no-perf 2>&1)"; then
  die "guard regression suite fails in this checkout:
$SUITE_OUT"
fi
(( INSTALL_GUARD && GUARD_READY )) && ok "guard tests pass"

# The second suite grades the guard against the job rather than its own rules,
# which is why it catches whole classes the rule-level suite never looked for.
if (( INSTALL_GUARD && GUARD_READY )) && ! FLOOR_OUT="$(python3 "$REPO/hooks/floor.py" 2>&1)"; then
  die "guard floor suite fails in this checkout:
$FLOOR_OUT"
fi
(( INSTALL_GUARD && GUARD_READY )) && ok "guard floor holds"

# Auto mode is all-or-nothing across hosts. If the user has replaced one
# instruction path since an earlier install, remove our remaining sibling link
# only after every preflight and correctness gate has passed. --check reports
# the split instead of calling it healthy.
if (( REMOVE_AUTO_BASELINE )); then
  if (( CHECK )); then
    if [[ "$BASELINE_MODE" == off ]]; then
      err "global agent-config instructions are still installed; run without --check to remove them for --skills-only mode"
    else
      err "global instructions are split: one host still uses agent-config while the other is user-owned"
    fi
  else
    for p in "$HOME/.claude/CLAUDE.md" "$HOME/.codex/AGENTS.md"; do
      if [[ -L "$p" ]] && _is_our_target "$(readlink "$p")"; then
        rm "$p"
        warn "removed agent-config baseline at $p so both hosts preserve user-owned instructions"
      fi
    done
  fi
fi

# Record where we are installing from, so a later run from a different path
# still recognises these links as ours. AFTER every gate: writing it during
# preflight meant an aborted install still widened _is_our_target permanently.
if (( ! CHECK )); then
  if ! { [[ -f "$ORIGINS" ]] && grep -qxF -- "$REPO" "$ORIGINS"; }; then
    # Terminate a previous line that lost its newline first, or the two paths
    # concatenate into one bogus origin and the older one is lost. Round 16
    # fixed the READ side of this and left the write.
    if [[ -s "$ORIGINS" && -n "$(tail -c 1 "$ORIGINS")" ]]; then
      printf '\n' >> "$ORIGINS" 2>/dev/null || true
    fi
    printf '%s\n' "$REPO" >> "$ORIGINS" 2>/dev/null || true
  fi
fi

if (( INSTALL_WORKFLOW )); then
  (( CHECK )) || mkdir -p "$HOME/.local/bin"
  link "$REPO/scripts/agent-init" "$HOME/.local/bin/agent-init"
  case ":${PATH:-}:" in
    *:"$HOME/.local/bin":*) ;;
    *) warn "$HOME/.local/bin is not on PATH; run $HOME/.local/bin/agent-init directly or add that directory to PATH." ;;
  esac
fi

# ---------------------------------------------------------------- claude code
echo
echo "Claude Code"
if (( INSTALL_WORKFLOW || INSTALL_OPERATOR )); then
(( CHECK )) || mkdir -p "$HOME/.claude/skills"
# Link each skill individually rather than replacing ~/.claude/skills wholesale.
# Taking over the directory would silently stop any skill the user wrote
# themselves, which is not a trade an installer gets to make on their behalf.
if [[ -L "$HOME/.claude/skills" ]]; then
  # A dotfile manager pointing the whole directory elsewhere was refused by
  # preflight, so this can only be an older install of ours.
  (( CHECK )) || { rm "$HOME/.claude/skills"; mkdir -p "$HOME/.claude/skills"; }
fi
n=0; missing=0
for root in "${SKILL_ROOTS[@]}"; do
  for d in "$root"/*/; do
    [[ -f "$d/SKILL.md" ]] || continue
    name="$(basename "$d")"
    if (( CHECK )); then
      [[ -L "$HOME/.claude/skills/$name" && "$(readlink "$HOME/.claude/skills/$name")" == "$d" ]] \
        || { err "claude skill $name not linked to this repo"; missing=1; }
    else
      if [[ -L "$HOME/.claude/skills/$name" && "$(readlink "$HOME/.claude/skills/$name")" == "$d" ]]; then
        : # already ours; do NOT re-record it as if it were the user's
      elif [[ -e "$HOME/.claude/skills/$name" || -L "$HOME/.claude/skills/$name" ]]; then
        # Ours from a previous clone location: preflight refused anything
        # that is not ours, so this can only be our own stale link.
        rm -f "$HOME/.claude/skills/$name"
      fi
      ln -sfn "$d" "$HOME/.claude/skills/$name"; n=$((n+1))
    fi
  done
done
prune_selected_skills "$HOME/.claude/skills"
(( CHECK )) && (( ! missing )) && ok "all skills linked into ~/.claude/skills"
(( CHECK )) || ok "$n skills linked into ~/.claude/skills (your own are untouched)"

fi

if (( INSTALL_OPERATOR )); then
  (( CHECK )) || mkdir -p "$HOME/.claude/output-styles"
  if [[ -L "$HOME/.claude/output-styles" ]]; then
    (( CHECK )) || { rm "$HOME/.claude/output-styles"; mkdir -p "$HOME/.claude/output-styles"; }
  fi
  sn=0; style_missing=0
  for f in "$REPO"/output-styles/*.md; do
    [[ -f "$f" ]] || continue
    name="$(basename "$f")"
    if (( CHECK )); then
      [[ -L "$HOME/.claude/output-styles/$name" \
         && "$(readlink "$HOME/.claude/output-styles/$name")" == "$f" ]] \
        || { err "Claude output style $name not linked to this repo"; style_missing=1; }
    else
      [[ -e "$HOME/.claude/output-styles/$name" || -L "$HOME/.claude/output-styles/$name" ]] \
        && rm -f "$HOME/.claude/output-styles/$name"
      ln -s "$f" "$HOME/.claude/output-styles/$name"; sn=$((sn+1))
    fi
  done
  (( CHECK )) && (( ! style_missing )) && ok "all Claude output styles linked"
  (( CHECK )) || ok "$sn Claude output styles linked (none selected)"
fi

if (( INSTALL_GUARD )); then
# Link the hook scripts individually too. Taking over ~/.claude/hooks would
# break any hook the user already wired there, and worse: settings.json keeps
# their entry, so a now-missing script makes python3 exit 2, and exit 2 in
# PreToolUse means BLOCK. Replacing the directory would turn their own hook
# into a block-everything rule.
(( CHECK )) || mkdir -p "$HOME/.claude/hooks"
if [[ -L "$HOME/.claude/hooks" ]]; then
  # Someone else's link here was refused by preflight; ours is safe to replace.
  (( CHECK )) || { rm "$HOME/.claude/hooks"; mkdir -p "$HOME/.claude/hooks"; }
fi
hn=0
# guard*.py includes the host entry points and every module they import.
# Anything added here needs a matching --check assertion below.
for f in "$REPO"/hooks/guard*.py; do
  [[ -e "$f" ]] || continue
  base="$(basename "$f")"
  if (( CHECK )); then
    [[ -L "$HOME/.claude/hooks/$base" && "$(readlink "$HOME/.claude/hooks/$base")" == "$f" ]] \
      || err "hook $base not linked to this repo"
  else
    if [[ -L "$HOME/.claude/hooks/$base" && "$(readlink "$HOME/.claude/hooks/$base")" == "$f" ]]; then
      : # already ours
    elif [[ -e "$HOME/.claude/hooks/$base" || -L "$HOME/.claude/hooks/$base" ]]; then
      rm -f "$HOME/.claude/hooks/$base"
    fi
    ln -sfn "$f" "$HOME/.claude/hooks/$base"; hn=$((hn+1))
  fi
done
prune_stale "$HOME/.claude/hooks" hooks hooks
(( CHECK )) || ok "$hn hook scripts linked into ~/.claude/hooks (your own are untouched)"

# settings.json also holds the user's model, theme, and permissions, so it is
# merged rather than replaced. The `test -f` prefix means that deleting this
# repo degrades to "no guardrails" instead of blocking every tool call: a
# missing script makes python3 exit 2, and exit 2 in PreToolUse means BLOCK.
SETTINGS="$HOME/.claude/settings.json"
if (( GUARD_READY && ! CHECK )); then
  # One copy, once, before the first change. Not per-run: repeated installs
  # used to pile up identical backups.
  if [[ -f "$SETTINGS" && ! -e "$SETTINGS.before-agent-config" ]]; then
    cp "$SETTINGS" "$SETTINGS.before-agent-config"
    warn "settings.json copied to settings.json.before-agent-config"
  fi
  # The merge lives in scripts/install_settings.py, with a test suite that
  # runs in milliseconds. It was 115 lines of Python inside this heredoc,
  # reachable only by running a real install into a fake HOME.
  python3 "$REPO/scripts/install_settings.py" merge "$SETTINGS"
  ok "settings.json PreToolUse hooks (existing keys preserved)"
elif (( GUARD_READY )); then
  # The same test the merge uses. A substring match called a hook that merely
  # MENTIONS the path "wired", and it never looked at the file matcher at all,
  # so --check said "all good" on a HOME with no guardrails running.
  python3 - "$SETTINGS" <<'PYCHECK' 2>/dev/null \
    && ok "settings.json guard hooks" || err "settings.json guard hooks missing or not wired"
import json, re, sys
try:
    cfg = json.load(open(sys.argv[1]))
except Exception:
    raise SystemExit(1)
R = re.compile(r"python3?\s+\S*[./]claude/hooks/guard-(bash|files)\.py(\s|;|$)")
found = set()
for entry in cfg.get("hooks", {}).get("PreToolUse", []):
    if not isinstance(entry, dict):
        continue
    for h in entry.get("hooks", []):
        m = R.search(str(h.get("command", ""))) if isinstance(h, dict) else None
        if m:
            found.add(m.group(1))
raise SystemExit(0 if found == {"bash", "files"} else 1)
PYCHECK
fi
fi

if (( INSTALL_BASELINE )); then
  link "$REPO/AGENTS.md" "$HOME/.claude/CLAUDE.md"
fi

# ---------------------------------------------------------------------- codex
echo
echo "Codex"
if [[ -d "$HOME/.codex" ]] || (( INSTALL_WORKFLOW )); then
  if (( INSTALL_WORKFLOW || INSTALL_OPERATOR )); then
  # Codex owns ~/.codex/skills: it preinstalls its own .system skills there,
  # so link each skill individually instead of replacing the directory.
  # A dotfile-managed symlink here gets the same treatment as the Claude side:
  # record the target and stand a real directory up. Without this, install
  # dropped one symlink per skill straight into the user's stow tree and
  # uninstall could never clean them out.
  if [[ -L "$HOME/.codex/skills" ]]; then
    (( CHECK )) || { rm "$HOME/.codex/skills"; }
  fi
  (( CHECK )) || mkdir -p "$HOME/.codex/skills"
  n=0; missing=0
  for root in "${SKILL_ROOTS[@]}"; do
    for d in "$root"/*/; do
      [[ -f "$d/SKILL.md" ]] || continue
      name="$(basename "$d")"
      if (( CHECK )); then
        [[ -L "$HOME/.codex/skills/$name" && "$(readlink "$HOME/.codex/skills/$name")" == "$d" ]] \
          || { err "codex skill $name not linked to this repo"; missing=1; }
      else
        if [[ -L "$HOME/.codex/skills/$name" && "$(readlink "$HOME/.codex/skills/$name")" == "$d" ]]; then
          : # already ours
        elif [[ -e "$HOME/.codex/skills/$name" || -L "$HOME/.codex/skills/$name" ]]; then
          rm -f "$HOME/.codex/skills/$name"
        fi
        ln -sfn "$d" "$HOME/.codex/skills/$name"; n=$((n+1))
      fi
    done
  done
  prune_selected_skills "$HOME/.codex/skills"
  (( CHECK )) && (( ! missing )) && ok "all skills linked into ~/.codex/skills"
  (( CHECK )) || ok "$n skills linked into ~/.codex/skills"
  (( INSTALL_BASELINE )) && link "$REPO/AGENTS.md" "$HOME/.codex/AGENTS.md"
  fi

  if (( INSTALL_GUARD )); then
    CODEX_HOOKS="$HOME/.codex/hooks.json"
    if (( GUARD_READY && ! CHECK )); then
      if [[ -f "$CODEX_HOOKS" && ! -e "$CODEX_HOOKS.before-agent-config" ]]; then
        cp "$CODEX_HOOKS" "$CODEX_HOOKS.before-agent-config"
        warn "hooks.json copied to hooks.json.before-agent-config"
      fi
      python3 "$REPO/scripts/install_codex_hooks.py" merge "$CODEX_HOOKS" "$REPO" \
        || die "could not merge agent-config hooks into $CODEX_HOOKS"
      ok "hooks.json PreToolUse guard merged (existing hooks preserved)"
      warn "review and trust new or changed Codex hooks with /hooks."
    elif (( GUARD_READY )); then
      # A deleted Codex hook must not report "all good".
      if python3 "$REPO/scripts/install_codex_hooks.py" check "$CODEX_HOOKS" "$REPO"; then
        ok "codex hooks.json guard parity"
      else
        err "codex hooks.json missing, unparseable, or missing the agent-config guard"
      fi
      # Trust is keyed to each current hook definition and is intentionally not
      # inferred from private config internals. /hooks is the supported view.
      warn "hook trust is user-reviewed state; inspect it with /hooks."
    fi
  fi
else
  warn "no ~/.codex, skipping Codex operator or guard wiring"
fi

echo
if (( CHECK )); then
  if (( PROBLEMS )); then
    echo "Check complete: $PROBLEMS problem(s). Run ./install.sh $PROFILE to fix."
    exit 1
  fi
  echo "Check complete: all good."
else
  if [[ "$PROFILE" == guard ]]; then
    echo "Done. Review hook trust in each host, then start a new agent session."
  elif [[ "$PROFILE" == workflow ]]; then
    echo "Done. Start a new agent session to pick up the workflow skills."
  elif [[ "$PROFILE" == operator ]]; then
    echo "Done. Start a new agent session to pick up the optional operator tools."
  else
    echo "Done. Review hook trust, then start a new agent session."
  fi
  echo "To remove: $REPO/uninstall.sh"
fi

exit 0
