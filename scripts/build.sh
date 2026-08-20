#!/usr/bin/env bash
# Package every skill in skills/ as a .skill file (a zip) into dist/.
# .skill files are what you upload to Claude.ai / ChatGPT and attach to a GitHub release.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST="$ROOT/dist"
rm -rf "$DIST" && mkdir -p "$DIST"

for skill in "$ROOT"/skills/*/; do
  name="$(basename "$skill")"
  [ -f "$skill/SKILL.md" ] || { echo "skip $name (no SKILL.md)"; continue; }
  ( cd "$ROOT/skills" && zip -qr "$DIST/$name.skill" "$name" \
      -x '*.DS_Store' -x '*/evals/*' -x '*/__pycache__/*' )
  echo "built dist/$name.skill"
done
