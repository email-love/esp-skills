# Changelog

All notable changes to the skills in this repo.

## [1.4.1] — 2026-08-22

Correctness and evaluation-integrity release, driven by an external review of 1.4.0 and by reading every failed eval assertion against the response that failed it. No new platforms.

### Corrected guidance

- **The shared escaping section no longer claims HTML output is escaped by default everywhere.** It never was: Marketo Velocity is explicitly unencoded, MoEngage runs Jinja with autoescape off, and Zephyr output is raw unless `h()` is called. The generated section now states each platform's verified default — escaped (Iterable double-brace, Klaviyo Django), raw (Braze, Customer.io, SFMC, Marketo, MoEngage, Sailthru), or honestly undocumented (HubSpot, Zeta) — from `shared/security/escaping.json`.
- **Klaviyo:** removed every suggestion that `|safe` or `{% autoescape off %}` addresses JSON or JavaScript output. Klaviyo ships no JSON/JS encoder; untrusted values must not be interpolated into inline script or JSON at all — assemble them upstream as structured data.
- **Customer.io:** `{% render_liquid %}` guidance is now consistent everywhere — author-written template strings only, never LLM, webhook, partner, profile, feed, or event content. The whole-object pseudo-JSON example is gone in favour of named fields and real serialization.
- **HubSpot:** `shared/security/mechanisms.json` wrongly said HubL has no stored-string evaluation construct. It does — the `|render` filter — and the generated trust-boundary text now names it.
- **SFMC:** removed an inverted claim that attributed to Salesforce the statement that `Empty()`/`IsNull()` return false on an empty rowset; current Salesforce documentation says both return true and directs authors to `RowCount()`. Preview examples touching `UpsertDE`/deletes/HTTP now require an isolated test data extension and seed subscriber.
- **MoEngage:** complete URLs are no longer piped through `|urlencode` (which is for path segments and query values and can mangle the scheme); dynamic destinations are validated against an HTTPS allowlist instead. The two fallback surfaces — raw-Jinja null suppression versus the UI's "No fallback" option — are now named as different mechanisms with different outcomes.
- **Marketo:** copy-ready Velocity examples wrap dynamic HTML text in `$esc.html(...)`.
- **All skills:** copy-ready URLs no longer embed recipient emails or user IDs (opaque signed tokens instead), and preview guidance uses dedicated seed/test records rather than production profiles.

### Recall and statement fixes

Every failed with-skill assertion from the 1.3.0 and 1.4.0 runs was classified — content gap, present-but-unattached, behaviour-right-statement-missing, or over-specified assertion — and fixed accordingly. Load-bearing facts are now attached to the scenarios that trigger them rather than filed under generic headings, and the skills now require *stating* the things models reliably did without saying (namespace assumptions, refusals, version assumptions). Five assertions across three suites were rewritten to test outcomes rather than one implementation; none were deleted or weakened.

### Evaluation integrity

- `run.json` is cumulative across `--skill` invocations sharing an `--out` directory; a multi-suite run can no longer be recorded as its final suite only.
- Full provenance per run and per case: git commit and dirty flag, exact argv, models, CLI version, context mode, and hashes of the skill context actually sent, the prompt, and the assertions.
- Cached cases are reused only when hashes and model settings match; stale results re-run.
- Grader responses are validated strictly — indexed verdicts, boolean `met`, non-empty evidence, raw output preserved — and a malformed grader response is a recorded, re-runnable failure rather than a zero or a hand-deleted artifact.
- Both assertion-weighted micro and equal-case macro averages are reported.
- The with-skill arm's full-context mode is labelled as the upper bound it is; a `skillmd-only` mode exists alongside it.
- **New: routing evals** (`scripts/run_routing_evals.py`, `routing/cases.json`, `ROUTING.md`) test that each skill's description fires on the right questions and stays silent on the wrong ones — 58 cases across named, symptom-only, code-only, confusable, and out-of-scope categories.

### Results, re-measured from this code

