# Evaluations

Every skill ships a small suite of test cases in `evals/evals.json`. They are **smoke tests, not a benchmark** — four or five cases per platform is enough to catch a regression and to show what the skill is claiming to fix. It is nowhere near enough to rank skills or to prove a capability. Read the numbers that way.

These suites measure answer quality with the right skill already in context. Whether the right skill gets loaded at all — the step every content eval skips — is measured separately; see [ROUTING.md](ROUTING.md).

## Schema

`evals/evals.json`, one per skill:

```json
{
  "schema_version": 1,
  "skill": "klaviyo-django",
  "cases": [
    {
      "id": "liquid-instinct-trap",
      "category": "authoring",
      "prompt": "the user's message, verbatim",
      "expected_output": "One paragraph describing what a correct answer contains.",
      "assertions": [
        "Uses {% elif %} rather than {% elsif %}.",
        "Does not use {% assign %}."
      ],
      "files": []
    }
  ]
}
```

| Field | Rule |
|---|---|
| `schema_version` | Integer `1` |
| `skill` | Must equal the skill's directory name |
| `id` | Kebab-case, unique within the suite |
| `category` | `authoring`, `debugging`, or `adversarial` |
| `prompt` | What the user says. Realistic, not idealised |
| `expected_output` | Prose. What a correct answer contains |
| `assertions` | At least five, each objectively checkable by reading the response alone |
| `files` | Optional attachments |

Two rules the validator enforces, both learned the hard way:

**Assertions have to be checkable from the response alone.** "Uses `{% elif %}` rather than `{% elsif %}`" is checkable. "Is helpful" is not. An assertion a grader cannot fail is not an assertion.

**Every suite needs at least one `adversarial` case.** These skills are triggered by pasted templates, and pasted content is untrusted. A suite that only tests happy-path authoring tells you nothing about the behaviour that matters most.

Assertions must also be *conditionally* fair. An assertion that a correct answer can fail for a reason unrelated to the skill — because it took a different but valid approach — measures the assertion, not the skill.

## Running them

```bash
python3 scripts/run_evals.py                      # every suite
python3 scripts/run_evals.py --skill braze-liquid # one suite
python3 scripts/run_evals.py --dry-run            # print the plan, call nothing
python3 scripts/test_eval_harness.py              # harness self-test, no model calls
```

Requires the `claude` CLI on `PATH` and an authenticated session. The default model is `claude-sonnet-4-5` for both arms and the grader; override with `--model` and `--grader-model`. Each case runs three model calls: the skill's content in context, the same prompt with no skill, and a grader that scores the response against that case's assertions one at a time.

The paired run is the point. A score on its own says very little, because a capable model already knows most of the syntax. The gap between the two arms is what tells you whether the skill is carrying its weight.

**Context modes.** The with-skill arm's context is controlled by `--context-mode` and recorded in `run.json` as `context_mode`:

- `full` (default, recorded as `full-context-upper-bound`) — SKILL.md plus every file in `references/`, concatenated. That is everything the skill ships, which a progressive-disclosure runtime would rarely have loaded all at once, so read these numbers as an **upper bound** on what the skill can deliver.
- `skillmd-only` (recorded as `skillmd-only`) — SKILL.md alone, closer to what a runtime has in context before any Read into `references/`.

The two modes measure different things; never compare a number from one against a number from the other without saying so.

**Resume and cache validity.** `--out <name>` writes into a named directory. A case already recorded there is reused only when its recorded hashes (skill context as sent, prompt, assertions) and model settings (model, grader model, context mode) match the current computation; anything stale — including cases recorded before the skill's content changed — is re-run, not silently reused. Failed cases are always re-run.

**Grader validation.** A grader response is accepted only if it is valid JSON with exactly one verdict per assertion, the original assertion text preserved verbatim (same order, or an unambiguous text-keyed mapping), `met` strictly boolean, and non-empty `evidence`. Anything else is recorded as a **grader failure** for that case: the raw grader output is preserved in the artifact, the case is excluded from the averages (never scored zero), and the next invocation with the same `--out` re-runs it. No manual artifact surgery.

