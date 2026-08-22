#!/usr/bin/env python3
"""Self-test for the eval harnesses. No model calls, no network, stdlib only.

Exercises the pieces that guard result integrity: strict grader validation,
cache invalidation, the cumulative run.json merge, both averages, and the
routing answer validation and verdict logic.

    python3 scripts/test_eval_harness.py
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import tempfile

SCRIPTS = pathlib.Path(__file__).resolve().parent


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ev = load("run_evals")
rt = load("run_routing_evals")

CHECKS = 0


def check(condition: bool, label: str) -> None:
    global CHECKS
    CHECKS += 1
    if not condition:
        print(f"FAIL: {label}")
        sys.exit(1)
    print(f"  ok  {label}")


def fails_validation(fn, *args, exc=Exception) -> bool:
    try:
        fn(*args)
    except exc:
        return True
    return False


# ---------------------------------------------------------------- grader validation

A = ["First assertion.", "Second assertion."]


def raw_verdicts(verdicts) -> str:
    return json.dumps({"verdicts": verdicts})


good = raw_verdicts([
    {"assertion": A[0], "met": True, "evidence": "quote"},
    {"assertion": A[1], "met": False, "evidence": "missing"},
])
out = ev.align_verdicts(A, "Sure, here you go:\n" + good)
check([v["met"] for v in out] == [True, False], "grader: valid response accepted")
check([v["assertion"] for v in out] == A, "grader: assertion text preserved verbatim")

reordered = raw_verdicts([
    {"assertion": A[1], "met": False, "evidence": "missing"},
    {"assertion": A[0], "met": True, "evidence": "quote"},
])
out = ev.align_verdicts(A, reordered)
check([v["assertion"] for v in out] == A and out[0]["met"] is True,
      "grader: unique-text permutation mapped back to suite order")

GV = ev.GraderValidationError
check(fails_validation(ev.align_verdicts, A, "no json here", exc=GV),
      "grader: non-JSON rejected")
check(fails_validation(ev.align_verdicts, A, raw_verdicts(
    [{"assertion": A[0], "met": True, "evidence": "q"}]), exc=GV),
      "grader: wrong verdict count rejected")
check(fails_validation(ev.align_verdicts, A, raw_verdicts([
    {"assertion": A[0], "met": "yes", "evidence": "q"},
    {"assertion": A[1], "met": False, "evidence": "q"}]), exc=GV),
      "grader: non-boolean met rejected")
check(fails_validation(ev.align_verdicts, A, raw_verdicts([
    {"assertion": A[0], "met": True, "evidence": ""},
    {"assertion": A[1], "met": False, "evidence": "q"}]), exc=GV),
      "grader: empty evidence rejected")
check(fails_validation(ev.align_verdicts, A, raw_verdicts([
    {"assertion": "Paraphrased assertion.", "met": True, "evidence": "q"},
    {"assertion": A[1], "met": False, "evidence": "q"}]), exc=GV),
      "grader: paraphrased assertion text rejected")
dupes = ["Same text.", "Same text."]
check(fails_validation(ev.align_verdicts, dupes, raw_verdicts([
    {"assertion": "Same text.", "met": True, "evidence": "q"},
    {"assertion": "Other text.", "met": False, "evidence": "q"}]), exc=GV),
      "grader: ambiguous mapping over duplicate assertions rejected")

# ---------------------------------------------------------------- content cache

HASHES = {"skill_context": "sha256:aaa", "prompt": "sha256:bbb", "assertions": "sha256:ccc"}
COMPLETE_ARM = {"response": "r", "raw_grader_output": "g",
                "verdicts": [{"assertion": A[0], "met": True, "evidence": "q"}]}
PRIOR = {"case": "c1", "hashes": dict(HASHES), "model": "m1", "grader_model": "m1",
         "context_mode": "full-context-upper-bound",
         "with_skill": dict(COMPLETE_ARM), "baseline": dict(COMPLETE_ARM)}


def content_cached(prior, **over) -> bool:
    params = {"hashes": HASHES, "model": "m1", "grader_model": "m1",
              "context_mode": "full-context-upper-bound"}
    params.update(over)
    ok, _ = ev.cache_check(prior, params["hashes"], params["model"],
                           params["grader_model"], params["context_mode"])
    return ok


check(content_cached(PRIOR), "cache: complete matching record reused")
check(not content_cached(None), "cache: unrecorded case runs")
check(not content_cached(PRIOR, hashes={**HASHES, "prompt": "sha256:zzz"}),
      "cache: changed prompt hash re-runs")
check(not content_cached(PRIOR, hashes={**HASHES, "skill_context": "sha256:zzz"}),
      "cache: changed skill context hash re-runs")
check(not content_cached(PRIOR, model="m2"), "cache: changed model re-runs")
check(not content_cached(PRIOR, grader_model="m2"), "cache: changed grader model re-runs")
check(not content_cached(PRIOR, context_mode="skillmd-only"),
      "cache: changed context mode re-runs")
legacy = {"case": "c1", "with_skill": dict(COMPLETE_ARM), "baseline": dict(COMPLETE_ARM)}
check(not content_cached(legacy), "cache: legacy record without hashes re-runs")
failed = dict(PRIOR, baseline={"response": "r", "raw_grader_output": "g",
                               "grader_failure": "bad json"})
check(not content_cached(failed), "cache: grader-failed arm re-runs, not reused")
errored = dict(PRIOR, with_skill={"error": "timeout"})
check(not content_cached(errored), "cache: errored arm re-runs, not reused")

# ---------------------------------------------------------------- manifest merge


def verdicts(met: int, total: int) -> list[dict]:
    return [{"assertion": f"a{i}", "met": i < met, "evidence": "q"}
            for i in range(total)]


def artifact_case(cid: str, ws: tuple[int, int], bl: tuple[int, int]) -> dict:
    return {"case": cid, "category": "authoring", "hashes": dict(HASHES),
            "model": "m1", "grader_model": "m1",
            "context_mode": "full-context-upper-bound",
            "with_skill": {"response": "r", "raw_grader_output": "g",
                           "verdicts": verdicts(*ws)},
            "baseline": {"response": "r", "raw_grader_output": "g",
                         "verdicts": verdicts(*bl)}}


def invocation(n: int) -> dict:
    return {"started_utc": f"2026-08-22T0{n}:00:00+00:00",
            "finished_utc": f"2026-08-22T0{n}:10:00+00:00",
            "argv": ["run_evals.py", f"--skill=s{n}"], "model": "m1",
            "grader_model": "m1", "context_mode": "full-context-upper-bound",
            "cli": "test", "settings": {}, "git_commit": "deadbeef", "git_dirty": True}


with tempfile.TemporaryDirectory() as tmp:
    out = pathlib.Path(tmp)
    # Invocation 1 writes suite A: 9/10 and 1/2 with skill -> micro 83.3, macro 70.0.
    (out / "skill-a.json").write_text(json.dumps({
        "schema_version": 2, "skill": "skill-a",
        "cases": [artifact_case("a1", (9, 10), (2, 10)),
                  artifact_case("a2", (1, 2), (0, 2))]}))
    manifest1 = ev.build_manifest(out, invocation(1))
    (out / "run.json").write_text(json.dumps(manifest1))
    check(len(manifest1["cases"]) == 2 and len(manifest1["invocations"]) == 1,
          "merge: first invocation records its own suite")
    ws = manifest1["aggregate"]["with_skill"]
    check(ws["assertion_weighted_micro_pct"] == 83.3, "merge: micro average is assertion-weighted")
    check(ws["equal_case_macro_pct"] == 70.0, "merge: macro average is equal-case")

    # Invocation 2 writes suite B into the same --out; one arm is a grader failure.
    (out / "skill-b.json").write_text(json.dumps({
        "schema_version": 2, "skill": "skill-b",
        "cases": [artifact_case("b1", (4, 4), (1, 4)),
                  dict(artifact_case("b2", (0, 1), (0, 1)),
                       with_skill={"response": "r", "raw_grader_output": "not json",
                                   "grader_failure": "no JSON object in grader output"})]}))
    manifest2 = ev.build_manifest(out, invocation(2))
    keys = {(r["skill"], r["case"]) for r in manifest2["cases"]}
    check(keys == {("skill-a", "a1"), ("skill-a", "a2"),
                   ("skill-b", "b1"), ("skill-b", "b2")},
          "merge: second invocation keeps suite A's cases (no overwrite)")
    check(len(manifest2["invocations"]) == 2 and
          manifest2["invocations"][0]["argv"] == ["run_evals.py", "--skill=s1"],
          "merge: invocation history is cumulative")
    check(manifest2["created_utc"] == manifest1["created_utc"] and
          manifest2["updated_utc"] == invocation(2)["finished_utc"],
          "merge: created_utc preserved, updated_utc advanced")
    agg = manifest2["aggregate"]
    check(agg["cases_total"] == 4, "merge: aggregate spans everything in the directory")
    check(agg["with_skill"]["grader_failures"] == 1 and
          agg["with_skill"]["cases_scored"] == 3,
          "merge: grader failure counted separately, excluded from averages")
    # 9/10 + 1/2 + 4/4 = 14/16 with skill; b2's with-skill arm must not appear as 0.
    check(agg["with_skill"]["assertions_met"] == 14 and
          agg["with_skill"]["assertions_total"] == 16,
          "merge: failed arm is not scored as zero")
    check(agg["baseline"]["cases_scored"] == 4,
          "merge: baseline arm of the failed case still counted")

# ---------------------------------------------------------------- routing parsing

VALID = {"braze-liquid", "customerio-liquid", "sailthru-zephyr"}
AV = rt.AnswerValidationError

ans = rt.parse_answer('{"load": ["braze-liquid"], "clarify": false, "why": "x"}', VALID)
check(ans["load"] == ["braze-liquid"] and ans["clarify"] is False,
      "routing: valid answer parsed")
ans = rt.parse_answer('prose first {"load": [], "why": "none apply"}', VALID)
check(ans["load"] == [] and ans["clarify"] is False,
      "routing: empty load means none, clarify defaults false")
check(fails_validation(rt.parse_answer, "I would load braze-liquid.", VALID, exc=AV),
      "routing: non-JSON answer rejected")
check(fails_validation(rt.parse_answer, '{"clarify": true}', VALID, exc=AV),
      "routing: missing load field rejected")
check(fails_validation(rt.parse_answer, '{"load": "braze-liquid"}', VALID, exc=AV),
      "routing: load as bare string rejected")
check(fails_validation(rt.parse_answer, '{"load": ["shopify-liquid"]}', VALID, exc=AV),
      "routing: unknown slug rejected")
check(fails_validation(rt.parse_answer, '{"load": [], "clarify": "yes"}', VALID, exc=AV),
      "routing: non-boolean clarify rejected")

# ---------------------------------------------------------------- routing verdicts


def verdict_of(case: dict, load: list[str], clarify: bool = False) -> str:
    return rt.judge(case, {"load": load, "clarify": clarify})["verdict"]


named = {"expect": "braze-liquid", "category": "named"}
check(verdict_of(named, ["braze-liquid"]) == "correct", "judge: expected skill fired")
check(verdict_of(named, []) == "silent", "judge: nothing fired when expected")
check(verdict_of(named, ["customerio-liquid"]) == "misfire", "judge: wrong skill fired")
check(verdict_of(named, ["braze-liquid", "customerio-liquid"]) == "misfire",
      "judge: right plus wrong is still a misfire")

clarify_case = {"expect": None, "accept": ["sailthru-zephyr", "braze-liquid"],
                "expect_clarify": True, "category": "confusable"}
check(verdict_of(clarify_case, [], clarify=True) == "correct-clarify",
      "judge: asking which platform passes a clarify case")
check(verdict_of(clarify_case, ["sailthru-zephyr"]) == "correct",
      "judge: accept-listed load on a null-expect case is not a misfire")
check(verdict_of(clarify_case, []) == "silent",
      "judge: doing nothing on a clarify case is silent, not a pass")
check(verdict_of(clarify_case, ["customerio-liquid"]) == "misfire",
      "judge: non-accepted load on a clarify case is a misfire")

oos = {"expect": None, "category": "out-of-scope"}
check(verdict_of(oos, []) == "correct-silent", "judge: out-of-scope silence passes")
check(verdict_of(oos, ["braze-liquid"]) == "misfire", "judge: out-of-scope fire is a misfire")

# ---------------------------------------------------------------- routing cache

RH = {"prompt": "sha256:p", "expectation": "sha256:e"}
rprior = {"case": "c", "verdict": "correct", "hashes": dict(RH),
          "description_set_hash": "sha256:d", "model": "m1"}
check(rt.cache_check(rprior, RH, "sha256:d", "m1")[0], "routing cache: matching record reused")
check(not rt.cache_check(dict(rprior, hashes={**RH, "prompt": "sha256:z"}),
                         RH, "sha256:d", "m1")[0],
      "routing cache: changed prompt re-runs")
check(not rt.cache_check(rprior, RH, "sha256:changed", "m1")[0],
      "routing cache: changed description set re-runs")
check(not rt.cache_check(rprior, RH, "sha256:d", "m2")[0],
      "routing cache: changed model re-runs")
rfail = {"case": "c", "error": "invalid answer: no JSON object in router output",
         "hashes": dict(RH), "description_set_hash": "sha256:d", "model": "m1"}
check(not rt.cache_check(rfail, RH, "sha256:d", "m1")[0],
      "routing cache: recorded failure re-runs")

# ---------------------------------------------------------------- routing aggregate


def rrow(cid, cat, verdict, should):
    return {"case": cid, "category": cat, "verdict": verdict,
            "should_respond": should, "wrong_skills": [], "expect": None}


rows = [
    rrow("n1", "named", "correct", True),
    rrow("n2", "named", "correct", True),
    rrow("c1", "confusable", "misfire", True),
    rrow("c2", "confusable", "silent", True),
    rrow("o1", "out-of-scope", "correct-silent", False),
    {"case": "x1", "category": "named", "error": "router call failed"},
]
agg = rt.aggregate(rows)
check(agg["cases_scored"] == 5 and agg["cases_failed"] == 1,
      "routing agg: failed case excluded from scoring, counted apart")
check(agg["micro"]["correct_fire_pct"] == 50.0, "routing agg: micro correct-fire rate")
check(agg["micro"]["misfire_pct"] == 20.0, "routing agg: micro misfire over all scored")
check(agg["micro"]["silent_pct"] == 25.0, "routing agg: micro silent over should-fire")
check(agg["micro"]["correct_silence_pct"] == 100.0, "routing agg: correct-silence rate")
# macro correct-fire: named 100, confusable 0 -> 50 (out-of-scope has no should-fire).
check(agg["macro_by_category"]["correct_fire_pct"] == 50.0,
      "routing agg: macro is the equal-category mean")
check(agg["misfired_cases"] == [{"case": "c1", "expect": None, "fired": []}],
      "routing agg: misfires listed by case")

print(f"\nall {CHECKS} checks passed")
