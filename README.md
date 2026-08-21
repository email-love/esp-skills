# Email Love ESP Skills

Free, open-source AI skills for the personalization languages inside email service providers — the merge tags, conditionals, and loops that decide what each subscriber actually sees.

Built and maintained by [Email Love](https://www.emaillove.com). Works in **Claude** and **ChatGPT**.

## Why these exist

Every ESP has its own templating language, and general-purpose AI is confidently wrong about them in ways that survive review.

The failure mode is the problem. These aren't errors you catch in the editor — they're errors you catch in the inbox, in a support ticket three days later, or never, because the message quietly didn't send at all.

Three real examples from the baseline runs behind these skills:

- Asked for Iterable Handlebars, it produced `{{subtract}}`, `{{toFixed}}`, `{{#with}}` and `timeZone=`. None exist in Iterable. All save without error and fail at send time.
- Asked to render a deadline in the recipient's timezone in Customer.io, it asserted no such filter exists and hand-rolled a 25-branch block hardcoding UTC offsets — correct for one week of the year, silently wrong across every DST boundary. The real answer is one argument on the `date` filter.
- Asked to list a person's related objects in Customer.io, it stated flatly that the platform can't do it and proposed three engineering workarounds. `objects.<plural>[n]` does exactly that.

Each skill encodes what a platform *actually* supports, what it doesn't, and which mistakes cost you a send rather than a space.

## Skills

| Skill | Platform | Language | Status |
|---|---|---|---|
| [`iterable-handlebars`](skills/iterable-handlebars) | Iterable | Handlebars (handlebars.java) | ✅ Available |
| [`klaviyo-django`](skills/klaviyo-django) | Klaviyo | **Django templates** — not Liquid | ✅ Available |
| [`braze-liquid`](skills/braze-liquid) | Braze | Liquid 5 (Shopify), partial | ✅ Available |
| [`customerio-liquid`](skills/customerio-liquid) | Customer.io | Liquid — two engines, set per message | ✅ Available |
| [`sfmc-ampscript`](skills/sfmc-ampscript) | Salesforce Marketing Cloud | AMPscript, GTL, SSJS | ✅ Available |
| [`marketo-velocity`](skills/marketo-velocity) | Marketo Engage | Tokens + Velocity | ✅ Available |
| `hubspot-hubl` | HubSpot | HubL | 🔜 Planned |
| `mailchimp-merge-tags` | Mailchimp | Merge tags | 🔜 Planned |

Want one prioritized? [Open an issue](../../issues).

### A note on Klaviyo

Klaviyo is widely described as using Liquid. It does not — it runs the **Django** template language with a set of Liquid-*named* filter aliases bolted on. The filters read like Liquid; the tags and control flow are Django, and the difference is not cosmetic:

| Written as | Result |
|---|---|
| `{% elsif %}` | **HTTP 400 — hard error.** It's `{% elif %}` |
| `{% assign x = 1 %}` | **HTTP 400.** There is no `assign`; use `{% with %}` |
| `{{ items.size }}` | Renders empty. It's `{{ items\|length }}` |
| `{{ p \| lookup: 'Name' }}` | **HTTP 400.** A space after the colon is fatal |

That last form appears in Klaviyo's own custom-objects documentation. All four verified against Klaviyo's `/api/template-render` endpoint, not inferred from docs.

Klaviyo's developer documentation says so directly — the page is slugged `django_message_design` and links out to Django's own builtins reference:

> "Klaviyo supports most of the filters used by the **Django template language**"

> "**Django template variables** cannot include spaces or special characters such as hyphens."

— [Message design overview](https://developers.klaviyo.com/en/docs/django_message_design)

And the render API's own error text names the engine: *"Please check included **django** syntax and ensure it is compatible with provided context."*

## Designing the email in Figma

Every skill also covers applying its language inside a Figma file built with the [Email Love plugin](https://www.emaillove.com/figma-plugin), which is a different problem from writing the code in the ESP. The language is identical — the plugin inserts your templating code as-is and validates none of it — but placement is not, and the plugin's preview does not render code blocks, so nothing is visible before export.

The rule that matters most: **paired Code Blocks must be siblings at the same nesting level.** Both between wrappers, both between sections, or both inside the same column. Compiled on MJML 4.18, a pair spanning two levels with the condition false leaves three orphaned `</table>`, `</tr>`, and `</td>` tags and an Outlook conditional-table depth of `-2`. The same pair as siblings, wrapping a two-column section and a wrapper and a full-width section at once, is balanced at depth `0`.

It fails quietly, too. The condition is true in your test send, so nothing looks wrong; it only breaks for recipients on the other branch, and it breaks worst in Outlook.

A second one, found the same way: a **double-quoted string argument in a link field silently truncates the link.** `{{ slug|default:"home" }}` in an href compiles without complaint at MJML's default validation level and ships as `href="https://x.com/{{ slug|default:"`. Klaviyo and Salesforce Marketing Cloud both write double quotes in their own documentation, so this is a copy-paste away on either.

Each skill's `references/figma-export.md` has the rest, including the specifics of that platform's export target — Braze Content Blocks dropping the `<head>`, Iterable snippets carrying no CSS, Marketo's reserved words breaking a link URL, SFMC impression regions taking their names from Figma layer names.

## Install

### Claude Code

```bash
claude plugin marketplace add email-love/esp-skills
claude plugin install iterable-handlebars@email-love-esp
```

### Claude (web, desktop, Cowork)

Download the `.skill` file from [Releases](../../releases) and upload it in Settings → Capabilities → Skills.

### ChatGPT

These follow the [Agent Skills open standard](https://help.openai.com/en/articles/20001066-skills-in-chatgpt), so the same folder works unmodified. Download the `.skill` from [Releases](../../releases), then in ChatGPT: **Skills → Create → Upload from your computer**. Requires a Business, Enterprise, Healthcare, or Edu plan. Also works in Codex and via the API.

### Claude Code / Codex, manual

```bash
git clone https://github.com/email-love/esp-skills.git
cp -r esp-skills/skills/iterable-handlebars ~/.claude/skills/
```

Once installed, skills trigger on their own. You don't invoke them — ask a question about your ESP's templating and the right one loads.

## One skill, both platforms

There is no Claude version and ChatGPT version. Both products read the same `SKILL.md` frontmatter and the same `references/` folder, so a skill authored once installs in either.

```
skills/iterable-handlebars/
├── SKILL.md                 # frontmatter (name, description) + workflow
├── references/              # loaded on demand, not upfront
│   ├── helpers.md
│   ├── data-sources.md
│   └── troubleshooting.md
├── agents/openai.yaml       # optional ChatGPT display metadata; Claude ignores it
└── evals/                   # test prompts and assertions
```

The one thing that isn't portable is *tools*. A skill that drives Figma or a browser only works where those tools exist. Everything in this repo is pure knowledge — no tool dependencies — so it runs anywhere.

## How these are built

Every skill here is written against the platform's official documentation, then measured against a no-skill baseline on realistic test prompts before release. Three cases per platform, run with and without the skill, graded on objective assertions:

| Skill | With skill | Baseline | Delta |
|---|---|---|---|
| `customerio-liquid` | 100% | 39% | +60 |
| `marketo-velocity` | 100% | 46% | +54 |
| `sfmc-ampscript` | 100% | 48% | +52 |
| `iterable-handlebars` | 100% | 52% | +48 |
| `braze-liquid` | 100% | 57% | +43 |
| `klaviyo-django` | 100% | 76% | +24 |

The spread is the interesting part, and we publish it rather than the average.

**Klaviyo has the smallest gap.** A general model already knows Klaviyo is Django-based, so the skill mostly adds second-order rules like the filter-colon spacing. **Customer.io has the largest**, because the baseline there doesn't fail by omission — it produces confident, elaborate, wrong answers that look reviewable.

The pattern across all six: the baseline is better at *syntax* than at *consequences*. It usually knows the language. What it reliably misses is which mistakes cost you a send, where the platform records the failure, and what the platform's own documentation gets wrong.

Test prompts and assertions ship with each skill in `evals/`, so you can see exactly what was checked and disagree with it.

## Contributing

ESPs change. If a skill tells you something that's no longer true, [open an issue](../../issues) with the platform, the skill's claim, and a link to the current docs — that's the most useful contribution here.

Adding a platform:

```bash
./scripts/build.sh        # package every skill into dist/*.skill
python3 scripts/validate.py   # check frontmatter before you commit
```

Keep `SKILL.md` under ~500 lines and push lookup tables into `references/` — both platforms load reference files on demand, so depth there is close to free while depth in `SKILL.md` is paid on every trigger.

## Also from Email Love

[**email-love/claude-skills**](https://github.com/email-love/claude-skills) — skills for building production emails in Figma with the Email Love plugin: design system migration, audits, and export-ready email assembly.

[**emaillove.com**](https://www.emaillove.com) — curated email design inspiration, and the Figma plugin that turns your designs into production code.

## License

MIT
