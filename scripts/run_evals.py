#!/usr/bin/env python3
"""Run the eval suites and write a reproducible record of the result.

Every case runs twice - once with the skill's content in context, once without -
and a third model call grades each response against that case's assertions. The
point of the paired run is that a score on its own says very little; the delta
between the two arms is what tells you whether the skill is carrying its weight.

Everything needed to reproduce or dispute a published number is written to
evals-runs/<name>/: run.json holds provenance (git commit, argv, model, grader
model, CLI version, settings) and the aggregate over every case recorded in the
directory, and one <skill>.json per suite holds every case with both raw
responses, the raw grader output, and the grader's per-assertion verdicts.

run.json is cumulative: when several invocations share an --out directory (one
per suite, say), each invocation rebuilds the manifest from every per-skill
artifact present, merged by (skill, case). No invocation ever narrows the
manifest to just its own suite.

A previously recorded case is reused only when its recorded hashes (skill
context, prompt, assertions) and model settings (model, grader model, context
mode) match the current computation. Anything stale is re-run, not silently
reused. Cases whose grader response failed strict validation are recorded as
grader failures - raw output preserved, excluded from averages, re-run on the
next invocation - never scored as zero.

Two averages are reported, and they are not the same number: the
assertion-weighted micro average (total assertions met / total assertions) and
the equal-case macro average (mean of per-case percentages).

Context modes (--context-mode):
  full          SKILL.md plus every file in references/, concatenated. This is
                everything the skill ships, so it measures an upper bound - a
                runtime that discloses progressively would rarely have all of it
                loaded. Recorded as "full-context-upper-bound".
  skillmd-only  SKILL.md alone, closer to what a runtime loads before any Read.
                Recorded as "skillmd-only".

    python3 scripts/run_evals.py                 # every skill
    python3 scripts/run_evals.py --skill klaviyo-django
    python3 scripts/run_evals.py --dry-run       # print the plan, call nothing

Requires the `claude` CLI on PATH and an authenticated session.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
RUNS = ROOT / "evals-runs"
SCHEMA_VERSION = 2
DEFAULT_MODEL = "claude-sonnet-4-5"
CONTEXT_MODES = {"full": "full-context-upper-bound", "skillmd-only": "skillmd-only"}
ARMS = ("with_skill", "baseline")

GRADER_INSTRUCTIONS = """\
You are grading one response against a list of assertions.

Judge only what the response actually says. An assertion is met only if the
response supports it; absence is not support, and plausible-sounding filler is
not support. Do not reward a response for being well written.

The assertions are numbered from 0. Return ONLY a JSON object, no prose and no
code fence. It must contain exactly one verdict per assertion, keyed by its
number, with "met" a JSON boolean and "evidence" a non-empty string:

{"verdicts": [{"i": 0, "met": true, "evidence": "<short quote from the response, or why it fails>"}]}

