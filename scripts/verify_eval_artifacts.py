#!/usr/bin/env python3
"""Offline verification of recorded eval artifacts. Stdlib only, no model calls.

Everything a published number rests on is re-derived from the raw material in
the run directory and compared against what the manifest claims:

  * inventory   - the manifest's case list agrees exactly with the per-skill
                  artifacts on disk: no missing, extra, or duplicate records.
  * parsing     - every stored raw grader / router output re-parses, and the
                  re-parsed verdicts equal the stored verdicts.
  * aggregates  - the stored aggregate is recomputed exactly from the stored
                  per-case verdicts (schema-2 runs are recomputed under
                  schema-2 rounding, schema-3 under exact-fraction rounding).
  * identity    - every record in one run shares one model / grader /
                  context-mode / contract identity.
  * provenance  - the run records an input commit; in --require-current mode
                  the commit must be clean, reachable from HEAD, and the case
                  ids must match the suites currently on disk (stale, extra,
                  duplicate, and orphan records are all failures; a case the
                  suite defines but the run lacks is reported as MISSING
                  coverage, distinct from a case the manifest marks deferred).
  * docs        - the numbers EVALS.md quotes for the run (CLI version, case
                  and assertion counts, model) agree with the artifacts.

Two modes, deliberately separate:

  --historical      Verify the named historical runs (default:
                    baseline-v1.4.1 and routing-v1.4.1) with the LEGACY
                    compatibility verdict parser (text-keyed grader output was
                    valid at the time). Known historical caveats - dirty
                    provenance, mixed grader-contract generations - are
                    REPORTED, not failed; those runs are preserved as history.
  --require-current Verify the run directories named by evals-runs/current.json
                    under the strict live rules: indexed verdicts only, clean
                    reachable provenance, exact suite agreement, doc agreement.
                    A missing pointer file is a failure - there is no current
                    run to stand behind.

    python3 scripts/verify_eval_artifacts.py --historical
    python3 scripts/verify_eval_artifacts.py --require-current
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
RUNS = ROOT / "evals-runs"
SCRIPTS = pathlib.Path(__file__).resolve().parent
HISTORICAL_CONTENT = "baseline-v1.4.1"
HISTORICAL_ROUTING = "routing-v1.4.1"

FAILURES: list[str] = []
NOTES: list[str] = []


def fail(msg: str) -> None:
    FAILURES.append(msg)
    print(f"  FAIL  {msg}")


def note(msg: str) -> None:
    NOTES.append(msg)
    print(f"  note  {msg}")


def ok(msg: str) -> None:
    print(f"  ok    {msg}")


def load_module(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rt = load_module("run_routing_evals")
ev = load_module("run_evals")


# ---------------------------------------------------------------------------
# The named historical compatibility verifier. Live runs accept only indexed
# verdicts (see run_evals.align_verdicts); this parser additionally accepts
# the text-keyed form that was valid when the historical runs were recorded.
# It exists here, under this name, and nowhere in the live runner.
# ---------------------------------------------------------------------------

def historical_align_verdicts(assertions: list[str], raw: str) -> list[dict]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n", "", text)
        text = re.sub(r"\n```$", "", text.rstrip())
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise ev.GraderValidationError("grader output is not valid JSON")
        data = json.loads(text[start:end + 1])
    verdicts = data.get("verdicts") if isinstance(data, dict) else data
    if not isinstance(verdicts, list) or len(verdicts) != len(assertions):
        raise ev.GraderValidationError("verdict list missing or wrong length")

    cleaned: list[dict | None] = [None] * len(assertions)
    legacy: list[dict] = []
    for i, v in enumerate(verdicts):
        if not isinstance(v, dict):
            raise ev.GraderValidationError(f"verdict {i} is not an object")
        met, evidence = v.get("met"), v.get("evidence")
        if not isinstance(met, bool):
            raise ev.GraderValidationError(f"verdict {i} has non-boolean met")
        if not isinstance(evidence, str) or not evidence.strip():
            raise ev.GraderValidationError(f"verdict {i} has empty evidence")
        idx = v.get("i")
        if type(idx) is int and 0 <= idx < len(assertions) and cleaned[idx] is None:
            cleaned[idx] = {"assertion": assertions[idx], "met": met, "evidence": evidence}
        elif isinstance(v.get("assertion"), str):
            legacy.append({"assertion": v["assertion"], "met": met, "evidence": evidence})
        else:
            raise ev.GraderValidationError(f"verdict {i} unmappable")
    if legacy and any(c is not None for c in cleaned):
        raise ev.GraderValidationError("mixed indexed and text-keyed verdicts")
    if legacy:
        if [v["assertion"] for v in legacy] == assertions:
            return legacy
        by_text = {v["assertion"]: v for v in legacy}
        if len(set(assertions)) == len(assertions) and set(by_text) == set(assertions) \
                and len(by_text) == len(legacy):
            return [by_text[a] for a in assertions]
        raise ev.GraderValidationError("text-keyed verdicts do not match assertions")
    if any(c is None for c in cleaned):
        raise ev.GraderValidationError("missing verdict for an assertion index")
    return [c for c in cleaned if c is not None]


# ---------------------------------------------------------------------------
# Aggregate recomputation, faithful to each schema's rounding.
# ---------------------------------------------------------------------------

def recompute_content_aggregate(rows: list[dict], schema: int) -> dict:
    agg: dict = {"cases_total": len(rows)}
    for arm in ("with_skill", "baseline"):
        scored = [r[arm] for r in rows if "pct" in r.get(arm, {})]
        grader_failed = sum(1 for r in rows if "grader_failure" in r.get(arm, {}))
        errored = sum(1 for r in rows if "error" in r.get(arm, {}))
        met = sum(s["met"] for s in scored)
        total = sum(s["total"] for s in scored)
        if schema >= 3:
            fractions = [s["met"] / s["total"] for s in scored if s["total"]]
            macro = round(100 * sum(fractions) / len(fractions), 1) if fractions else None
        else:
            macro = round(sum(s["pct"] for s in scored) / len(scored), 1) if scored else None
        agg[arm] = {
            "cases_scored": len(scored),
            "grader_failures": grader_failed,
            "errors": errored,
            "assertions_met": met,
            "assertions_total": total,
            "assertion_weighted_micro_pct": round(100 * met / total, 1) if total else None,
            "equal_case_macro_pct": macro,
        }
    return agg


def summarize_arm(record_arm: dict | None) -> dict:
    if not isinstance(record_arm, dict):
        return {"error": "not attempted"}
    if "response" in record_arm and "verdicts" in record_arm:
        v = record_arm["verdicts"]
        met = sum(1 for x in v if x.get("met") is True)
        return {"met": met, "total": len(v),
                "pct": round(100 * met / len(v), 1) if v else 0.0}
    if "grader_failure" in record_arm:
        return {"grader_failure": record_arm["grader_failure"]}
    return {"error": record_arm.get("error", "unknown failure")}


# ---------------------------------------------------------------------------
# Content-run verification
# ---------------------------------------------------------------------------

def verify_content_run(run_dir: pathlib.Path, strict: bool) -> None:
    print(f"content run: {run_dir.relative_to(ROOT)}")
    manifest_path = run_dir / "run.json"
    if not manifest_path.exists():
        fail(f"{run_dir.name}: run.json missing")
        return
    manifest = json.loads(manifest_path.read_text())
    schema = manifest.get("schema_version", 2)
    verifier = ev.align_verdicts if strict else historical_align_verdicts

    # Inventory: manifest rows == artifact records, keyed by (skill, case).
    artifact_records: dict[tuple[str, str], dict] = {}
    for path in sorted(run_dir.glob("*.json")):
        if path.name in ("run.json", "routing.json"):
            continue
        data = json.loads(path.read_text())
        if not (isinstance(data, dict) and "skill" in data):
            continue
        for record in data["cases"]:
            key = (data["skill"], record.get("case", ""))
            if key in artifact_records:
                fail(f"duplicate record {key}")
            artifact_records[key] = record
    manifest_keys = {(r["skill"], r["case"]) for r in manifest.get("cases", [])}
    if len(manifest_keys) != len(manifest.get("cases", [])):
        fail("manifest contains duplicate (skill, case) rows")
    if manifest_keys != set(artifact_records):
        missing = sorted(set(artifact_records) - manifest_keys)
        extra = sorted(manifest_keys - set(artifact_records))
        fail(f"inventory mismatch: manifest missing {missing}, extra {extra}")
    else:
        ok(f"inventory: {len(artifact_records)} case records agree with the manifest")

    # Parsing: every stored raw grader output re-parses to the stored verdicts.
    reparsed, parse_failures = 0, 0
    for key, record in sorted(artifact_records.items()):
        for arm in ("with_skill", "baseline"):
            arm_rec = record.get(arm)
            if not isinstance(arm_rec, dict) or "verdicts" not in arm_rec:
                continue
            assertions = [v["assertion"] for v in arm_rec["verdicts"]]
            raw = arm_rec.get("raw_grader_output")
            if raw is None:
                fail(f"{key} [{arm}]: verdicts without raw grader output")
                parse_failures += 1
                continue
            try:
                again = verifier(assertions, raw)
            except ev.GraderValidationError as exc:
                fail(f"{key} [{arm}]: raw grader output no longer parses: {exc}")
                parse_failures += 1
                continue
            if [(v["met"], v["assertion"]) for v in again] != \
                    [(v["met"], v["assertion"]) for v in arm_rec["verdicts"]]:
                fail(f"{key} [{arm}]: re-parsed verdicts differ from stored verdicts")
                parse_failures += 1
            else:
                reparsed += 1
    if not parse_failures:
        ok(f"parsing: {reparsed} stored grader outputs re-parse to the stored verdicts")

    # Aggregates: recompute exactly from stored verdicts.
    rows = []
    for (skill, case), record in sorted(artifact_records.items()):
        row = {"skill": skill, "case": case}
        for arm in ("with_skill", "baseline"):
            row[arm] = summarize_arm(record.get(arm))
        rows.append(row)
    recomputed = recompute_content_aggregate(rows, schema)
    stored = manifest.get("aggregate", {})
    stored_cmp = {"cases_total": stored.get("cases_total")}
    for arm in ("with_skill", "baseline"):
        stored_cmp[arm] = {k: stored.get(arm, {}).get(k) for k in recomputed[arm]}
    if stored_cmp != recomputed:
        fail(f"aggregate mismatch:\n    stored     {stored_cmp}\n    recomputed {recomputed}")
    else:
        ok("aggregate: stored numbers recompute exactly from the stored verdicts")

    # Identity: one model / grader / context mode per run.
    identities = {(r.get("model"), r.get("grader_model"), r.get("context_mode"),
                   json.dumps(r.get("contracts"), sort_keys=True))
                  for r in artifact_records.values()}
    if len(identities) > 1:
        msg = f"mixed identities in one run: {sorted(identities)!r}"
        if strict:
            fail(msg)
        else:
            note(f"historical caveat: {msg}")
    else:
        ok("identity: one model/grader/context/contract identity across the run")

    # Errors and failures.
    errors = sum(1 for r in rows for arm in ("with_skill", "baseline")
                 if "error" in r[arm] or "grader_failure" in r[arm])
    if errors:
        msg = f"{errors} arm(s) errored or failed grading"
        fail(msg) if strict else note(f"historical caveat: {msg}")
    else:
        ok("failures: none")

    # Provenance.
    prov = manifest.get("provenance", {})
    if not prov.get("git_commit"):
        fail("provenance records no input commit")
    elif strict:
        if prov.get("git_dirty") is not False:
            fail(f"provenance is dirty: {prov}")
        else:
            reachable = subprocess.run(
                ["git", "merge-base", "--is-ancestor", prov["git_commit"], "HEAD"],
                cwd=ROOT, capture_output=True).returncode == 0
            if not reachable:
                fail(f"input commit {prov['git_commit'][:12]} is not an ancestor of HEAD")
            else:
                ok("provenance: clean input commit, reachable from HEAD")
    else:
        if prov.get("git_dirty"):
            note("historical caveat: provenance recorded a dirty working tree")
        ok(f"provenance: input commit {str(prov.get('git_commit'))[:12]} recorded")

    # Strict-only: suite agreement (stale / extra / orphan / missing-vs-deferred).
    if strict:
        current: dict[str, set[str]] = {}
        for path in sorted(ROOT.glob("skills/*/evals/evals.json")):
            data = json.loads(path.read_text())
            current[data["skill"]] = {c["id"] for c in data["cases"]}
        run_by_skill: dict[str, set[str]] = {}
        for skill, case in artifact_records:
            run_by_skill.setdefault(skill, set()).add(case)
        deferred = set(map(tuple, manifest.get("deferred", [])))
        for skill, ids in sorted(current.items()):
            got = run_by_skill.get(skill, set())
            stale = got - ids
            missing = ids - got
            if stale:
                fail(f"{skill}: run contains stale cases not in the suite: {sorted(stale)}")
            truly_missing = {m for m in missing if (skill, m) not in deferred}
            if truly_missing:
                fail(f"{skill}: MISSING coverage (not marked deferred): {sorted(truly_missing)}")
            for m in missing - truly_missing:
                note(f"{skill}/{m}: coverage explicitly deferred in the manifest")
        orphans = set(run_by_skill) - set(current)
        if orphans:
            fail(f"orphan skill artifacts for skills not in the repo: {sorted(orphans)}")
        if not any(f.startswith(s) for s in current for f in FAILURES):
            ok("suite agreement: no stale, orphan, or silently missing cases")


# ---------------------------------------------------------------------------
# Routing-run verification
# ---------------------------------------------------------------------------

def verify_routing_run(run_dir: pathlib.Path, strict: bool) -> None:
    print(f"routing run: {run_dir.relative_to(ROOT)}")
    manifest_path = run_dir / "run.json"
    artefact_path = run_dir / "routing.json"
    if not manifest_path.exists() or not artefact_path.exists():
        fail(f"{run_dir.name}: run.json or routing.json missing")
        return
    manifest = json.loads(manifest_path.read_text())
    records = json.loads(artefact_path.read_text())["cases"]

    valid: set[str] = set()
    settings = manifest.get("settings", {})
    if isinstance(settings.get("skills_presented"), list):
        valid = set(settings["skills_presented"])
    if not valid:
        valid = {p.parent.name for p in ROOT.glob("skills/*/SKILL.md")}
        note("run did not record skills_presented; validating against current skills")

    # Inventory.
    ids = [r.get("case") for r in records]
    if len(ids) != len(set(ids)):
        fail("routing.json contains duplicate case records")
    manifest_ids = [r.get("case") for r in manifest.get("cases", [])]
    if sorted(ids) != sorted(manifest_ids):
        fail("manifest case list does not match routing.json")
    else:
        ok(f"inventory: {len(ids)} routing records agree with the manifest")

    # Parsing + verdict recomputation.
    parse_failures = 0
    for record in records:
        if "verdict" not in record:
            continue
        raw = record.get("raw")
        if raw is None:
            fail(f"{record.get('case')}: verdict without raw router output")
            parse_failures += 1
            continue
        try:
            answer = rt.parse_answer(raw, valid)
        except rt.AnswerValidationError as exc:
            fail(f"{record.get('case')}: raw router output no longer parses: {exc}")
            parse_failures += 1
            continue
        case_spec = {"expect": record.get("expect"),
                     "accept": record.get("accept") or [],
                     "expect_clarify": record.get("expect_clarify"),
                     "category": record.get("category")}
        again = rt.judge(case_spec, answer)
        if again["verdict"] != record["verdict"]:
            fail(f"{record.get('case')}: recomputed verdict {again['verdict']!r} "
                 f"!= stored {record['verdict']!r}")
            parse_failures += 1
    if not parse_failures:
        ok("parsing: every stored router answer re-parses to the stored verdict")

    # Aggregate recomputation.
    recomputed = rt.aggregate(records)
    stored = manifest.get("aggregate", {})
    if json.loads(json.dumps(recomputed)) != stored:
        fail("routing aggregate does not recompute from the stored records")
    else:
        ok("aggregate: stored numbers recompute exactly from the stored records")

    # Failures.
    failed = [r for r in records if "verdict" not in r]
    if failed:
        msg = f"{len(failed)} routing case(s) recorded as failures"
        fail(msg) if strict else note(f"historical caveat: {msg}")
    else:
        ok("failures: none")

    # Provenance + strict suite agreement.
    prov = manifest.get("provenance", {})
    if not prov.get("git_commit"):
        fail("provenance records no input commit")
    elif strict and prov.get("git_dirty") is not False:
        fail(f"provenance is dirty: {prov}")
    elif strict:
        ok("provenance: clean input commit recorded")
    else:
        if prov.get("git_dirty"):
            note("historical caveat: provenance recorded a dirty working tree")
        ok(f"provenance: input commit {str(prov.get('git_commit'))[:12]} recorded")

    if strict:
        suite_ids = {c["id"] for c in
                     json.loads((ROOT / "routing" / "cases.json").read_text())["cases"]}
        got = set(ids)
        if got - suite_ids:
            fail(f"routing run contains stale cases: {sorted(got - suite_ids)}")
        if suite_ids - got:
            fail(f"routing run MISSING coverage: {sorted(suite_ids - got)}")
        if got == suite_ids:
            ok("suite agreement: routing cases match routing/cases.json exactly")


# ---------------------------------------------------------------------------
# Documentation agreement
# ---------------------------------------------------------------------------

def verify_docs(content_run: pathlib.Path) -> None:
    """The metadata EVALS.md quotes for the run must agree with the artifacts."""
    print("documentation agreement: EVALS.md")
    manifest = json.loads((content_run / "run.json").read_text())
    docs = (ROOT / "EVALS.md").read_text()
    cli = manifest.get("cli") or ""
    cli_short = cli.split()[0] if cli else ""
    checks = [
        (cli_short, f"CLI version {cli_short!r} from run.json appears in EVALS.md"),
        (str(manifest["aggregate"]["cases_total"]), "case count appears in EVALS.md"),
        (manifest.get("model", ""), "model name appears in EVALS.md"),
    ]
    for needle, label in checks:
        if needle and needle in docs:
            ok(label)
        elif needle:
            fail(f"documentation drift: {label.replace(' appears in EVALS.md', '')} "
                 f"({needle!r}) not found in EVALS.md")


# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--historical", action="store_true",
                      help="verify the preserved historical runs with the "
                           "legacy-compatibility verdict parser")
    mode.add_argument("--require-current", action="store_true",
                      help="verify the runs named by evals-runs/current.json "
                           "under strict live rules")
    ap.add_argument("--content-run", default=None,
                    help="override the content run directory name")
    ap.add_argument("--routing-run", default=None,
                    help="override the routing run directory name")
    args = ap.parse_args()

    if args.require_current:
        pointer = RUNS / "current.json"
        if not pointer.exists():
            print("FAIL: evals-runs/current.json does not exist - there is no "
                  "current run to verify. Produce a clean successor run first.",
                  file=sys.stderr)
            return 1
        current = json.loads(pointer.read_text())
        content = RUNS / (args.content_run or current["content"])
        routing = RUNS / (args.routing_run or current["routing"])
        verify_content_run(content, strict=True)
        verify_routing_run(routing, strict=True)
        verify_docs(content)
    else:
        content = RUNS / (args.content_run or HISTORICAL_CONTENT)
        routing = RUNS / (args.routing_run or HISTORICAL_ROUTING)
        verify_content_run(content, strict=False)
        verify_routing_run(routing, strict=False)
        verify_docs(content)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s), {len(NOTES)} note(s)")
        return 1
    print(f"all checks passed ({len(NOTES)} historical note(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
