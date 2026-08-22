# Routing evaluations

The content evals in [EVALS.md](EVALS.md) assume the right skill is already loaded and measure the quality of the answer. This suite measures the step before that: shown nothing but the ten `name` + `description` pairs and one user message — the same information a routing layer has at runtime — does the model load the right skill, the wrong one, or none at all? A skill whose description never fires is invisible; one that fires on another platform's question produces answers that are fluent and wrong.

The descriptions are read live from `skills/*/SKILL.md` frontmatter at run time, never copied into the suite, so the numbers always reflect the wording actually on disk. Nothing under `skills/` is ever written to.

## Schema

`routing/cases.json`, 58 cases across five categories:

| Category | Cases | What it probes |
|---|---:|---|
| `named` | 10 | Platform named outright, one per skill. The easy baseline. |
| `symptom` | 13 | Platform named, but the question is a symptom with no language jargon. |
| `code-only` | 13 | A pasted snippet, platform never named; syntax alone identifies it. |
| `confusable` | 12 | Built to provoke cross-firing: Zeta-says-Zephyr, HubSpot in Jinja terms, generic "Liquid". |
| `out-of-scope` | 10 | Mailchimp, Shopify, plain HTML, deliverability, copywriting. Nothing should fire. |

Each case:

| Field | Rule |
|---|---|
| `id` | Kebab-case, unique in the suite |
| `prompt` | What the user types, verbatim — lowercase, partial, warts included |
| `expect` | The slug that should fire, or `null` when nothing should |
| `accept` | Optional extra slugs that are defensible and not counted as mis-fires |
| `expect_clarify` | Optional; `true` when the message is genuinely ambiguous between platforms and asking which one is a full pass — not a fake single answer |
| `category` | One of the five above |
| `why` | One line on what the case probes |

## Running it

```bash
python3 scripts/run_routing_evals.py                    # all 58 cases
python3 scripts/run_routing_evals.py --category confusable --limit 5
python3 scripts/run_routing_evals.py --out routing-v1   # resumable
python3 scripts/run_routing_evals.py --dry-run          # print the plan, call nothing
python3 scripts/test_eval_harness.py                    # harness self-test, no model calls
```

Requires the `claude` CLI on `PATH` and an authenticated session. Default model is `claude-sonnet-4-5`; one model call per case. The model is asked to return `{"load": [...], "clarify": bool, "why": ...}`; an answer that fails strict validation — not JSON, no `load` list, or a name not in the installed set — is recorded as a failure with the raw output preserved, excluded from the rates, and re-run on the next invocation with the same `--out`. Never coerced into a verdict.

Artifacts land in `evals-runs/<name>/`: `routing.json` holds every case with the raw answer and the verdict; `run.json` holds provenance (git commit and dirty flag, argv, model, CLI version, the hash of the description set as presented, per-case prompt and expectation hashes), the invocation history, and the aggregate — cumulative over everything recorded in the directory. A recorded case is reused only when its hashes, the description-set hash, and the model match the current state; edit any description and every case re-runs.

## Reading the three scores

Three numbers, kept apart on purpose — do not average them into one:

- **`correct_fire_pct`** — on cases where a skill should load, the right one (or an accept-listed one, or a clarify where the case allows it) did.
- **`misfire_pct`** — a skill fired that should not have, over all scored cases. **The dangerous one**: a mis-routed question gets a confident answer in the wrong platform's syntax. `misfired_cases` in `run.json` names each offender.
- **`silent_pct`** — nothing fired (and no clarify where one would count) on a case where something should have, over the should-fire cases. Merely worthless: the user gets a generic answer instead of the skill.

`correct_silence_pct` tracks the out-of-scope cases separately. Each rate is reported micro (pooled over cases) and macro (equal-weight mean across categories, under `macro_by_category`); the two differ when categories are uneven, so quote whichever you mean by name.

## What acceptable looks like

`named` should be at or near 100% correct-fire — a description that cannot catch its own platform's name is broken. `symptom` and `code-only` are what the descriptions are actually for; sustained silence there means load-bearing symptoms or syntax markers are missing from a description. Mis-fire is the number to hold near zero everywhere, and `out-of-scope` correct-silence should stay high — over-triggering is a worse trade than the occasional silence. On `confusable`, a `correct-clarify` is a real pass: for a genuinely ambiguous message, asking which platform is the honest behaviour, and a description rewrite that converts clarifies into confident cross-fires is a regression even if correct-fire ticks up.

Like the content evals: one run, one model, no repeats, no variance estimate. A few points of movement between runs means nothing; a new mis-fire that reproduces does.
