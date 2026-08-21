#!/usr/bin/env bash
# Package every skill in skills/ as a .skill archive (a zip) into dist/.
#
# A .skill archive is what you upload to Claude or ChatGPT and what gets attached
# to a GitHub release. Each archive must be self-contained and installable on its
# own, so this script copies the repository LICENSE into every one of them.
#
# Files are staged through an explicit allowlist rather than zipped in place, so a
# stray file in a skill directory cannot silently end up in a published archive.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST="$ROOT/dist"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

VERSION="$(tr -d '[:space:]' < "$ROOT/VERSION")"
[ -n "$VERSION" ] || { echo "VERSION file is empty" >&2; exit 1; }

# A symlink inside a package is both a portability problem and a path-traversal
# risk once the archive is unpacked somewhere else. Refuse to build rather than
# publish one.
if find "$ROOT/skills" -type l -print | grep -q .; then
  echo "refusing to build: symlink(s) found under skills/" >&2
  find "$ROOT/skills" -type l -print >&2
  exit 1
fi

rm -rf "$DIST" && mkdir -p "$DIST"
built=0

for skill in "$ROOT"/skills/*/; do
  name="$(basename "$skill")"
  [ -f "$skill/SKILL.md" ] || { echo "skip $name (no SKILL.md)"; continue; }

  pkg="$STAGE/$name"
  mkdir -p "$pkg"

  # Explicit allowlist. Anything not named here is not shipped.
  install -m 0644 "$skill/SKILL.md" "$pkg/SKILL.md"
  install -m 0644 "$ROOT/LICENSE"   "$pkg/LICENSE"

  for sub in references agents evals; do
    [ -d "$skill/$sub" ] || continue
    mkdir -p "$pkg/$sub"
    find "$skill/$sub" -maxdepth 1 -type f \
      \( -name '*.md' -o -name '*.yaml' -o -name '*.json' \) \
      -exec install -m 0644 {} "$pkg/$sub/" \;
  done

  ( cd "$STAGE" && zip -qrX "$DIST/$name.skill" "$name" )
  built=$((built + 1))
  echo "built dist/$name.skill"
done

expected="$(find "$ROOT"/skills -maxdepth 2 -name SKILL.md | wc -l | tr -d ' ')"
if [ "$built" -ne "$expected" ]; then
  echo "expected $expected archives, built $built" >&2
  exit 1
fi

( cd "$DIST" && sha256sum ./*.skill > SHA256SUMS )
echo
echo "$built archive(s) for v$VERSION in dist/, checksums in dist/SHA256SUMS"
