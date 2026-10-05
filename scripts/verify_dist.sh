#!/usr/bin/env bash
# Post-build assertions on the archives in dist/.
#
# Everything here is a property a broken release would violate: the right number
# of archives, readable zip data, no symlinks or executables smuggled in, the
# licence present in each one, plugin folders that ship the same files, and
# checksums that match the files on disk.
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

# Expected-vs-actual inventory: every allowlisted source file must be in the
# archive, path for path. Catches an allowlist that silently drops something.
for a in "${archives[@]}"; do
  name="$(basename "$a" .skill)"
  src="$ROOT/skills/$name"
  listing="$(unzip -Z1 "$a")"
  while IFS= read -r -d '' f; do
    rel="${f#"$src/"}"
    grep -qxF "$name/$rel" <<<"$listing" || {
      echo "$a is missing source file $rel" >&2; exit 1; }
  done < <(find "$src" -type f \
      \( -name '*.md' -o -name '*.yaml' -o -name '*.json' \
         -o -name '*.png' -o -name '*.svg' -o -name '*.jpg' -o -name '*.webp' \) -print0)
done
echo "ok source inventory"

# Each Claude plugin folder must carry exactly what its .skill archive ships,
# file for file and byte for byte. scripts/sync_plugins.py writes those copies
# from its own allowlist; this catches the two allowlists drifting apart.
for a in "${archives[@]}"; do
  name="$(basename "$a" .skill)"
  copy="$ROOT/plugins/$name/skills"
  [ -d "$copy/$name" ] || { echo "plugins/$name/skills/$name is missing" >&2; exit 1; }
  want="$(unzip -Z1 "$a" | grep -v '/$' | LC_ALL=C sort)"
  have="$(cd "$copy" && find "$name" -type f | LC_ALL=C sort)"
  if [ "$want" != "$have" ]; then
    echo "plugins/$name does not ship the same files as $(basename "$a")" >&2
    diff <(echo "$want") <(echo "$have") >&2 || true
    exit 1
  fi
  while IFS= read -r f; do
    unzip -p "$a" "$f" | cmp -s - "$copy/$f" || {
      echo "plugins/$name/skills/$f differs from $(basename "$a")" >&2; exit 1; }
  done <<<"$want"
done
echo "ok plugin folders match the archives"

if command -v sha256sum >/dev/null 2>&1; then SHACMD="sha256sum"; else SHACMD="shasum -a 256"; fi
( cd "$DIST" && $SHACMD -c SHA256SUMS >/dev/null ) || {
  echo "checksums in dist/SHA256SUMS do not match" >&2; exit 1; }
echo "ok SHA256SUMS"

echo
echo "${#archives[@]} archive(s) verified"
