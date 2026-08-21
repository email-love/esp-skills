# Email Love ESP Skills

Free, open-source AI skills for the personalization languages inside email service providers — the merge tags, conditionals, and loops that decide what each subscriber actually sees.

Built and maintained by [Email Love](https://www.emaillove.com). Works in **Claude** and **ChatGPT**.

> **Beta.** The content is grounded in first-party documentation and measured against a no-skill baseline, but the suites are small, one Customer.io behaviour is unverified end to end (see [Known limitations](#known-limitations)), and nothing here has been through a stable release. Use it, and report what it gets wrong.

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
| [`iterable-handlebars`](skills/iterable-handlebars) | Iterable | Handlebars (handlebars.java) | 🧪 Beta |
| [`klaviyo-django`](skills/klaviyo-django) | Klaviyo | **Django templates** — not Liquid | 🧪 Beta |
| [`braze-liquid`](skills/braze-liquid) | Braze | Liquid 5 (Shopify), partial | 🧪 Beta |
| [`customerio-liquid`](skills/customerio-liquid) | Customer.io | Liquid — two engines, set per message | 🧪 Beta |
| [`sfmc-ampscript`](skills/sfmc-ampscript) | Salesforce Marketing Cloud | AMPscript, GTL, SSJS | 🧪 Beta |
| [`marketo-velocity`](skills/marketo-velocity) | Marketo Engage | Tokens + Velocity | 🧪 Beta |
| [`hubspot-hubl`](skills/hubspot-hubl) | HubSpot | HubL (Jinjava) | 🧪 Beta |
| [`moengage-jinja`](skills/moengage-jinja) | MoEngage | Jinja | 🧪 Beta |
| [`sailthru-zephyr`](skills/sailthru-zephyr) | Sailthru / Zeta Engage | **Zephyr** — single braces, no filters | 🧪 Beta |
| [`zeta-zml`](skills/zeta-zml) | Zeta Marketing Platform | ZML — Liquid-derived | 🧪 Beta |
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

## Choose your skill

| Your ESP | Skill | Try it with |
|---|---|---|
| Iterable | [`iterable-handlebars`](skills/iterable-handlebars) | "Why is my Iterable cart loop rendering blank for some users?" |
| Klaviyo | [`klaviyo-django`](skills/klaviyo-django) | "Write a Klaviyo block that shows different copy per loyalty tier." |
| Braze | [`braze-liquid`](skills/braze-liquid) | "My Braze campaign sent to half the audience and stopped. Why?" |
| Customer.io | [`customerio-liquid`](skills/customerio-liquid) | "Some Customer.io deliveries show as Failed, not bounced. What's happening?" |
| Salesforce Marketing Cloud | [`sfmc-ampscript`](skills/sfmc-ampscript) | "Subscribers are showing as Errored on this AMPscript send." |
| Marketo Engage | [`marketo-velocity`](skills/marketo-velocity) | "This Marketo email won't validate and there's no scripting in it." |
| HubSpot | [`hubspot-hubl`](skills/hubspot-hubl) | "Why is my default value not working on a HubSpot contact token?" |
| MoEngage | [`moengage-jinja`](skills/moengage-jinja) | "My MoEngage campaign reached far fewer users than the segment. Why?" |
| Sailthru / Zeta Engage | [`sailthru-zephyr`](skills/sailthru-zephyr) | "This Sailthru campaign sent, but the email arrived empty." |
| Zeta Marketing Platform | [`zeta-zml`](skills/zeta-zml) | "Some messages in this Zeta campaign show as skipped. What causes that?" |

Install only the one you use. Each skill is deliberately scoped to a single platform and tells the model not to apply itself to the others, so installing all ten is fine but installing one is better.

**Zeta ships two email platforms and they speak different languages.** Zeta Marketing Platform uses ZML, which is Liquid-derived. Zeta Engage by Sailthru uses Zephyr, which is single-brace and has no filter pipe. If you are not sure which one you are on, look at an existing template: `{% if %}` means ZML, `{if}` means Zephyr.

## Install

### Claude Code

```bash
claude plugin marketplace add email-love/esp-skills
claude plugin install klaviyo-django@email-love-esp
```

Update with `claude plugin marketplace update email-love-esp`, then reinstall. Remove with `claude plugin uninstall klaviyo-django@email-love-esp`.

Verified against Claude Code 2.1.238: the marketplace resolves, the plugin installs at the version in `VERSION`, and `claude plugin details` reports roughly 370 tokens always-on with about 5.1k paid when the skill actually fires.

### Claude apps (web, desktop, Cowork)

Download the `.skill` file for your platform from [Releases](../../releases), then **Settings → Capabilities → Skills → Upload**.

An uploaded skill is a snapshot, not a subscription. It does not update itself — to move to a new version, download the new `.skill` and upload it again; same name replaces the old one. Remove it from the same screen.

### ChatGPT

These follow the [Agent Skills open standard](https://help.openai.com/en/articles/20001066-skills-in-chatgpt), so the same folder works unmodified. Download the `.skill` from [Releases](../../releases), then **Skills → Create → Upload from your computer**. Requires a Business, Enterprise, Healthcare, or Edu plan. Updates and removal work the same way as the Claude apps: re-upload to update, delete to remove.

`agents/openai.yaml` supplies the display name, blurb, and default prompt ChatGPT shows. Claude ignores that file.

### Codex

Codex reads the same directory layout. Clone and copy the skill you want into your Codex skills directory:

```bash
git clone https://github.com/email-love/esp-skills.git
cp -r esp-skills/skills/klaviyo-django ~/.codex/skills/
```

### Manually, into Claude Code

```bash
git clone https://github.com/email-love/esp-skills.git
cp -r esp-skills/skills/klaviyo-django ~/.claude/skills/
```

Once installed, skills trigger on their own. You don't invoke them — ask a question about your ESP's templating and the right one loads.

### Verifying a download

Every release ships `SHA256SUMS`. From the directory holding the downloaded files:

```bash
sha256sum -c SHA256SUMS
```

## One skill, both platforms

There is no Claude version and ChatGPT version. Both products read the same `SKILL.md` frontmatter and the same `references/` folder, so a skill authored once installs in either.

```
skills/iterable-handlebars/
├── SKILL.md                 # frontmatter (name, description) + workflow
├── LICENSE                  # every archive is independently licensed
├── references/              # loaded on demand, not upfront
│   ├── helpers.md
│   ├── data-sources.md
│   ├── troubleshooting.md
│   └── figma-export.md      # generated from shared/ - see Contributing
├── agents/openai.yaml       # ChatGPT display metadata; Claude ignores it
└── evals/evals.json         # test prompts and assertions
```

The one thing that isn't portable is *tools*. A skill that drives Figma or a browser only works where those tools exist. Everything in this repo is pure knowledge — no tool dependencies — so it runs anywhere.

## How these are built

Every skill is written against the platform's official documentation, then measured against a no-skill baseline before release. Each case runs twice — with the skill's content in context and without it — and a grader scores the response against that case's assertions one at a time.

41 cases, `claude-sonnet-4-5` on both arms and as grader, Claude Code CLI 2.1.238:

| Skill | Cases | With skill | Baseline | Delta |
|---|---:|---:|---:|---:|
| `sailthru-zephyr` | 4 | 86% | 33% | +53 |
| `moengage-jinja` | 4 | 65% | 21% | +44 |
| `zeta-zml` | 4 | 89% | 48% | +41 |
| `customerio-liquid` | 4 | 75% | 36% | +39 |
| `hubspot-hubl` | 4 | 79% | 40% | +39 |
| `sfmc-ampscript` | 4 | 88% | 51% | +37 |
| `marketo-velocity` | 4 | 90% | 53% | +37 |
| `klaviyo-django` | 4 | 82% | 46% | +36 |
| `braze-liquid` | 4 | 77% | 42% | +35 |
| `iterable-handlebars` | 5 | 88% | 65% | +23 |
| **All** | **41** | **81%** | **43%** | **+38** |

**These are smoke tests, not a benchmark.** Four or five cases per platform catches a regression and shows what the skill claims to fix. It cannot rank skills or prove a capability, and one run of one model gives no variance estimate. Every prompt, response, per-assertion verdict, and setting is committed under `evals-runs/baseline-v1.3.0/` and `evals-runs/baseline-v1.4.0/` — [`EVALS.md`](EVALS.md) has the schema, the command, and the caveats.

The spread is the interesting part, and we publish it rather than the average. **The delta tracks how alien the language is.** Klaviyo and Iterable have the smallest gaps, because a general model already knows roughly what those languages are. **Sailthru's Zephyr has the largest** — single braces, no filter pipe, functions instead of filters — and a baseline model writes confident Liquid at it. Customer.io and MoEngage are large for the opposite reason: the baseline doesn't fail by omission there, it produces elaborate, wrong answers that look reviewable. MoEngage's baseline scored **0 out of 10** on the case that asks what happens to a user with a missing attribute.

The pattern across all ten: the baseline is better at *syntax* than at *consequences*. It usually knows the language. What it reliably misses is which mistakes cost you a send, where the platform records the failure, and what the platform's own documentation gets wrong.

**With-skill is not 100%, and two results are worth naming rather than averaging away.** The adversarial cases are the weakest class across the board. And `moengage-jinja` scores 65% — the lowest in the set — because its Content API case expects the model to recall six specific platform facts that live in `references/`, and the response only surfaced three. We are publishing that rather than loosening the assertions. It is the main reason this is a beta rather than a stable release.

## Known limitations

**Customer.io unsubscribe tags, via the Email Love plugin — unverified.** Customer.io documents `{% unsubscribe_url %}` as a tag and states that the variable form `{{unsubscribe_url}}` "will render as empty text". Email Love's own [Customer.io export documentation](https://help.emaillove.com/plugin/export/customerio) says the plugin swaps the footer link for `{{unsubscribe_url}}` — the variable form. If the plugin really emits that, a Figma-exported Customer.io email ships with an empty unsubscribe link, which is a compliance problem and not a cosmetic one.

We could not resolve this from the outside: it needs one Figma file exported through the current plugin to Customer.io, and the exported HTML read. Until someone does that, this skill follows Customer.io's documented syntax, and the Figma reference says so explicitly. If you have both halves, [tell us what you see](../../issues).

**Nothing here has been through a stable release.** The eval suites are small, the guidance on trust boundaries is new, and no platform behaviour has been re-verified on a schedule yet.

## Contributing

ESPs change. If a skill tells you something that's no longer true, [open an issue](../../issues) with the platform, the skill's claim, and a link to the current docs — that's the most useful contribution here.

Adding a platform:

```bash
python3 -m pip install pyyaml==6.0.2
python3 scripts/validate.py          # frontmatter, metadata, evals, versions, hygiene
python3 scripts/sync_shared.py       # regenerate the blocks shared by every skill
bash scripts/build.sh                # package every skill into dist/*.skill
bash scripts/verify_dist.sh          # zip integrity, inventory, licence, checksums
```

Two blocks are shared between all six skills and generated rather than hand-edited: `references/figma-export.md`, and the "Handling untrusted content" section in each `SKILL.md`. Edit them in `shared/` and run `scripts/sync_shared.py`. CI runs `--check` and fails on drift.

Changing the version means editing `VERSION` and adding a matching `## [x.y.z]` section to `CHANGELOG.md`; the validator checks that the marketplace manifest agrees.

Keep `SKILL.md` under ~500 lines and push lookup tables into `references/` — both platforms load reference files on demand, so depth there is close to free while depth in `SKILL.md` is paid on every trigger.

## Also from Email Love

[**email-love/claude-skills**](https://github.com/email-love/claude-skills) — skills for building production emails in Figma with the Email Love plugin: design system migration, audits, and export-ready email assembly.

[**emaillove.com**](https://www.emaillove.com) — curated email design inspiration, and the Figma plugin that turns your designs into production code.

## License

MIT