Content: 88% with skill vs 41% baseline across 41 cases (micro 87.6/41.0) — `evals-runs/baseline-v1.4.1/`. Routing: 100% correct fire, 0% misfire, 0% silent across 58 cases — `evals-runs/routing-v1.4.1/`. The 1.3.0/1.4.0 run directories remain committed as history and are labelled as such.

### Packaging

- `build.sh` stages recursively through the allowlist (nested references and future assets cannot silently vanish), errors on files the allowlist would drop, and generates checksums with `sha256sum` or `shasum -a 256`.
- `verify_dist.sh` compares each archive's inventory against the source tree file-for-file.
- `CONTRIBUTING.md` documents the full command sequence; stale six-skill wording fixed; install instructions no longer point at a GitHub release that does not exist yet.

## [1.4.0] — 2026-08-21

Four platforms added, taking the set from six to ten. Each is written against first-party documentation only, and each names what its vendor does not document rather than filling the gap with a guess.

### New skills

- **`hubspot-hubl`** — HubSpot marketing email. HubL is Jinjava, not Liquid and not stock Jinja2, and the fact that reorganizes everything is HubSpot's own: filters apply to personalization tokens on CMS and blog pages, *not in email*. So `{{ contact.firstname|default("there") }}` is wrong in an email and `{{ personalization_token("contact.firstname", "there") }}` is right. Also covers programmable email and `isEnabledForEmailV3Rendering`, `crm_objects()` returning a wrapper you have to iterate as `.results`, single-send `customProperties` not working inside `if`, and the two first-party limit statements that do not reconcile — 10 function invocations per function against 5 CRM functions with 500k–100k recipient ceilings. Both are cited, and the disagreement is stated rather than resolved.
- **`moengage-jinja`** — MoEngage. One rule governs the platform: *"when a message contains a null value, it will not be sent."* A missing attribute does not render blank, it removes that user from the send, so the skill is built around the five documented fallback forms and the fact that only `{% MOE_NOT_SEND("reason") %}` produces a labelled analytics row. Also covers the `UserAttribute` / `EventAttribute` / `ProductSet` / `ContentApi` namespaces, autoescape being off, the Content API's 5-second timeout and three retries, and the editor behaviour that corrupts a template *after* it saved cleanly — Froala HTML-encoding `<` and `>`, BeautifulSoup rewriting the markup on save, and a `{% for %}` that must wrap a complete `<tr>`.
- **`sailthru-zephyr`** — Sailthru, now sold as Zeta Engage by Sailthru. Zephyr shares its syntax with nothing else in this repository: single braces, `{if}…{/if}`, `{foreach x as c}`, no filter pipe at all — functions only — and a space after the opening brace stops it evaluating. Covers the `{{double}}` versus `{single}` creation-time/send-time distinction, the Elvis default idiom, Java `SimpleDateFormat` dates with no timezone control, prices as integer cents, `filter_content()` versus the `filter()`/`dedupe()` pair that destroys Recommendations pinning, `sort()` mutating the global content array, and the asymmetry that matters most in production: `assert()` and `cancel()` suppress a campaign send but neither stops a Lifecycle Optimizer flow.
- **`zeta-zml`** — the Zeta Marketing Platform. ZML is Liquid-derived and its documentation is public. Covers the tag set (`resources`, `recommendation`, `event`, `feeds`, `media_asset`, `coupon`, `segments`, `skip_message`), the filter catalogue as currently published, `elsif` — Zeta's docs note the missing 'e' is intentional — the `liquid_internal` / `custom_skip` / `email_subject_missing` error categories, and the silent failures that are the whole point of the skill: `BETWEEN` inside `{% resources %}`, and lowercase operators where `CONTAINS`, `AFTER`, `BEFORE`, `NOT` and `EXISTS` must be uppercase.

### One vendor, two languages

