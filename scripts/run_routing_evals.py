#!/usr/bin/env python3
"""Run the routing eval suite and write a reproducible record of the result.

Every other eval in this repository assumes the right skill is already loaded
and measures the quality of the answer. This one measures the step before that:
given nothing but the ten `name` + `description` pairs and one user message,
does the routing layer load the right skill, the wrong one, or none at all?

The descriptions are read live from skills/*/SKILL.md at run time, never
copied, so the suite tracks whatever wording is actually on disk. No SKILL.md
is ever written to. Cases live in routing/cases.json.

Three numbers come out, and they are kept apart on purpose:

    correct-fire    on cases where a skill should load, the right one did
    mis-fire        a skill fired that should not have - the dangerous failure,
                    because a Braze question answered in Customer.io syntax
                    reads as confident and correct
    silent          nothing fired on a case where something should have - the
                    skill is invisible, which is merely worthless

Artifacts land in evals-runs/<name>/: routing.json holds every case with the
model's raw answer and the verdict; run.json holds provenance (git commit,
argv, model, CLI version, description-set hash) and the aggregate over every
case recorded in the directory, cumulative across invocations sharing --out.

A previously recorded case is reused only when its recorded hashes (prompt,
expectation, description set) and model match the current computation; stale
entries are re-run. An answer that fails strict validation - not JSON, no
"load" list, or a name not in the installed set - is recorded as a failure
with the raw output preserved and re-run on the next invocation; it is never
silently coerced into a verdict.

    python3 scripts/run_routing_evals.py
    python3 scripts/run_routing_evals.py --limit 5 --category confusable
    python3 scripts/run_routing_evals.py --out routing-v1   # resumable
    python3 scripts/run_routing_evals.py --dry-run          # print the plan

Requires the `claude` CLI on PATH and an authenticated session.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
RUNS = ROOT / "evals-runs"
CASES = ROOT / "routing" / "cases.json"
SCHEMA_VERSION = 2
DEFAULT_MODEL = "claude-sonnet-4-5"
CATEGORIES = ("named", "symptom", "code-only", "confusable", "out-of-scope")

ROUTER_INSTRUCTIONS = """\
You are the skill-routing layer of an AI assistant. The skills below are
installed. For each one you can see its name and its description and nothing
else - the same information the routing layer has at runtime.

Decide which skill or skills, if any, you would load to answer the user message
that follows.

Rules:
- Load a skill only if its own description says it covers this request.
- Loading the wrong platform's skill is worse than loading nothing: the answer
  comes back fluent and wrong.
- Loading nothing is a valid and often correct answer.
- If the message is genuinely ambiguous between platforms and you would ask the
  user which one they are on before loading anything, set "clarify" to true.

Return ONLY a JSON object, no prose and no code fence:

{"load": ["<skill-name>", ...], "clarify": true, "why": "<one sentence>"}

Use an empty list for "load nothing". Use only names from the list.
"""


class AnswerValidationError(Exception):
    """The router's answer cannot be trusted as a routing decision."""


def sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def git_provenance() -> dict:
    def run(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)

    head = run("rev-parse", "HEAD")
    status = run("status", "--porcelain")
    return {
        "git_commit": head.stdout.strip() if head.returncode == 0 else None,
        "git_dirty": bool(status.stdout.strip()) if status.returncode == 0 else None,
    }


def cli_version() -> str | None:
    if shutil.which("claude") is None:
        return None
    proc = subprocess.run(["claude", "--version"], capture_output=True, text=True)
    return proc.stdout.strip() or None


def load_skills() -> list[dict]:
    """Read name + description from each SKILL.md frontmatter. Read-only, live."""
    skills = []
    for path in sorted(ROOT.glob("skills/*/SKILL.md")):
        text = path.read_text(encoding="utf-8")
        match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
        if not match:
            raise RuntimeError(f"no YAML frontmatter in {path}")
        block = match.group(1)
        fields: dict[str, str] = {}
        key = None
        for line in block.split("\n"):
            head = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):\s?(.*)$", line)
            if head:
                key, value = head.group(1), head.group(2)
                fields[key] = value.strip()
            elif key and line.strip():
                fields[key] = (fields[key] + " " + line.strip()).strip()
        for field in ("name", "description"):
            if not fields.get(field):
                raise RuntimeError(f"{path} frontmatter has no {field}")
        if fields["name"] != path.parent.name:
            raise RuntimeError(
                f"{path} name {fields['name']!r} != directory {path.parent.name!r}")
        skills.append({"name": fields["name"],
                       "description": fields["description"].strip("'\"")})
    return skills


def description_set_hash(skills: list[dict]) -> str:
    return sha256_text(json.dumps(skills, sort_keys=True, ensure_ascii=False))


