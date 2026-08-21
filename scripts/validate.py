#!/usr/bin/env python3
"""Validate the repository before it can be packaged or released.

Every check here exists because the failure it catches is silent. A malformed
description means a skill never triggers and nobody sees an error. A version that
disagrees between the changelog and the marketplace manifest installs the wrong
thing. A leftover TODO ships as product copy. None of these break a build on
their own, so the build has to be taught to care.

    python3 scripts/validate.py
    python3 scripts/validate.py --list   # show what is checked, run nothing
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import stat
import sys

try:
    import yaml
except ImportError:  # pragma: no cover - the message is the point
    print("PyYAML is required: python3 -m pip install pyyaml==6.0.2", file=sys.stderr)
    sys.exit(2)

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKILLS = sorted(p for p in (ROOT / "skills").iterdir() if (p / "SKILL.md").exists())

# Agent Skills open standard.
MAX_NAME = 64
MAX_DESCRIPTION = 1024
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

# OpenAI presentation metadata.
INTERFACE_KEYS = {"display_name", "short_description", "icon_small", "icon_large",
                  "brand_color", "default_prompt"}
INTERFACE_REQUIRED = {"display_name", "short_description"}
POLICY_KEYS = {"allow_implicit_invocation"}
SHORT_DESC_RANGE = (25, 64)
HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")

EVAL_CATEGORIES = {"authoring", "debugging", "adversarial"}
MIN_ASSERTIONS = 5

# Anything that looks like a credential. Deliberately noisy rather than clever:
# a false positive costs one line of review, a false negative ships a key.
SECRET_PATTERNS = [
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"), "OpenAI-style secret key"),
    (re.compile(r"\bpk_(live|test)_[A-Za-z0-9]{10,}"), "publishable key"),
    (re.compile(r"\bsa_live_[A-Za-z0-9]{10,}"), "Customer.io service-account token"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"), "GitHub token"),
    (re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}"), "Slack token"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS access key id"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key"),
]
PLACEHOLDER_RE = re.compile(r"\bTODO\b|\bFIXME\b|\bXXX\b|<PLACEHOLDER>", re.I)

# HTTP is only acceptable where the scheme is the subject of the sentence.
HTTP_RE = re.compile(r"http://[^\s`\"'<>)\]]+")
HTTP_ALLOW = {
    "http://www.w3.org",     # XML namespace URIs, which are identifiers, not links
}

errors: list[str] = []
notes: list[str] = []


def rel(p: pathlib.Path) -> str:
    return str(p.relative_to(ROOT))


def frontmatter(path: pathlib.Path) -> dict | None:
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        errors.append(f"{rel(path)}: no YAML frontmatter")
        return None
    try:
        data = yaml.safe_load(m.group(1))
    except yaml.YAMLError as exc:
        errors.append(f"{rel(path)}: frontmatter is not valid YAML - {exc}")
        return None
    if not isinstance(data, dict):
        errors.append(f"{rel(path)}: frontmatter is not a mapping")
        return None
    return data


def check_skill_frontmatter() -> None:
    for skill in SKILLS:
        md = skill / "SKILL.md"
        fm = frontmatter(md)
        if fm is None:
            continue

        name = fm.get("name")
        if not name:
            errors.append(f"{rel(md)}: missing `name`")
        else:
            if name != skill.name:
                errors.append(f"{rel(md)}: name `{name}` != directory `{skill.name}`")
            if len(name) > MAX_NAME:
                errors.append(f"{rel(md)}: name is {len(name)} chars, max {MAX_NAME}")
            if not NAME_RE.match(str(name)):
                errors.append(f"{rel(md)}: name `{name}` is not lowercase-hyphen-separated")

        desc = fm.get("description")
        if not desc:
            errors.append(f"{rel(md)}: missing `description`")
        elif not isinstance(desc, str):
            errors.append(f"{rel(md)}: description must be a string")
        elif len(desc) > MAX_DESCRIPTION:
            errors.append(f"{rel(md)}: description is {len(desc)} chars, max {MAX_DESCRIPTION}")

        unknown = set(fm) - {"name", "description", "license", "allowed-tools", "metadata"}
        if unknown:
            notes.append(f"{rel(md)}: non-standard frontmatter keys {sorted(unknown)}")


def check_references() -> None:
    """Referenced files must exist, and must live inside the skill's own package."""
    for skill in SKILLS:
        for md in sorted(skill.rglob("*.md")):
            text = md.read_text(encoding="utf-8")
            for ref in re.findall(r"`((?:references|agents|evals)/[^`\s]+)`", text):
                target = (skill / ref).resolve()
                if not target.exists():
                    errors.append(f"{rel(md)}: references a missing file `{ref}`")
                elif skill.resolve() not in target.parents:
                    errors.append(f"{rel(md)}: `{ref}` resolves outside the skill package")

            for link in re.findall(r"\]\((?!https?:|mailto:|#)([^)]+)\)", text):
                target = (md.parent / link.split("#")[0]).resolve()
                if not target.exists():
                    errors.append(f"{rel(md)}: broken relative link `{link}`")


