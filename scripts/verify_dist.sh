#!/usr/bin/env bash
# Post-build assertions on the archives in dist/.
#
# Everything here is a property a broken release would violate: the right number
# of archives, readable zip data, no symlinks or executables smuggled in, the
# licence present in each one, and checksums that match the files on disk.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST="$ROOT/dist"
expected="$(find "$ROOT"/skills -maxdepth 2 -name SKILL.md | wc -l | tr -d ' ')"

shopt -s nullglob
archives=("$DIST"/*.skill)
if [ "${#archives[@]}" -ne "$expected" ]; then
  echo "expected $expected .skill archives in dist/, found ${#archives[@]}" >&2
  exit 1
fi

for a in "${archives[@]}"; do
  name="$(basename "$a" .skill)"

  unzip -tq "$a" >/dev/null || { echo "corrupt archive: $a" >&2; exit 1; }

  listing="$(unzip -Z1 "$a")"
  for required in "$name/SKILL.md" "$name/LICENSE"; do
    grep -qxF "$required" <<<"$listing" || {
      echo "$a is missing $required" >&2; exit 1; }
  done

  # Nothing may escape the skill's own directory.
  if grep -vq "^$name/" <<<"$listing"; then
    echo "$a contains entries outside $name/" >&2
    grep -v "^$name/" <<<"$listing" >&2
    exit 1
  fi

  # Long-form listing: reject symlinks (l) and any executable bit.
  if unzip -Z "$a" | grep -Eq '^[lL]'; then
    echo "$a contains a symlink" >&2; exit 1
  fi
  if unzip -Z "$a" | grep -Eq '^-.{0,8}[x]'; then
    echo "$a contains an executable file" >&2; exit 1
  fi

  echo "ok $(basename "$a")"
done

( cd "$DIST" && sha256sum -c SHA256SUMS >/dev/null ) || {
  echo "checksums in dist/SHA256SUMS do not match" >&2; exit 1; }
echo "ok SHA256SUMS"

echo
echo "${#archives[@]} archive(s) verified"
