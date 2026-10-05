#!/usr/bin/env bash
# Package every skill in skills/ as a .skill archive (a zip) into dist/.
#
# A .skill archive is what you upload to Claude or ChatGPT and what gets attached
# to a GitHub release. Each archive must be self-contained and installable on its
# own, so this script copies the repository LICENSE into every one of them.
#
# Files are staged through an explicit allowlist rather than zipped in place, so a
# stray file in a skill directory cannot silently end up in a published archive.
#
# Builds are DETERMINISTIC: staged files are stamped with one fixed timestamp,
# given fixed permissions, added in sorted path order, and stripped of extra zip
# attributes, and zip ignores any default options set in the environment. The
# same source tree therefore produces a byte-identical archive on any machine with
# Info-ZIP zip 3.0 (the zip macOS and Ubuntu ship), so a published release asset
# can be independently re-derived and checksum-compared.
set -euo pipefail

# One fixed timestamp for reproducibility. touch -t reads it as local time and zip
# stores local time, so every archive records 2026-01-01 00:00 in any timezone.
STAMP="202601010000"

# zip adds the contents of these variables to its command line. A stray -9 in
# either would change the bytes of every archive.
unset ZIP ZIPOPT

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

  # Recursive: nested reference material and future assets/icons must not
  # silently vanish from a published archive because of a depth cap.
  for sub in references agents evals assets; do
    [ -d "$skill/$sub" ] || continue
    ( cd "$skill" && find "$sub" -type f \
        \( -name '*.md' -o -name '*.yaml' -o -name '*.json' \
           -o -name '*.png' -o -name '*.svg' -o -name '*.jpg' -o -name '*.webp' \) \
        -print0 ) | while IFS= read -r -d '' f; do
      mkdir -p "$pkg/$(dirname "$f")"
      install -m 0644 "$skill/$f" "$pkg/$f"
    done
  done

  # Anything under those directories NOT matched by the allowlist is an error,
  # not a silent omission.
  unshipped="$(cd "$skill" && find references agents evals assets -type f \
      ! -name '*.md' ! -name '*.yaml' ! -name '*.json' \
      ! -name '*.png' ! -name '*.svg' ! -name '*.jpg' ! -name '*.webp' 2>/dev/null || true)"
  if [ -n "$unshipped" ]; then
    echo "refusing to build $name: files present that the allowlist would drop:" >&2
    echo "$unshipped" >&2
    exit 1
  fi

  # Deterministic: fixed modes and mtime, sorted entry order, no extra attributes.
  # install already gave every file 0644; the directories come from mkdir -p and
  # would otherwise carry the builder's umask (0775 under umask 002, say).
  find "$pkg" -type d -exec chmod 0755 {} +
  find "$pkg" -exec touch -t "$STAMP" {} +
  ( cd "$STAGE" && find "$name" \( -type f -o -type d \) | LC_ALL=C sort \
      | zip -qX "$DIST/$name.skill" -@ )
  built=$((built + 1))
  echo "built dist/$name.skill"
done

expected="$(find "$ROOT"/skills -maxdepth 2 -name SKILL.md | wc -l | tr -d ' ')"
if [ "$built" -ne "$expected" ]; then
  echo "expected $expected archives, built $built" >&2
  exit 1
fi

# sha256sum on Linux, shasum -a 256 on macOS.
if command -v sha256sum >/dev/null 2>&1; then
  ( cd "$DIST" && sha256sum ./*.skill > SHA256SUMS )
else
  ( cd "$DIST" && shasum -a 256 ./*.skill > SHA256SUMS )
fi
echo
echo "$built archive(s) for v$VERSION in dist/, checksums in dist/SHA256SUMS"