def check_openai_metadata() -> None:
    for skill in SKILLS:
        path = skill / "agents" / "openai.yaml"
        if not path.exists():
            errors.append(f"{skill.name}: missing agents/openai.yaml")
            continue
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            errors.append(f"{rel(path)}: not valid YAML - {exc}")
            continue

        unknown = set(data) - {"interface", "policy"}
        if unknown:
            errors.append(f"{rel(path)}: unknown top-level keys {sorted(unknown)}")

        interface = data.get("interface") or {}
        missing = INTERFACE_REQUIRED - set(interface)
        if missing:
            errors.append(f"{rel(path)}: interface is missing {sorted(missing)}")
        for key in set(interface) - INTERFACE_KEYS:
            errors.append(f"{rel(path)}: unknown interface key `{key}`")

        short = interface.get("short_description", "")
        lo, hi = SHORT_DESC_RANGE
        if short and not (lo <= len(short) <= hi):
            errors.append(f"{rel(path)}: short_description is {len(short)} chars, want {lo}-{hi}")

        colour = interface.get("brand_color")
        if colour is not None and not HEX_RE.match(str(colour)):
            errors.append(f"{rel(path)}: brand_color `{colour}` is not a #RRGGBB hex value")

        prompt = interface.get("default_prompt")
        if prompt and f"${skill.name}" not in prompt:
            errors.append(f"{rel(path)}: default_prompt must reference `${skill.name}`")

        for key in set(data.get("policy") or {}) - POLICY_KEYS:
            errors.append(f"{rel(path)}: unknown policy key `{key}`")


def check_evals() -> None:
    for skill in SKILLS:
        path = skill / "evals" / "evals.json"
        if not path.exists():
            errors.append(f"{skill.name}: missing evals/evals.json")
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"{rel(path)}: not valid JSON - {exc}")
            continue

        if data.get("schema_version") != 1:
            errors.append(f"{rel(path)}: schema_version must be 1")
        if data.get("skill") != skill.name:
            errors.append(f"{rel(path)}: skill `{data.get('skill')}` != directory `{skill.name}`")

        cases = data.get("cases")
        if not isinstance(cases, list) or not cases:
            errors.append(f"{rel(path)}: `cases` must be a non-empty list")
            continue

        seen: set[str] = set()
        categories: set[str] = set()
        for case in cases:
            cid = case.get("id", "<no id>")
            where = f"{rel(path)}[{cid}]"
            if not NAME_RE.match(str(cid)):
                errors.append(f"{where}: id is not a kebab-case slug")
            if cid in seen:
                errors.append(f"{where}: duplicate id")
            seen.add(cid)

            category = case.get("category")
            if category not in EVAL_CATEGORIES:
                errors.append(f"{where}: category must be one of {sorted(EVAL_CATEGORIES)}")
            else:
                categories.add(category)

            for field in ("prompt", "expected_output"):
                if not str(case.get(field, "")).strip():
                    errors.append(f"{where}: `{field}` is empty")

            assertions = case.get("assertions")
            if not isinstance(assertions, list) or len(assertions) < MIN_ASSERTIONS:
                errors.append(f"{where}: needs at least {MIN_ASSERTIONS} assertions")
            elif any(not str(a).strip() for a in assertions):
                errors.append(f"{where}: has an empty assertion")

        if "adversarial" not in categories:
            errors.append(f"{rel(path)}: no adversarial case - every suite needs at least one")


def check_marketplace_and_version() -> None:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if not re.match(r"^\d+\.\d+\.\d+$", version):
        errors.append(f"VERSION: `{version}` is not semver")

    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    if not re.search(rf"^## \[{re.escape(version)}\]", changelog, re.M):
        errors.append(f"CHANGELOG.md: no `## [{version}]` section for the current VERSION")

    path = ROOT / ".claude-plugin" / "marketplace.json"
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"{rel(path)}: not valid JSON - {exc}")
        return

    for key in ("name", "owner", "plugins"):
        if key not in manifest:
            errors.append(f"{rel(path)}: missing `{key}`")

    listed = set()
    for plugin in manifest.get("plugins", []):
        pname = plugin.get("name", "<unnamed>")
        listed.add(pname)
        for key in ("name", "source", "description", "version"):
            if not plugin.get(key):
                errors.append(f"{rel(path)}[{pname}]: missing `{key}`")
        if plugin.get("version") != version:
            errors.append(
                f"{rel(path)}[{pname}]: version {plugin.get('version')} != VERSION {version}")
        source = plugin.get("source", "")
        if source and not (ROOT / source.lstrip("./")).is_dir():
            errors.append(f"{rel(path)}[{pname}]: source `{source}` is not a directory")

    on_disk = {s.name for s in SKILLS}
    for missing in sorted(on_disk - listed):
        errors.append(f"{rel(path)}: skill `{missing}` exists on disk but is not listed")
    for extra in sorted(listed - on_disk):
        errors.append(f"{rel(path)}: lists `{extra}`, which has no skill directory")