Zeta Global ships both of the last two. Zeta Marketing Platform speaks ZML; Zeta Engage by Sailthru speaks Zephyr. They share no syntax. Both skills name the other platform as explicitly out of scope in their trigger descriptions, and `zeta-zml` carries an eval case for the routing boundary itself — someone pasting single-brace Zephyr and saying "Zeta" should be asked which platform, not have their syntax silently "corrected".

### Repository

- The shared trust-boundary block now takes a full per-platform sentence rather than a mechanism name spliced into a fixed one. Four of the ten platforms have **no** documented construct that executes a stored string as template code, and the old wording asserted one did. The section is now accurate on all ten: where there is an eval mechanism it is named, and where there is not, the exposure is stated as what it actually is — unescaped output.
- `shared/figma/` gained fragments for all four platforms. Three have a documented Email Love export route; the Zeta Marketing Platform does not, so that fragment says so and points at **Download as HTML**, including the caveat that the plugin's `unsubscribe.com` sentinel has no ZMP-specific tag to swap to.

## [1.3.0] — 2026-08-21

Release-readiness pass. Nothing about what the skills teach has been thrown away; what changed is whether the repository can be trusted to ship it.

### Release and packaging

- **The release workflow could not have worked.** It invoked `./scripts/build.sh` directly, and the file is mode `100644` in the repository, so the step would have failed with `permission denied`. It also lacked the `contents: write` permission needed to create a release. Both fixed: scripts are invoked through `bash`, validation and packaging run with `contents: read`, and only the publish job — gated on a tag, behind a `release` environment — gets write access.
- **Added `.github/workflows/ci.yml`.** Pull requests and pushes to `main` now validate, package, and verify the archives with no permission to publish anything.
- **Every GitHub Action is pinned to a full commit SHA**, and `persist-credentials: false` is set on checkout.
- **`scripts/build.sh` rewritten.** Files are staged through an explicit allowlist instead of zipped in place, symlinks under `skills/` abort the build, the archive count is asserted, and `dist/SHA256SUMS` is generated.
- **`scripts/verify_dist.sh` added** — zip integrity, file inventory, no entries outside the skill directory, no symlinks or executables, and checksum verification.
- **Every archive now contains the MIT licence.** Previously the licence lived only at the repository root, so a distributed `.skill` carried none.
- **Eval suites now ship inside the archives**, which the README already claimed.

### Versioning and installation

- **`VERSION` is now the single source of truth.** The validator fails if the marketplace manifest or `CHANGELOG.md` disagrees with it, and the release job fails if the tag does not match. Previously the changelog said `1.3.0` while all six marketplace entries said `1.0.0`.
- **Install instructions rewritten per platform** — Claude Code, the Claude apps, ChatGPT, and Codex each get their own tested route, plus what updating and removing actually does for a manually uploaded skill.
- **Added a "choose your skill" table** with one starter prompt per platform.
- The Claude Code path is verified end to end against CLI 2.1.238: marketplace resolves, plugin installs at the version in `VERSION`, roughly 370 tokens always-on and 5.1k on invocation.

### OpenAI metadata

- All six `agents/openai.yaml` files used `interface.name` and `interface.description`, which are not in the schema. They now use `display_name` and `short_description`, and every `default_prompt` explicitly references its skill as `$skill-name`.
- The `brand_color: "#FF4D6D"  # TODO` placeholder is removed rather than guessed at. The key is optional; it can come back when there is an approved value.
- The validator now checks this schema, including the 25–64 character `short_description` range.

### Correctness and safety

