#!/usr/bin/env bash
set -uo pipefail

SRC=research/tldr/src
COMPILE="python3 lib/compile.py"

compile_all() {
  echo "Compiling all TLDRs"
  $COMPILE --once "$SRC"
}

refresh_index() {
  echo "Refreshing TLDR index"
  $COMPILE --index "$SRC"
}

if [ "${EVENT_NAME:-}" = "workflow_dispatch" ]; then
  echo "Manual dispatch"
  compile_all
  exit $?
fi

BASE="${BEFORE_SHA:-}"
if [ -z "$BASE" ] \
  || [ "$BASE" = "0000000000000000000000000000000000000000" ] \
  || ! git cat-file -e "${BASE}^{commit}" 2>/dev/null; then
  echo "No usable diff base"
  compile_all
  exit $?
fi

shopt -s nullglob
cached=(research/tldr/*/index.html)
shopt -u nullglob
if [ "${#cached[@]}" -eq 0 ]; then
  echo "No cached output to build on"
  compile_all
  exit $?
fi

changed="$(git diff --name-only "$BASE" "${HEAD_SHA}")"

if echo "$changed" | grep -qE '^lib/(compile\.py|render_math\.js|package(-lock)?\.json)$'; then
  echo "Compiler changed"
  compile_all
  exit $?
fi

if echo "$changed" | grep -E "^${SRC}/" | grep -qvE '\.mdtx$'; then
  echo "Shared source asset changed"
  compile_all
  exit $?
fi

mdtx_changed="$(echo "$changed" | grep -E "^${SRC}/.+\.mdtx$" || true)"

if [ -z "$mdtx_changed" ]; then
  echo "No TLDR source changes"
  refresh_index
  exit $?
fi

status=0
while IFS= read -r f; do
  [ -z "$f" ] && continue
  if [ -f "$f" ]; then
    echo "Compiling $f"
    $COMPILE --once "$f" || status=1
  else
    stem="$(basename "$f" .mdtx)"
    echo "Removing output for deleted $f"
    rm -rf "research/tldr/${stem}"
  fi
done <<< "$mdtx_changed"

refresh_index || status=1
exit "$status"
