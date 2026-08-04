#!/usr/bin/env bash
# Symlink my-vidwatch into every agent skills directory found on this machine.
# Symlink rather than copy so edits to the working tree take effect immediately.
# Pass --copy to copy instead (for filesystems without symlink support).
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAME="my-vidwatch"
MODE="link"
MIGRATE=0
for arg in "$@"; do
  case "$arg" in
    --copy)    MODE="copy" ;;
    --migrate) MIGRATE=1 ;;
    -h|--help)
      echo "usage: install.sh [--copy] [--migrate]"
      echo "  --copy     copy instead of symlink"
      echo "  --migrate  move an existing real directory aside instead of refusing"
      exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

# Any host that follows the SKILL.md folder convention. A host is only touched
# if its parent directory already exists, so this never creates config for
# tooling that is not installed.
HOSTS=(
  "$HOME/.claude/skills"
  "$HOME/.codex/skills"
  "$HOME/.cursor/skills"
  "$HOME/.gemini/skills"
  "$HOME/.copilot/skills"
  "$HOME/.aider/skills"
  "$HOME/.config/agents/skills"
  "$HOME/.config/opencode/skills"
)

# Real path of the source, so we can refuse to destroy it.
SRC_REAL="$(cd "$SRC" && pwd -P)"

installed=0
refused=0
declare -a SEEN_REAL=()

for dir in "${HOSTS[@]}"; do
  parent="$(dirname "$dir")"
  [[ -d "$parent" ]] || continue          # host not installed, skip silently
  mkdir -p "$dir"

  # Several hosts commonly symlink to one shared skills directory (e.g. both
  # ~/.claude/skills and ~/.codex/skills -> ~/.agents/skills). Resolve to the
  # real path and install once, or the second pass would delete the first.
  dir_real="$(cd "$dir" && pwd -P)"
  dup=""
  for seen in "${SEEN_REAL[@]:-}"; do
    [[ "$seen" == "$dir_real" ]] && dup=1 && break
  done
  if [[ -n "$dup" ]]; then
    echo "  skip $dir (same directory as one already installed)"
    continue
  fi
  SEEN_REAL+=("$dir_real")

  target="$dir_real/$NAME"

  # Guard: the skill already lives here. Linking would mean deleting the source
  # and then pointing at nothing. Nothing to do — it is already installed.
  if [[ "$target" == "$SRC_REAL" ]]; then
    echo "  already in place at $target (source directory) — nothing to do"
    installed=$((installed + 1))
    continue
  fi

  # A real directory here is very likely an install the owner made themselves.
  # An earlier version of this script printed "never remove a real directory"
  # and then ran rm -rf anyway, destroying exactly that. Only symlinks are
  # replaced without asking.
  if [[ -L "$target" ]]; then
    echo "  replacing existing symlink $target"
    rm -rf "$target"
  elif [[ -d "$target" ]]; then
    if [[ $MIGRATE -eq 1 ]]; then
      backup="$target.bak.$(date +%Y%m%d%H%M%S)"
      echo "  --migrate: moving existing directory aside -> $backup"
      mv "$target" "$backup"
    else
      echo "  REFUSED: $target is a real directory, not a symlink." >&2
      echo "           Nothing was removed. It may be an install you made." >&2
      echo "           Re-run with --migrate to move it aside first." >&2
      refused=$((refused + 1))
      continue
    fi
  elif [[ -e "$target" ]]; then
    echo "  REFUSED: $target exists and is neither directory nor symlink." >&2
    refused=$((refused + 1))
    continue
  fi

  if [[ "$MODE" == "copy" ]]; then
    cp -R "$SRC_REAL" "$target"
  else
    ln -s "$SRC_REAL" "$target"
  fi
  echo "  installed -> $target"
  installed=$((installed + 1))
done

if [[ $refused -gt 0 ]]; then
  echo
  echo "$refused location(s) refused. Re-run with --migrate to move them aside." >&2
fi

if [[ $installed -eq 0 ]]; then
  echo "No agent skills directory found, or all were refused. Expected one of:"
  printf '  %s\n' "${HOSTS[@]}"
  echo "Create the parent directory for your host and re-run, or symlink by hand."
  exit 1
fi

echo
python3 "$SRC/scripts/setup.py" || true