The runner reattaches each assertion's text from the suite itself, so do not
echo the assertion text back.
"""


class GraderValidationError(Exception):
    """The grader returned something that cannot be trusted as a score."""


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


def skill_context(skill_dir: pathlib.Path, mode: str) -> str:
    """What we place in context for the with-skill arm, read live from disk.

    "full" is SKILL.md plus every references/*.md - an upper bound on what a
    progressive-disclosure runtime would have loaded. "skillmd-only" is just
    SKILL.md, closer to the pre-Read state at runtime.
    """
    parts = [f"### {skill_dir.name}/SKILL.md\n\n{(skill_dir / 'SKILL.md').read_text()}"]
    if mode == "full":
        for ref in sorted((skill_dir / "references").glob("*.md")):
            parts.append(f"### {skill_dir.name}/references/{ref.name}\n\n{ref.read_text()}")
    return "\n\n".join(parts)


def case_hashes(context: str, case: dict) -> dict:
    """The identity of one case's computation. If any of these change, a cached
    record is stale and must be re-run."""
    return {
        "skill_context": sha256_text(context),
        "prompt": sha256_text(case["prompt"]),
        "assertions": sha256_text(json.dumps(case["assertions"], ensure_ascii=False)),
    }


def claude(prompt: str, model: str, timeout: int) -> str:
    proc = subprocess.run(
        ["claude", "-p", "--model", model, "--output-format", "text"],
        input=prompt, capture_output=True, text=True, timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"claude exited {proc.returncode}: {proc.stderr.strip()[:500]}")
    return proc.stdout.strip()


def grader_prompt(response: str, assertions: list[str]) -> str:
    numbered = [{"i": i, "assertion": a} for i, a in enumerate(assertions)]
    return (GRADER_INSTRUCTIONS + "\nAssertions:\n"
            + json.dumps(numbered, indent=2, ensure_ascii=False)
            + "\n\nResponse to grade:\n<response>\n" + response + "\n</response>\n")


def align_verdicts(assertions: list[str], raw: str) -> list[dict]:
    """Strictly validate one grader response against the assertions it was given.

    Requirements: parseable JSON, exactly one verdict per assertion, an
    unambiguous index mapping (each index 0..n-1 exactly once), `met` strictly
    boolean, `evidence` a non-empty string. The verbatim assertion text is
    reattached from the suite by the runner, so grader transcription can never
    corrupt it. Legacy text-keyed responses (an "assertion" field instead of
    "i") are accepted when they map verbatim and unambiguously.
    Anything else raises GraderValidationError.
    """
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n", "", text)
        text = re.sub(r"\n```$", "", text.rstrip())
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Tolerate prose around the object ("Sure, here you go: {...}") — the
        # payload itself is still validated strictly below.
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise GraderValidationError("grader output is not valid JSON")
        try:
            data = json.loads(text[start:end + 1])
        except json.JSONDecodeError as exc:
            raise GraderValidationError(f"grader output is not valid JSON: {exc}")
    verdicts = data.get("verdicts") if isinstance(data, dict) else data
    if not isinstance(verdicts, list):
        raise GraderValidationError("grader output has no verdict list")
    if len(verdicts) != len(assertions):
        raise GraderValidationError(
            f"expected {len(assertions)} verdicts, got {len(verdicts)}")

    cleaned: list[dict | None] = [None] * len(assertions)
    legacy: list[dict] = []
    for i, v in enumerate(verdicts):
        if not isinstance(v, dict):
            raise GraderValidationError(f"verdict {i} is not an object")
        met, evidence = v.get("met"), v.get("evidence")
        if not isinstance(met, bool):
            raise GraderValidationError(f"verdict {i} has non-boolean met")
        if not isinstance(evidence, str) or not evidence.strip():
            raise GraderValidationError(f"verdict {i} has empty evidence")
        idx = v.get("i")
        if isinstance(idx, int):
            if not (0 <= idx < len(assertions)):
                raise GraderValidationError(f"verdict {i} has out-of-range index {idx}")
            if cleaned[idx] is not None:
                raise GraderValidationError(f"duplicate verdict for index {idx}")
            cleaned[idx] = {"assertion": assertions[idx], "met": met, "evidence": evidence}
        elif isinstance(v.get("assertion"), str):
            legacy.append({"assertion": v["assertion"], "met": met, "evidence": evidence})
        else:
            raise GraderValidationError(f"verdict {i} has neither an index nor assertion text")

    if legacy and any(c is not None for c in cleaned):
        raise GraderValidationError("grader mixed indexed and text-keyed verdicts")
    if legacy:
        if [v["assertion"] for v in legacy] == assertions:
            return legacy
        if len(set(assertions)) == len(assertions):
            by_text = {v["assertion"]: v for v in legacy}
            if len(by_text) == len(legacy) and set(by_text) == set(assertions):
                return [by_text[a] for a in assertions]
        raise GraderValidationError("verdict assertion texts do not match the assertions verbatim")
    if any(c is None for c in cleaned):
        raise GraderValidationError("missing verdict for at least one assertion index")
    return [c for c in cleaned if c is not None]


def arm_complete(arm: dict | None) -> bool:
    return isinstance(arm, dict) and "response" in arm and "verdicts" in arm


def cache_check(prior: dict | None, hashes: dict, model: str,
                grader_model: str, context_mode: str) -> tuple[bool, str]:
    """A recorded case is reusable only when it is complete and its recorded
    hashes and model settings match the current computation."""
    if prior is None:
        return False, "not recorded"
    for arm in ARMS:
        if not arm_complete(prior.get(arm)):
            return False, f"{arm} incomplete or previously failed"
    if prior.get("hashes") != hashes:
        return False, "content hashes changed"
    if prior.get("model") != model:
        return False, f"recorded model {prior.get('model')!r} != {model!r}"
    if prior.get("grader_model") != grader_model:
        return False, f"recorded grader model {prior.get('grader_model')!r} != {grader_model!r}"
    if prior.get("context_mode") != context_mode:
        return False, f"recorded context mode {prior.get('context_mode')!r} != {context_mode!r}"
    return True, ""


def arm_summary(arm: dict | None) -> dict:
    if arm is None:
        return {"error": "not attempted"}
    if arm_complete(arm):
        v = arm["verdicts"]
        met = sum(1 for x in v if x.get("met") is True)
        return {"met": met, "total": len(v),
                "pct": round(100 * met / len(v), 1) if v else 0.0}
    if "grader_failure" in arm:
        return {"grader_failure": arm["grader_failure"]}
    return {"error": arm.get("error", "unknown failure")}


def case_row(skill: str, record: dict) -> dict:
    row = {"skill": skill, "case": record.get("case"),
           "category": record.get("category")}
    for key in ("context_mode", "model", "grader_model", "hashes"):
        if key in record:
            row[key] = record[key]
    for arm in ARMS:
        row[arm] = arm_summary(record.get(arm))
    return row


def collect_artifacts(out: pathlib.Path) -> list[dict]:
    """Every per-skill artifact in the run directory, whichever invocation wrote it."""
    artifacts = []
    for path in sorted(out.glob("*.json")):
        if path.name in ("run.json", "routing.json"):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if isinstance(data, dict) and "skill" in data and isinstance(data.get("cases"), list):
            artifacts.append(data)
    return artifacts


def aggregate_rows(rows: list[dict]) -> dict:
    agg: dict = {"cases_total": len(rows)}
    for arm in ARMS:
        scored = [r[arm] for r in rows if "pct" in r.get(arm, {})]
        grader_failed = sum(1 for r in rows if "grader_failure" in r.get(arm, {}))
        errored = sum(1 for r in rows if "error" in r.get(arm, {}))
        met = sum(s["met"] for s in scored)
        total = sum(s["total"] for s in scored)
        agg[arm] = {
            "cases_scored": len(scored),
            "grader_failures": grader_failed,
            "errors": errored,
            "assertions_met": met,
            "assertions_total": total,
            "assertion_weighted_micro_pct":
                round(100 * met / total, 1) if total else None,
            "equal_case_macro_pct":
                round(sum(s["pct"] for s in scored) / len(scored), 1) if scored else None,
        }
    return agg


def build_manifest(out: pathlib.Path, invocation: dict) -> dict:
    """Rebuild run.json from every artifact in the directory, merged by
    (skill, case). Cumulative across invocations that share --out: the current
    invocation is appended to the invocation history, never allowed to narrow
    the manifest to its own suite."""
    prior: dict = {}
    manifest_path = out / "run.json"
    if manifest_path.exists():
        try:
            prior = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            prior = {}

    merged: dict[tuple[str, str], dict] = {}
    for artifact in collect_artifacts(out):
        for record in artifact["cases"]:
            merged[(artifact["skill"], record.get("case", ""))] = \
                case_row(artifact["skill"], record)
    rows = [merged[key] for key in sorted(merged)]

    invocations = prior.get("invocations") if isinstance(prior.get("invocations"), list) else []
    invocations = invocations + [invocation]

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "content-evals",
        "created_utc": prior.get("created_utc", invocation["started_utc"]),
        "updated_utc": invocation["finished_utc"],
        "repo_version": (ROOT / "VERSION").read_text().strip(),
        "context_mode": invocation["context_mode"],
        "model": invocation["model"],
        "grader_model": invocation["grader_model"],
        "cli": invocation["cli"],
        "settings": invocation["settings"],
        "provenance": {k: invocation[k] for k in ("git_commit", "git_dirty", "argv")},
        "invocations": invocations,
        "cases": rows,
        "aggregate": aggregate_rows(rows),
    }


def run_arm(prompt: str, assertions: list[str], model: str,
            grader_model: str, timeout: int) -> dict:
    """One arm of one case: response call, grader call, strict validation.
    Every outcome preserves what raw material exists; nothing is scored zero
    for a harness failure."""
    try:
        response = claude(prompt, model, timeout)
    except Exception as exc:                        # noqa: BLE001 - recorded, not raised
        return {"error": f"response call failed: {exc}"}
    try:
        raw = claude(grader_prompt(response, assertions), grader_model, timeout)
    except Exception as exc:                        # noqa: BLE001 - recorded, not raised
        return {"response": response, "error": f"grader call failed: {exc}"}
    try:
        verdicts = align_verdicts(assertions, raw)
    except GraderValidationError as exc:
        return {"response": response, "raw_grader_output": raw,
                "grader_failure": str(exc)}
    return {"response": response, "raw_grader_output": raw, "verdicts": verdicts}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skill", action="append", help="limit to one skill (repeatable)")
    ap.add_argument("--model", default=DEFAULT_MODEL, help="model for both arms")
    ap.add_argument("--grader-model", default=None, help="defaults to --model")
    ap.add_argument("--timeout", type=int, default=600, help="per-call timeout, seconds")
    ap.add_argument("--limit", type=int, default=None,
                    help="run at most N cases per suite (smoke test)")
    ap.add_argument("--context-mode", choices=sorted(CONTEXT_MODES), default="full",
                    help="'full' = SKILL.md + all references (upper bound); "
                         "'skillmd-only' = SKILL.md alone")
    ap.add_argument("--out", default=None,
                    help="write into this run directory instead of a new timestamped one; "
                         "cases already recorded there with matching hashes and model "
                         "settings are reused, everything stale is re-run")
    ap.add_argument("--dry-run", action="store_true", help="print the plan and exit")
    args = ap.parse_args()
    grader_model = args.grader_model or args.model
    context_mode = CONTEXT_MODES[args.context_mode]

    if not args.dry_run and shutil.which("claude") is None:
        print("the `claude` CLI is not on PATH", file=sys.stderr)
        return 2

    suites = []
    for path in sorted(ROOT.glob("skills/*/evals/evals.json")):
        raw_bytes = path.read_bytes()
        data = json.loads(raw_bytes)
        if args.skill and data["skill"] not in args.skill:
            continue
        if args.limit:
            data = dict(data, cases=data["cases"][: args.limit])
        suites.append((path.parent.parent, data,
                       "sha256:" + hashlib.sha256(raw_bytes).hexdigest()))

    if not suites:
        print("no matching eval suites", file=sys.stderr)
        return 2

    total_cases = sum(len(d["cases"]) for _, d, _ in suites)
    print(f"{len(suites)} suite(s), {total_cases} case(s), up to {total_cases * 3} model calls")
    print(f"model {args.model}  grader {grader_model}  context mode {context_mode}")
    if args.dry_run:
        for skill_dir, data, _ in suites:
            context = skill_context(skill_dir, args.context_mode)
            for case in data["cases"]:
                hashes = case_hashes(context, case)
                print(f"  {data['skill']}/{case['id']} [{case['category']}] "
                      f"{len(case['assertions'])} assertions  "
                      f"prompt {hashes['prompt'][:19]}")
        return 0

    started = dt.datetime.now(dt.timezone.utc)
    out = RUNS / (args.out or started.strftime("%Y%m%dT%H%M%SZ"))
    out.mkdir(parents=True, exist_ok=True)

    for skill_dir, data, suite_hash in suites:
        # Read live at run time: skill content may change between invocations,
        # and the hashes recorded per case capture exactly what was sent.
        context = skill_context(skill_dir, args.context_mode)
        artefact = out / f"{data['skill']}.json"
        recorded: dict[str, dict] = {}
        if artefact.exists():
            try:
                recorded = {c["case"]: c
                            for c in json.loads(artefact.read_text())["cases"]}
            except (json.JSONDecodeError, KeyError, TypeError):
                recorded = {}

        for case in data["cases"]:
            hashes = case_hashes(context, case)
            valid, reason = cache_check(recorded.get(case["id"]), hashes,
                                        args.model, grader_model, context_mode)
            if valid:
                print(f"  {data['skill']}/{case['id']} [cached]")
                continue
            if case["id"] in recorded:
                print(f"  {data['skill']}/{case['id']} [stale: {reason}] re-running")

            record = {
                "case": case["id"], "category": case["category"],
                "hashes": hashes, "suite_hash": suite_hash,
                "model": args.model, "grader_model": grader_model,
                "context_mode": context_mode,
                "settings": {"output_format": "text", "timeout_seconds": args.timeout},
                "recorded_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            }
            for arm, prompt in (
                ("with_skill",
                 f"Use the following reference material to answer.\n\n{context}\n\n"
                 f"---\n\nUser:\n\n{case['prompt']}"),
                ("baseline", case["prompt"]),
            ):
                record[arm] = run_arm(prompt, case["assertions"], args.model,
                                      grader_model, args.timeout)
                summary = arm_summary(record[arm])
                if "pct" in summary:
                    print(f"  {data['skill']}/{case['id']} [{arm}] "
                          f"{summary['met']}/{summary['total']}")
                elif "grader_failure" in summary:
                    print(f"  !! {data['skill']}/{case['id']} [{arm}] "
                          f"grader failure: {summary['grader_failure']}")
                else:
                    print(f"  !! {data['skill']}/{case['id']} [{arm}] {summary['error']}")

            recorded[case["id"]] = record
            # Write after every case so an interrupted run loses nothing.
            artefact.write_text(json.dumps(
                {"schema_version": SCHEMA_VERSION, "skill": data["skill"],
                 "cases": list(recorded.values())},
                indent=2, ensure_ascii=False) + "\n")

    invocation = {
        "started_utc": started.isoformat(),
        "finished_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "argv": sys.argv,
        "model": args.model,
        "grader_model": grader_model,
        "context_mode": context_mode,
        "cli": cli_version(),
        "settings": {"output_format": "text", "timeout_seconds": args.timeout,
                     "limit": args.limit},
        **git_provenance(),
    }
    manifest = build_manifest(out, invocation)
    (out / "run.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")

    agg = manifest["aggregate"]
    for arm in ARMS:
        a = agg[arm]
        print(f"\n{arm}: micro (assertion-weighted) {a['assertion_weighted_micro_pct']}%  "
              f"macro (equal-case) {a['equal_case_macro_pct']}%  "
              f"[{a['cases_scored']}/{agg['cases_total']} cases scored, "
              f"{a['grader_failures']} grader failure(s), {a['errors']} error(s)]")
    print(f"\nartifacts: {out.relative_to(ROOT)}")
    failures = sum(agg[a]["grader_failures"] + agg[a]["errors"] for a in ARMS)
    if failures:
        print(f"{failures} arm(s) failed; re-run with the same --out to retry just those")
    return 0


if __name__ == "__main__":
    sys.exit(main())
