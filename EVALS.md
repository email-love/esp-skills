# Evaluations

Every skill ships a small suite of test cases in `evals/evals.json`. They are **smoke tests, not a benchmark** — four or five cases per platform is enough to catch a regression and to show what the skill is claiming to fix. It is nowhere near enough to rank skills or to prove a capability. Read the numbers that way.

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
```

Requires the `claude` CLI on `PATH` and an authenticated session. Each case runs three model calls: the skill's content in context, the same prompt with no skill, and a grader that scores the response against that case's assertions one at a time.

The paired run is the point. A score on its own says very little, because a capable model already knows most of the syntax. The gap between the two arms is what tells you whether the skill is carrying its weight.

Runs are resumable. `--out <name>` writes into a named directory and skips cases already recorded there, so an interrupted run picks up where it stopped.

## What gets recorded

Under `evals-runs/<name>/`:

```
run.json              model, grader model, CLI version, settings, timestamps,
                      per-case scores, aggregate
<skill>.json          every case in that suite, with both raw responses and the
                      grader's per-assertion verdict and evidence
```

Every number published anywhere in this repository has to be reproducible from a committed run directory. If you cannot point at one, do not publish the number.

## Current committed runs

Two directories, because the four platforms added in 1.4.0 were run separately rather than re-running the six that had not changed. Both used `claude-sonnet-4-5` on both arms and as grader, Claude Code CLI 2.1.238.

`evals-runs/baseline-v1.4.0/` — 16 cases, the platforms added in 1.4.0.

| Skill | Cases | With skill | Baseline | Delta |
|---|---:|---:|---:|---:|
| `sailthru-zephyr` | 4 | 86% | 33% | +53 |
| `moengage-jinja` | 4 | 65% | 21% | +44 |
| `zeta-zml` | 4 | 89% | 48% | +41 |
| `hubspot-hubl` | 4 | 79% | 40% | +39 |
| **These four** | **16** | **80%** | **35%** | **+45** |

`evals-runs/baseline-v1.3.0/` — 25 cases, the original six.

| Skill | Cases | With skill | Baseline | Delta |
|---|---:|---:|---:|---:|
| `customerio-liquid` | 4 | 75% | 36% | +39 |
| `sfmc-ampscript` | 4 | 88% | 51% | +37 |
| `marketo-velocity` | 4 | 90% | 53% | +37 |
| `klaviyo-django` | 4 | 82% | 46% | +36 |
| `braze-liquid` | 4 | 77% | 42% | +35 |
| `iterable-handlebars` | 5 | 88% | 65% | +23 |
| **These six** | **25** | **82%** | **49%** | **+33** |

Across both directories: **41 cases, 412 assertions, 81% with skill against 43% baseline.** The six skills in the 1.3.0 directory did change in 1.4.0 — the shared trust-boundary block was reworded — so their numbers are from the wording that shipped in 1.3.0, not from what is on disk now. Re-run them before quoting those rows as current.

### Caveats worth stating plainly

- **One run, one model, no repeats.** No variance estimate. A few points of movement between runs means nothing.
- **The grader is a model.** It reads the assertion and the response and judges. It is more consistent than a human on a rubric this narrow, and it is not infallible; the per-assertion evidence is committed so you can check its work.
- **With-skill is not 100%, and should not be.** The adversarial cases are the weakest across the board — several sit at 8/12 or below. That is a real finding about the skills, not noise to be tuned away, and it is the main reason this release is a beta.
- **One grader call in the 1.4.0 run returned malformed JSON** on `moengage-jinja/partial-audience-drop-debug`, scoring the with-skill arm 0. The case was deleted from the artifact and re-run rather than left as a zero; the committed directory holds the re-run. A grader that can fail this way is a known weakness of the harness.
- **`moengage-jinja/content-api-recommendation-row` scores 3/10 with the skill in context.** The response was sound code — `{% set %}`, a `|length` guard, `MOE_NOT_SEND` with reason strings, `|e` and `|urlencode` — and it missed six recall assertions whose answers live in `references/`, not in `SKILL.md`. Both readings are worth holding: the assertions may be asking for more recall than one response should carry, and the skill may be putting load-bearing facts a level too deep. It is published as it scored.