def skills_block(skills: list[dict]) -> str:
    entries = "\n".join(
        f"<skill>\n<name>{s['name']}</name>\n<description>{s['description']}</description>\n</skill>"
        for s in skills
    )
    return f"<available_skills>\n{entries}\n</available_skills>"


def case_hashes(case: dict) -> dict:
    """The identity of one case. If any of these change, a cached record is stale."""
    expectation = {"expect": case.get("expect"),
                   "accept": sorted(case.get("accept") or []),
                   "expect_clarify": bool(case.get("expect_clarify")),
                   "category": case["category"]}
    return {
        "prompt": sha256_text(case["prompt"]),
        "expectation": sha256_text(json.dumps(expectation, sort_keys=True)),
    }


def load_cases(suite: dict, valid: set[str]) -> list[dict]:
    """Validate the whole suite up front; a malformed case is a suite bug, not
    something to discover halfway through a paid run."""
    cases = suite.get("cases")
    if not isinstance(cases, list) or not cases:
        raise RuntimeError("routing/cases.json has no cases")
    seen: set[str] = set()
    for case in cases:
        cid = case.get("id")
        if not cid or not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", cid):
            raise RuntimeError(f"case id {cid!r} is not kebab-case")
        if cid in seen:
            raise RuntimeError(f"duplicate case id {cid!r}")
        seen.add(cid)
        if case.get("category") not in CATEGORIES:
            raise RuntimeError(f"case {cid}: unknown category {case.get('category')!r}")
        for field in ("prompt", "why"):
            if not isinstance(case.get(field), str) or not case[field].strip():
                raise RuntimeError(f"case {cid}: missing {field}")
        for slug in [case.get("expect")] + list(case.get("accept") or []):
            if slug is not None and slug not in valid:
                raise RuntimeError(f"case {cid} references unknown skill {slug!r}")
    return cases


def claude(prompt: str, model: str, timeout: int) -> str:
    proc = subprocess.run(
        ["claude", "-p", "--model", model, "--output-format", "text"],
        input=prompt, capture_output=True, text=True, timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"claude exited {proc.returncode}: {proc.stderr.strip()[:500]}")
    return proc.stdout.strip()


def parse_answer(raw: str, valid: set[str]) -> dict:
    """Strictly parse one router answer to a set of installed slugs or none.

    Requirements: a JSON object with a "load" list of strings, every one of
    them a name from the installed set, and "clarify" (when present) a boolean.
    Anything else raises AnswerValidationError - the caller records it as a
    failure with the raw output preserved; it is never coerced into a verdict.
    """
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        raise AnswerValidationError("no JSON object in router output")
    try:
        data = json.loads(raw[start:end + 1])
    except json.JSONDecodeError as exc:
        raise AnswerValidationError(f"router output is not valid JSON: {exc}") from exc
    if not isinstance(data, dict) or "load" not in data:
        raise AnswerValidationError("router output has no 'load' field")
    loaded = data["load"]
    if not isinstance(loaded, list) or not all(isinstance(x, str) for x in loaded):
        raise AnswerValidationError("'load' is not a list of strings")
    loaded = [x.strip() for x in loaded if x.strip()]
    unknown = sorted(set(loaded) - valid)
    if unknown:
        raise AnswerValidationError(f"'load' names skills that do not exist: {unknown}")
    clarify = data.get("clarify", False)
    if not isinstance(clarify, bool):
        raise AnswerValidationError("'clarify' is not a boolean")
    return {"load": sorted(set(loaded)), "clarify": clarify,
            "why": str(data.get("why", ""))[:500]}


def judge(case: dict, answer: dict) -> dict:
    """Compare one validated answer to the case's expectation.

    verdict is one of:
      correct         everything that fired was acceptable, and for cases with
                      an expected skill, at least one acceptable skill fired
      correct-silent  nothing fired on a case where nothing should have
      correct-clarify the case allows asking which platform, and that happened
      misfire         at least one skill fired that should not have
      silent          nothing fired (and no clarify where one would count) on a
                      case where something should have happened
    """
    expected = case.get("expect")
    accept = set(case.get("accept") or [])
    if expected:
        accept.add(expected)
    should_respond = bool(expected) or bool(case.get("expect_clarify"))
    loaded = set(answer["load"])
    wrong = sorted(loaded - accept)

    if wrong:
        verdict = "misfire"
    elif loaded:
        verdict = "correct"          # only acceptable skills fired
    elif answer["clarify"] and case.get("expect_clarify"):
        verdict = "correct-clarify"
    elif should_respond:
        verdict = "silent"
    else:
        verdict = "correct-silent"

    return {
        "verdict": verdict,
        "loaded": sorted(loaded),
        "wrong_skills": wrong,
        "clarify": answer["clarify"],
        "should_respond": should_respond,
    }


