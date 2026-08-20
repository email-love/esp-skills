#!/usr/bin/env python3
"""Check every skill's SKILL.md frontmatter against the Agent Skills spec.

Both Claude and ChatGPT read `name` and `description` from this frontmatter, and the
description is the entire triggering mechanism — a malformed one means the skill
silently never fires. Cheap to check, expensive to miss.
"""
import pathlib, re, sys

MAX_DESC = 1024
root = pathlib.Path(__file__).resolve().parent.parent
errors = []

for skill_md in sorted(root.glob("skills/*/SKILL.md")):
    rel = skill_md.relative_to(root)
    text = skill_md.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        errors.append(f"{rel}: no YAML frontmatter")
        continue
    fm = m.group(1)

    name = re.search(r"^name:\s*(.+)$", fm, re.M)
    desc = re.search(r"^description:\s*(.+)$", fm, re.M)

    if not name:
        errors.append(f"{rel}: missing `name`")
    elif name.group(1).strip() != skill_md.parent.name:
        errors.append(f"{rel}: `name` ({name.group(1).strip()}) != folder ({skill_md.parent.name})")

    if not desc:
        errors.append(f"{rel}: missing `description`")
    else:
        d = desc.group(1).strip()
        if len(d) > MAX_DESC:
            errors.append(f"{rel}: description is {len(d)} chars, max {MAX_DESC}")
        # An unquoted YAML scalar breaks on ': ' — this is the most common authoring bug.
        if not (d.startswith(('"', "'"))) and ": " in d:
            errors.append(f"{rel}: unquoted description contains ': ' and will fail YAML parsing")

    for ref in re.findall(r"`(references/[^`]+\.md)`", text):
        if not (skill_md.parent / ref).exists():
            errors.append(f"{rel}: references a missing file: {ref}")

    print(f"checked {rel}")

if errors:
    print("\nFAILED:", file=sys.stderr)
    for e in errors:
        print("  " + e, file=sys.stderr)
    sys.exit(1)
print("\nAll skills valid.")
