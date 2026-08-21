# Contributing

## Reporting something wrong

ESPs ship changes and these skills go stale. The most valuable issue you can file:

- Which skill and which claim
- What actually happens now
- A link to the platform's current documentation

## Adding a platform

1. Create `skills/<platform>-<language>/SKILL.md` with `name` and `description` frontmatter. The folder name and `name` must match — `scripts/validate.py` enforces it.
2. Put lookup material in `references/*.md`. Both Claude and ChatGPT load these on demand, so depth here costs nothing until it's needed; depth in `SKILL.md` is paid every time the skill fires.
3. Write the description last, and write it as trigger conditions rather than a summary. It is the entire mechanism by which the skill gets used — and with sibling skills in the same install, it also needs to say which platforms it is *not* for.
4. Add test prompts to `evals/evals.json` and run them against a no-skill baseline before you open the PR. If the baseline scores as well as the skill, the skill isn't earning its context.
5. Register it in `.claude-plugin/marketplace.json`.

```bash
python3 scripts/validate.py   # frontmatter + reference-file checks
./scripts/build.sh            # package into dist/*.skill
```

## Writing style

Explain *why* a rule exists rather than issuing it. A model that understands that an unguarded comparison helper skips the send will generalize the guard to cases the skill never listed; one told "ALWAYS wrap comparisons" will apply it mechanically and miss the variants.