**Two averages, kept apart.** `run.json` and the console report both the assertion-weighted micro average (`assertion_weighted_micro_pct`: total assertions met over total assertions) and the equal-case macro average (`equal_case_macro_pct`: mean of per-case percentages). They differ whenever cases have different assertion counts; quote whichever you mean by name, never a blend.

## What gets recorded

Under `evals-runs/<name>/`:

```
run.json              provenance (git commit + dirty flag, argv, model, grader
                      model, CLI version, settings, context mode), the history
                      of every invocation that wrote into the directory, one
                      row per (skill, case), and the aggregate
<skill>.json          every case in that suite: per-case hashes (skill context,
                      prompt, assertions, suite file), model settings, both raw
                      responses, the raw grader output (success or failure),
                      and the grader's per-assertion verdict and evidence
```

`run.json` is **cumulative**: when several invocations share an `--out` directory — one per suite, say — each invocation rebuilds the manifest from every per-skill artifact present, merged by (skill, case), and the aggregate covers everything in the directory. A four-suite run can no longer be recorded as one suite by whichever invocation finished last.

Every number published anywhere in this repository has to be reproducible from a committed run directory. If you cannot point at one, do not publish the number.

## Current committed runs

`evals-runs/baseline-v1.4.1/` is the current content-eval run: 41 cases, all ten suites, `claude-sonnet-4-5` on both arms and as grader, Claude Code CLI 2.1.238, `full` context mode, produced from this code — provenance (commit, dirty flag, argv, per-case hashes) is in its `run.json`. All 41 cases scored; zero grader failures outstanding.

| Skill | Cases | With skill | Baseline | Delta |
|---|---:|---:|---:|---:|
| `moengage-jinja` | 4 | 86% | 23% | +63 |
| `hubspot-hubl` | 4 | 86% | 28% | +58 |
| `sailthru-zephyr` | 4 | 86% | 29% | +57 |
| `zeta-zml` | 4 | 89% | 34% | +55 |
| `braze-liquid` | 4 | 90% | 40% | +50 |
| `sfmc-ampscript` | 4 | 95% | 47% | +48 |
| `klaviyo-django` | 4 | 86% | 43% | +43 |
| `customerio-liquid` | 4 | 85% | 46% | +39 |
| `marketo-velocity` | 4 | 89% | 61% | +28 |
| `iterable-handlebars` | 5 | 84% | 66% | +18 |
| **All** | **41** | **88%** | **41%** | **+47** |

Micro (assertion-weighted): 87.6% vs 41.0%. Macro (equal-case): 87.3% vs 41.8%.

`evals-runs/routing-v1.4.1/` is the current routing run: 58 cases, 100% correct fire, 0% misfire, 0% silent — see `ROUTING.md`.

`evals-runs/baseline-v1.3.0/` and `evals-runs/baseline-v1.4.0/` are historical. They predate the provenance fields, were produced against earlier skill wording, and their numbers must not be quoted as current.

### Caveats worth stating plainly

- **One run, one model, no repeats.** No variance estimate. A few points of movement between runs means nothing.
- **The grader is a model.** It reads the assertion and the response and judges. It is more consistent than a human on a rubric this narrow, and it is not infallible; the per-assertion evidence is committed so you can check its work.
- **With-skill is not 100%, and should not be.** The adversarial cases are the weakest across the board — several sit at 8/12 or below. That is a real finding about the skills, not noise to be tuned away, and it is the main reason this release is a beta.
- **One grader call in the 1.4.0 run returned malformed JSON** on `moengage-jinja/partial-audience-drop-debug`, scoring the with-skill arm 0 under the harness of the time. The case was deleted from the artifact by hand and re-run; the committed directory holds the re-run. The current harness closes this hole: a grader response that fails strict validation is recorded as a grader failure with its raw output preserved, excluded from the averages, and re-run automatically on the next invocation — never a zero, never manual surgery.
- **`moengage-jinja/content-api-recommendation-row` scores 3/10 with the skill in context.** The response was sound code — `{% set %}`, a `|length` guard, `MOE_NOT_SEND` with reason strings, `|e` and `|urlencode` — and it missed six recall assertions whose answers live in `references/`, not in `SKILL.md`. Both readings are worth holding: the assertions may be asking for more recall than one response should carry, and the skill may be putting load-bearing facts a level too deep. It is published as it scored.