- **Iterable escaping is now context-aware.** The skill previously recommended triple braces — unescaped output — as the default for URLs, product names, apostrophes, and ampersands. That is only defensible for markup you authored, and these values arrive from profiles, events, feeds, and catalogs. The claim that escaping "breaks" apostrophes and ampersands in HTML was checked against Iterable's documentation and does not hold; it is narrowed to the surfaces where it is real, and the guidance now separates HTML text, HTML attributes, URL components, JavaScript, and JSON, names `urlEncode` and `toJson`, and says to validate links that come from data.
- **Every skill gained a "Handling untrusted content" section.** Pasted templates, comments, payloads, feed records, and URLs are data, not instructions; anything with a side effect needs the user to ask for it in this conversation; secrets and production recipient data stay out of templates and replies.
- **Dynamic template evaluation now has a stated trust boundary** in every skill — `render_liquid`, `:rerender`, `TreatAsContent`, `#evaluate`, `|safe` and `autoescape off`. Author-controlled content only, and turning HTML escaping off is explicitly not JSON or JavaScript encoding.
- **The Customer.io unsubscribe contradiction is documented rather than papered over.** The skill said `{{unsubscribe_url}}` renders empty; the Figma reference quoted Email Love's help centre saying the plugin injects exactly that. Customer.io's own documentation confirms the skill is right, which makes the plugin behaviour a real question that needs one export to settle. It is now a stated release blocker in the README and in the Figma reference, with the exact test.
- Fixed a snippet-syntax error the Customer.io Figma reference had been carrying: `{% snippet "name" %}` is not a Customer.io construct; it is `{{snippets.name}}`.
- Every copy-ready example uses HTTPS.

### Evaluations

- **One documented schema**, enforced by the validator: kebab-case ids, a category, an expected output, and at least five objectively checkable assertions per case. Marketo and SFMC previously had no expected outputs and no assertions at all; Braze, Customer.io, and Klaviyo had prose but nothing checkable.
- **Every suite now has an adversarial case** carrying injected instructions in HTML comments, template comments, JSON values, and URL parameters, plus that platform's dynamic-evaluation boundary.
- **`scripts/run_evals.py` added** — paired with-skill and baseline arms, a grader pass per assertion, and a resumable run directory recording model, grader model, CLI version, settings, timestamps, both raw responses, and per-assertion evidence.
- **The README's six 100% scores are gone.** They could not be reproduced from anything in the repository. In their place: a real run committed at `evals-runs/baseline-v1.3.0/` — 83% with skill against 50% baseline across 25 cases — described as a smoke test rather than a benchmark, with the caveats stated.

### Validation

- `scripts/validate.py` rewritten. It previously regex-checked two frontmatter fields and passed a repository with invalid OpenAI metadata, inconsistent versions, and an unresolved TODO. It now parses YAML properly and checks name and description constraints, reference and relative-link targets, the OpenAI schema, the eval schema, the marketplace manifest, version agreement, symlinks and executable bits, credential-shaped strings, placeholders, plain-HTTP URLs, workflow permissions, and SHA pinning.
- **`scripts/sync_shared.py` added.** The Figma reference and the security section are generated into all six skills from `shared/`, so the packages stay self-contained without the copies silently drifting. CI runs it with `--check`.

### Documentation

- `EVALS.md` added: schema, how to run, what gets recorded, the committed run, and its limitations.
- A "Known limitations" section in the README, and a beta designation on the repository and on every skill in the table.
- Each `SKILL.md` carries the date its platform claims were last checked.

## [1.2.0] — 2026-08-20

### Added

- **`sfmc-ampscript`** — write, review and debug AMPscript, Guide Template Language and personalization strings in Salesforce Marketing Cloud.
  - Frames the three languages (AMPscript, SSJS, GTL) and when each applies, and the **two independent substitution engines** — `%%…%%` is case-insensitive and resolved by the email compiler, `{{…}}` is case-sensitive and resolved by Journey Builder beforehand.
  - Leads with the platform's defining behaviour: a personalization mistake usually means the message is **never built**. Errored/NotSent, no MTA, no bounce.
  - Documents the rowset emptiness trap (`Empty()` and `IsNull()` both return false on an empty rowset — only `RowCount()` works), that `IIf()` is not short-circuiting, that AMPscript has no arithmetic operators, and that Salesforce's own docs have `DateDiff`'s argument order backwards.
  - Full send error code table, the NotSent Tracking Extract workflow, and the silent exclusions that produce no error and no delivery.
  - Validated at 100% vs a 48% no-skill baseline.