def check_hygiene() -> None:
    """Symlinks, executables, secrets, placeholders, and plain-HTTP examples."""
    for path in sorted((ROOT / "skills").rglob("*")):
        if path.is_symlink():
            errors.append(f"{rel(path)}: symlinks are not allowed inside skills/")
            continue
        if not path.is_file():
            continue
        if path.stat().st_mode & stat.S_IXUSR:
            errors.append(f"{rel(path)}: unexpected executable bit inside skills/")

    scan = list((ROOT / "skills").rglob("*.md")) + list((ROOT / "skills").rglob("*.json")) \
        + list((ROOT / "skills").rglob("*.yaml")) + list((ROOT / "shared").rglob("*")) \
        + [ROOT / "README.md", ROOT / "CONTRIBUTING.md", ROOT / "SECURITY.md", ROOT / "CHANGELOG.md"]

    for path in sorted(p for p in scan if p.is_file()):
        text = path.read_text(encoding="utf-8", errors="replace")

        # A committed credential is unacceptable anywhere, fixture or not.
        for pattern, label in SECRET_PATTERNS:
            if pattern.search(text):
                errors.append(f"{rel(path)}: looks like a committed {label}")

        # Eval suites are deliberately realistic broken and hostile input, and
        # their expected outputs and assertions quote it back. A TODO or an
        # http:// link in a fixture is the test, not unfinished product copy.
        # The placeholder and HTTPS checks exist to catch the latter, so they
        # stop here; the credential scan above deliberately does not.
        if path.name == "evals.json":
            continue

        # A changelog's job is to describe what the repository used to contain,
        # including the placeholders that were removed. Quoting one is not
        # shipping one.
        if path.name == "CHANGELOG.md":
            for m in HTTP_RE.finditer(text):
                if not any(m.group(0).startswith(a) for a in HTTP_ALLOW):
                    line = text[: m.start()].count("\n") + 1
                    errors.append(f"{rel(path)}:{line}: plain-HTTP URL - use HTTPS")
            continue

        for m in PLACEHOLDER_RE.finditer(text):
            line = text[: m.start()].count("\n") + 1
            errors.append(f"{rel(path)}:{line}: unresolved placeholder `{m.group(0)}`")
        for m in HTTP_RE.finditer(text):
            if any(m.group(0).startswith(a) for a in HTTP_ALLOW):
                continue
            line = text[: m.start()].count("\n") + 1
            errors.append(f"{rel(path)}:{line}: plain-HTTP URL `{m.group(0)}` - use HTTPS")


def check_workflow_expectations() -> None:
    """Workflows must not depend on an executable bit, and must not over-grant."""
    for script in ("scripts/build.sh", "scripts/verify_dist.sh"):
        if not (ROOT / script).exists():
            errors.append(f"{script}: missing")

    for wf in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        text = wf.read_text(encoding="utf-8")
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            errors.append(f"{rel(wf)}: not valid YAML - {exc}")
            continue

        for m in re.finditer(r"run:\s*\.?/?scripts/(\S+\.sh)", text):
            if "bash scripts/" not in text.split(m.group(0))[0][-40:]:
                errors.append(f"{rel(wf)}: invoke `{m.group(1)}` through bash, "
                              "not by relying on the executable bit")

        for m in re.finditer(r"uses:\s*([\w.-]+/[\w.-]+)@(\S+)", text):
            if not re.fullmatch(r"[0-9a-f]{40}", m.group(2)):
                errors.append(
                    f"{rel(wf)}: `{m.group(1)}` is pinned to `{m.group(2)}` - "
                    "use a full 40-character commit SHA")

        top = data.get("permissions")
        if top != {"contents": "read"}:
            errors.append(f"{rel(wf)}: top-level permissions must be `contents: read`")

        writers = [name for name, job in (data.get("jobs") or {}).items()
                   if (job.get("permissions") or {}).get("contents") == "write"]
        if wf.name != "release.yml" and writers:
            errors.append(f"{rel(wf)}: job(s) {writers} request write access outside release.yml")
        for name in writers:
            job = data["jobs"][name]
            if not str(job.get("if", "")).strip():
                errors.append(f"{rel(wf)}: job `{name}` has write access with no `if:` guard")


CHECKS = [
    ("SKILL.md frontmatter", check_skill_frontmatter),
    ("reference and link targets", check_references),
    ("OpenAI presentation metadata", check_openai_metadata),
    ("eval suites", check_evals),
    ("marketplace manifest and version agreement", check_marketplace_and_version),
    ("hygiene: symlinks, exec bits, secrets, placeholders, HTTPS", check_hygiene),
    ("workflow permissions and pinning", check_workflow_expectations),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="list the checks and exit")
    args = ap.parse_args()

    if args.list:
        for label, _ in CHECKS:
            print(f"  {label}")
        print("  shared-block drift (scripts/sync_shared.py --check, run separately)")
        return 0

    print(f"validating {len(SKILLS)} skill(s)\n")
    for label, fn in CHECKS:
        before = len(errors)
        fn()
        status = "FAIL" if len(errors) > before else "ok"
        print(f"  [{status:4}] {label}")

    if notes:
        print("\nNotes:")
        for n in notes:
            print(f"  {n}")

    if errors:
        print(f"\nFAILED with {len(errors)} problem(s):", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return 1

    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
