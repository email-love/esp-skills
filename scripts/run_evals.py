#!/usr/bin/env python3
"""Run the eval suites and write a reproducible record of the result.

Every case runs twice - once with the skill's content in context, once without -
and a third model call grades each response against that case's assertions. The
point of the paired run is that a score on its own says very little; the delta
between the two arms is what tells you whether the skill is carrying its weight.

Everything needed to reproduce or dispute a published number is written to
evals-runs/<timestamp>/: run.json holds the model, settings and aggregate, and
one <skill>.json per suite holds every case with both raw responses and the
grader's per-assertion verdicts.

    python3 scripts/run_evals.py                 # every skill
    python3 scripts/run_evals.py --skill klaviyo-django
    python3 scripts/run_evals.py --dry-run       # print the plan, call nothing

Requires the `claude` CLI on PATH and an authenticated session.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
RUNS = ROOT / "evals-runs"

GRADER_INSTRUCTIONS = """\
You are grading one response against a list of assertions.

Judge only what the response actually says. An assertion is met only if the
response supports it; absence is not support, and plausible-sounding filler is
not support. Do not reward a response for being well written.

Return ONLY a JSON object, no prose and no code fence:

{"verdicts": [{"assertion": "<verbatim assertion>", "met": true, "evidence": "<short quote from the response, or why it fails>"}]}
"""


def skill_context(skill_dir: pathlib.Path) -> str:
    """Everything the platform would load for this skill, concatenated."""
    parts = [f"### {skill_dir.name}/SKILL.md\n\n{(skill_dir / 'SKILL.md').read_text()}"]
    for ref in sorted((skill_dir / "references").glob("*.md")):
        parts.append(f"### {skill_dir.name}/references/{ref.name}\n\n{ref.read_text()}")
    return "\n\n".join(parts)


def claude(prompt: str, model: str, timeout: int) -> str:
    proc = subprocess.run(
        ["claude", "-p", "--model", model, "--output-format", "text"],
        input=prompt, capture_output=True, text=True, timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"claude exited {proc.returncode}: {proc.stderr.strip()[:500]}")
    return proc.stdout.strip()


def grade(response: str, assertions: list[str], model: str, timeout: int) -> dict:
    prompt = (
        f"{GRADER_INSTRUCTIONS}\n\n## Assertions\n\n"
        + json.dumps(assertions, indent=2)
        + f"\n\n## Response under test\n\n{response}\n"
    )
    raw = claude(prompt, model, timeout)
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        raise RuntimeError(f"grader did not return JSON: {raw[:300]}")
    return json.loads(raw[start : end + 1])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skill", action="append", help="limit to one skill (repeatable)")
    ap.add_argument("--model", default="claude-opus-4-5", help="model for both arms")
    ap.add_argument("--grader-model", default=None, help="defaults to --model")
    ap.add_argument("--timeout", type=int, default=600, help="per-call timeout, seconds")
    ap.add_argument("--limit", type=int, default=None,
                    help="run at most N cases per suite (smoke test)")
    ap.add_argument("--out", default=None,
                    help="write into this run directory instead of a new timestamped one; "
                         "cases already recorded there are skipped, so an interrupted run resumes")
    ap.add_argument("--dry-run", action="store_true", help="print the plan and exit")
    args = ap.parse_args()
    grader_model = args.grader_model or args.model

    if not args.dry_run and shutil.which("claude") is None:
        print("the `claude` CLI is not on PATH", file=sys.stderr)
        return 2

    suites = []
    for path in sorted(ROOT.glob("skills/*/evals/evals.json")):
        data = json.loads(path.read_text())
        if args.skill and data["skill"] not in args.skill:
            continue
        if args.limit:
            data = dict(data, cases=data["cases"][: args.limit])
        suites.append((path.parent.parent, data))

    if not suites:
        print("no matching eval suites", file=sys.stderr)
        return 2

    total_cases = sum(len(d["cases"]) for _, d in suites)
    print(f"{len(suites)} suite(s), {total_cases} case(s), {total_cases * 3} model calls")
    if args.dry_run:
        for skill_dir, data in suites:
            for case in data["cases"]:
                print(f"  {data['skill']}/{case['id']} [{case['category']}] "
                      f"{len(case['assertions'])} assertions")
        return 0

    started = dt.datetime.now(dt.timezone.utc)
    out = RUNS / (args.out or started.strftime("%Y%m%dT%H%M%SZ"))
    out.mkdir(parents=True, exist_ok=True)

    results = []
    for skill_dir, data in suites:
        context = skill_context(skill_dir)
        artefact = out / f"{data['skill']}.json"
        recorded = {}
        if artefact.exists():
            recorded = {c["case"]: c for c in json.loads(artefact.read_text())["cases"]}

        cases_out = []
        for case in data["cases"]:
            row = {"skill": data["skill"], "case": case["id"], "category": case["category"],
                   "assertions": len(case["assertions"])}
            prior = recorded.get(case["id"])
            if prior and all(a in prior for a in ("with_skill", "baseline")):
                for arm in ("with_skill", "baseline"):
                    v = prior[arm]["verdicts"]
                    met = sum(1 for x in v if x.get("met"))
                    row[arm] = {"met": met, "total": len(v),
                                "pct": round(100 * met / len(v)) if v else 0}
                cases_out.append(prior)
                results.append(row)
                print(f"  {data['skill']}/{case['id']} [cached]")
                continue

            record = {"case": case["id"], "category": case["category"]}
            for arm, prompt in (
                ("with_skill",
                 f"Use the following reference material to answer.\n\n{context}\n\n"
                 f"---\n\nUser:\n\n{case['prompt']}"),
                ("baseline", case["prompt"]),
            ):
                try:
                    response = claude(prompt, args.model, args.timeout)
                    verdicts = grade(response, case["assertions"], grader_model, args.timeout)["verdicts"]
                except Exception as exc:                      # noqa: BLE001 - recorded, not raised
                    record[arm] = {"error": str(exc)}
                    row[arm] = {"error": str(exc)}
                    print(f"  !! {data['skill']}/{case['id']} [{arm}] {exc}")
                    continue

                record[arm] = {"response": response, "verdicts": verdicts}
                met = sum(1 for v in verdicts if v.get("met"))
                row[arm] = {"met": met, "total": len(verdicts),
                            "pct": round(100 * met / len(verdicts)) if verdicts else 0}
                print(f"  {data['skill']}/{case['id']} [{arm}] {met}/{len(verdicts)}")

            cases_out.append(record)
            results.append(row)

        artefact.write_text(json.dumps(
            {"skill": data["skill"], "cases": cases_out}, indent=2, ensure_ascii=False) + "\n")

    def arm_pct(arm: str) -> float | None:
        vals = [r[arm]["pct"] for r in results if isinstance(r.get(arm), dict) and "pct" in r[arm]]
        return round(sum(vals) / len(vals), 1) if vals else None

    record = {
        "started_utc": started.isoformat(),
        "finished_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "repo_version": (ROOT / "VERSION").read_text().strip(),
        "model": args.model,
        "grader_model": grader_model,
        "cli": subprocess.run(["claude", "--version"], capture_output=True, text=True).stdout.strip(),
        "settings": {"output_format": "text", "timeout_seconds": args.timeout},
        "cases": results,
        "aggregate": {"with_skill_pct": arm_pct("with_skill"), "baseline_pct": arm_pct("baseline")},
    }
    (out / "run.json").write_text(json.dumps(record, indent=2) + "\n")

    print(f"\nwith skill {record['aggregate']['with_skill_pct']}%  "
          f"baseline {record['aggregate']['baseline_pct']}%")
    print(f"artifacts: {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