- **`marketo-velocity`** — write, review and debug personalization in Adobe Marketo Engage.
  - Separates the two mechanisms — tokens and Velocity email scripting — which have opposite null handling and opposite HTML encoding, and names the five things that force the switch to Velocity.
  - Documents that `:default=` silently does nothing on Email Script tokens, and that `$display.alt` never fires on a lead field because Marketo lead fields are empty strings rather than null.
  - Records the **reserved-word trap**: every Marketo email is assembled through Velocity, so `#end` in a URL fragment or body copy breaks an email containing no scripting at all.
  - Covers the SOAP-API field-naming rule, custom object retrieval limits, the three ways Velocity breaks link tracking, and that `$TriggerObject` in a batch campaign fails the send.
  - Validated at 100% vs a 46% no-skill baseline.

### Changed

- `README.md` — added both skills, replaced the results table with all six measured deltas sorted by gap, and added the Klaviyo documentation quotes so that claim stands without running the API test.

## [1.1.0] — 2026-08-19

### Added

- **`klaviyo-django`** — write, review and debug personalization in Klaviyo templates.
  - Documents that Klaviyo runs the **Django** template language, not Liquid, with the four Liquid idioms that hard-error (`{% elsif %}`, `{% assign %}`, `.size`, a space after a filter colon) verified against Klaviyo's `/api/template-render` endpoint.
  - `references/data-sources.md` carries the per-integration cart paths for Shopify, WooCommerce, BigCommerce, Magento 1 and Magento 2 — which do not follow a pattern and cannot be derived from one another.
  - Covers the three failure classes: missing property → silent blank, malformed tag → nothing renders, catalog/coupon miss → send skipped.
  - Validated at 100% vs a 76% no-skill baseline.

- **`braze-liquid`** — write, review and debug Liquid personalization in Braze.
  - Covers the `${}` variable syntax, the restriction on where filters and operators may appear, and the absence of parentheses in conditionals.
  - Connected Content in full: `:save` scope, `__http_status_code__`, the 2-second timeout, retry-vs-abort precedence, and the cache key that excludes the user.
  - Records that `{% cancel_message %}` does not exist and that `to_json` is `as_json_string`.
  - Full Currents `abort_type` enum and the Message Activity Log's 60-hour retention and sampling caps.
  - Validated at 100% vs a 57% no-skill baseline.

- **`customerio-liquid`** — write, review and debug Liquid personalization in Customer.io.
  - Documents the two Liquid engines (legacy Ruby vs latest LiquidJS), set per message, and what silently changes between them — `escape` no longer URL-encoding, timezone offsets moving from hours to minutes.
  - Leads with the platform's most consequential behaviour: a missing attribute **fails the send** rather than rendering blank, while a wrong namespace renders empty and sends anyway.
  - Namespace rules for `customer`, `event`, `trigger`, `objects`, `journey`, including the singular-vs-plural slug split for object-triggered workflows.
  - Validated at 100% vs a 39% no-skill baseline — the largest gap in the repo.

### Changed

- `README.md` — corrected the Klaviyo entry, which previously described it as Liquid. Added per-skill baseline results rather than an average.
- Each skill now ships an optional `agents/openai.yaml` for ChatGPT presentation metadata. Claude ignores it; the same folder works on both platforms.

## [1.0.0] — 2026-08-19

### Added
- `iterable-handlebars` — write, review and debug Handlebars personalization in Iterable templates.
  - `references/helpers.md` — Iterable's helper set with exact argument order, plus what standard Handlebars is **not** supported (`{{#with}}`, partials, `../`, custom helpers, inverse blocks).
  - `references/data-sources.md` — profile vs event precedence, the three `shoppingCartItems` paths, catalogs, data feeds and the `[[ ]]` / `{{ }}` merge setting, snippets, built-in merge tags.
  - `references/troubleshooting.md` — symptom → cause → fix, send-skip reason codes, Preview workflow, pre-ship review checklist.
  - Validated at 100% vs a 52% no-skill baseline.