def aggregate(records: list[dict]) -> dict:
    scored = [r for r in records if "verdict" in r]

    def rates(rows: list[dict]) -> dict:
        should_fire = [r for r in rows if r.get("should_respond")]
        should_stay = [r for r in rows if not r.get("should_respond")]

        def pct(part: int, whole: int) -> float | None:
            return round(100 * part / whole, 1) if whole else None

        return {
            "correct_fire_pct": pct(
                sum(1 for r in should_fire if r["verdict"].startswith("correct")),
                len(should_fire)),
            "misfire_pct": pct(
                sum(1 for r in rows if r["verdict"] == "misfire"), len(rows)),
            "silent_pct": pct(
                sum(1 for r in should_fire if r["verdict"] == "silent"),
                len(should_fire)),
            "correct_silence_pct": pct(
                sum(1 for r in should_stay if r["verdict"] == "correct-silent"),
                len(should_stay)),
        }

    by_category: dict[str, dict] = {}
    for cat in CATEGORIES:
        rows = [r for r in scored if r.get("category") == cat]
        if rows:
            by_category[cat] = {"cases": len(rows), **rates(rows)}

    def macro(key: str) -> float | None:
        vals = [c[key] for c in by_category.values() if c.get(key) is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    return {
        "cases_scored": len(scored),
        "cases_failed": len(records) - len(scored),
        "micro": rates(scored),
        "macro_by_category": {k: macro(k) for k in
                              ("correct_fire_pct", "misfire_pct", "silent_pct")},
        "by_category": by_category,
        "counts": {
            "correct": sum(1 for r in scored if r["verdict"].startswith("correct")),
            "misfire": sum(1 for r in scored if r["verdict"] == "misfire"),
            "silent": sum(1 for r in scored if r["verdict"] == "silent"),
            "should_fire": sum(1 for r in scored if r.get("should_respond")),
            "should_stay_silent": sum(1 for r in scored if not r.get("should_respond")),
        },
        "misfired_cases": [
            {"case": r["case"], "expect": r.get("expect"), "fired": r["wrong_skills"]}
            for r in scored if r["verdict"] == "misfire"],
    }


def cache_check(prior: dict | None, hashes: dict, desc_hash: str,
                model: str) -> tuple[bool, str]:
    if prior is None:
        return False, "not recorded"
    if "verdict" not in prior:
        return False, "previously failed"
    if prior.get("hashes") != hashes:
        return False, "case content changed"
    if prior.get("description_set_hash") != desc_hash:
        return False, "skill descriptions changed"
    if prior.get("model") != model:
        return False, f"recorded model {prior.get('model')!r} != {model!r}"
    return True, ""


def build_manifest(out: pathlib.Path, suite_name: str, invocation: dict,
                   records: list[dict]) -> dict:
    prior: dict = {}
    manifest_path = out / "run.json"
    if manifest_path.exists():
        try:
            prior = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            prior = {}
    invocations = prior.get("invocations") if isinstance(prior.get("invocations"), list) else []
    rows = [{k: r.get(k) for k in ("case", "category", "expect", "verdict",
                                   "loaded", "wrong_skills", "error")
             if k in r}
            for r in sorted(records, key=lambda r: r.get("case", ""))]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "routing-evals",
        "created_utc": prior.get("created_utc", invocation["started_utc"]),
        "updated_utc": invocation["finished_utc"],
        "repo_version": (ROOT / "VERSION").read_text().strip(),
        "suite": suite_name,
        "model": invocation["model"],
        "cli": invocation["cli"],
        "settings": invocation["settings"],
        "description_set_hash": invocation["description_set_hash"],
        "provenance": {k: invocation[k] for k in ("git_commit", "git_dirty", "argv")},
        "invocations": invocations + [invocation],
        "cases": rows,
        "aggregate": aggregate(records),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=DEFAULT_MODEL, help="model acting as the router")
    ap.add_argument("--timeout", type=int, default=600, help="per-call timeout, seconds")
    ap.add_argument("--limit", type=int, default=None, help="run at most N cases (smoke test)")
    ap.add_argument("--category", action="append", choices=CATEGORIES,
                    help="limit to one category (repeatable)")
    ap.add_argument("--out", default=None,
                    help="write into this run directory instead of a new timestamped one; "
                         "cases already recorded there with matching hashes and model "
                         "are reused, everything stale is re-run")
    ap.add_argument("--dry-run", action="store_true", help="print the plan and exit")
    args = ap.parse_args()

    if not args.dry_run and shutil.which("claude") is None:
        print("the `claude` CLI is not on PATH", file=sys.stderr)
        return 2

    skills = load_skills()
    valid = {s["name"] for s in skills}
    desc_hash = description_set_hash(skills)
    suite = json.loads(CASES.read_text(encoding="utf-8"))
    all_cases = load_cases(suite, valid)
    cases = all_cases
    if args.category:
        cases = [c for c in cases if c["category"] in args.category]
    if args.limit:
        cases = cases[: args.limit]
    if not cases:
        print("no matching cases", file=sys.stderr)
        return 2

    print(f"{len(skills)} skill descriptions ({desc_hash[:19]}), "
          f"{len(cases)} case(s), {len(cases)} model calls, model {args.model}")
    if args.dry_run:
        for case in cases:
            print(f"  {case['id']} [{case['category']}] -> "
                  f"{case.get('expect') or ('clarify' if case.get('expect_clarify') else 'nothing')}")
        return 0

    started = dt.datetime.now(dt.timezone.utc)
    out = RUNS / (args.out or started.strftime("routing-%Y%m%dT%H%M%SZ"))
    out.mkdir(parents=True, exist_ok=True)
    artefact = out / "routing.json"

    recorded: dict[str, dict] = {}
    if artefact.exists():
        try:
            recorded = {c["case"]: c
                        for c in json.loads(artefact.read_text())["cases"]}
        except (json.JSONDecodeError, KeyError, TypeError):
            recorded = {}

    catalogue = skills_block(skills)
    for case in cases:
        hashes = case_hashes(case)
        cached, reason = cache_check(recorded.get(case["id"]), hashes,
                                     desc_hash, args.model)
        if cached:
            print(f"  {case['id']} [cached] {recorded[case['id']]['verdict']}")
            continue
        if case["id"] in recorded:
            print(f"  {case['id']} [stale: {reason}] re-running")

        record = {"case": case["id"], "category": case["category"],
                  "expect": case.get("expect"), "accept": case.get("accept") or [],
                  "expect_clarify": bool(case.get("expect_clarify")),
                  "why": case["why"], "hashes": hashes,
                  "description_set_hash": desc_hash, "model": args.model,
                  "recorded_utc": dt.datetime.now(dt.timezone.utc).isoformat()}
        prompt = (
            f"{ROUTER_INSTRUCTIONS}\n\n{catalogue}\n\n"
            f"<user_message>\n{case['prompt']}\n</user_message>\n"
        )
        try:
            raw = claude(prompt, args.model, args.timeout)
        except Exception as exc:                    # noqa: BLE001 - recorded, not raised
            record["error"] = f"router call failed: {exc}"
            recorded[case["id"]] = record
            print(f"  !! {case['id']} {record['error']}")
        else:
            record["raw"] = raw
            try:
                answer = parse_answer(raw, valid)
            except AnswerValidationError as exc:
                record["error"] = f"invalid answer: {exc}"
                print(f"  !! {case['id']} {record['error']}")
            else:
                record["answer"] = answer
                record.update(judge(case, answer))
                mark = {"correct": "ok", "correct-silent": "ok", "correct-clarify": "ok",
                        "misfire": "MISFIRE", "silent": "silent"}[record["verdict"]]
                detail = f" fired {record['loaded']}" if record["loaded"] else ""
                print(f"  {case['id']} [{case['category']}] {mark}{detail}")
            recorded[case["id"]] = record

        # Write after every case so an interrupted run loses nothing.
        artefact.write_text(json.dumps(
            {"schema_version": SCHEMA_VERSION, "suite": suite["suite"],
             "cases": list(recorded.values())},
            indent=2, ensure_ascii=False) + "\n")

    invocation = {
        "started_utc": started.isoformat(),
        "finished_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "argv": sys.argv,
        "model": args.model,
        "cli": cli_version(),
        "settings": {"output_format": "text", "timeout_seconds": args.timeout,
                     "limit": args.limit, "category": args.category,
                     "skills_presented": sorted(valid)},
        "description_set_hash": desc_hash,
        **git_provenance(),
    }
    # Cumulative: the manifest covers every case recorded in the directory,
    # whichever invocation recorded it.
    manifest = build_manifest(out, suite["suite"], invocation, list(recorded.values()))
    (out / "run.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")

    agg = manifest["aggregate"]
    micro, macro = agg["micro"], agg["macro_by_category"]
    print(f"\ncorrect-fire {micro['correct_fire_pct']}% (macro {macro['correct_fire_pct']}%)  "
          f"mis-fire {micro['misfire_pct']}% (macro {macro['misfire_pct']}%)  "
          f"silent-when-should-fire {micro['silent_pct']}% (macro {macro['silent_pct']}%)")
    for miss in agg["misfired_cases"]:
        print(f"  MISFIRE {miss['case']}: expected {miss['expect'] or 'nothing'}, "
              f"fired {', '.join(miss['fired'])}")
    if agg["cases_failed"]:
        print(f"{agg['cases_failed']} case(s) failed; "
              f"re-run with the same --out to retry just those")
    print(f"artifacts: {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
