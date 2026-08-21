# Changelog

All notable changes to the skills in this repo.

## [1.3.0] — 2026-08-20

### Added

- **`references/figma-export.md` in all six skills** — how to apply each platform's personalization language inside a Figma file built with the [Email Love plugin](https://www.emaillove.com/figma-plugin) so that it survives export to production HTML. Covers where code can go (text layer, Code Block, link field, Head of email, override image source), the nesting rule for paired Code Blocks, and the platform-specific behaviour of each export target.
- **A "In Figma, with the Email Love plugin" section in every `SKILL.md`**, carrying the three rules that break emails if missed, plus one platform-specific line.
- Figma, Email Love, and `mj-raw` added to every skill's trigger description.

### Verified

Two findings in the new reference were compiled and measured on MJML 4.18 rather than inferred from documentation:

- **Paired Code Blocks are safe if and only if they are siblings.** A pair spanning two nesting levels, with the condition false, leaves three orphaned `</table>`, `</tr>`, and `</td>` tags and an Outlook conditional-table depth of `-2`. The same pair as siblings — wrapping a two-column section, a wrapper, and a full-width section at once — is balanced on every tag at depth `0`. This confirms and explains the plugin's own documented rule.
- **A double-quoted string argument in a link field silently truncates the link.** `href="https://x.com/{{ slug|default:"home" }}"` raises `Attributes home", }}" are illegal` under strict validation and, under MJML's default soft validation, compiles without complaint to `href="https://x.com/{{ slug|default:"`. This lands hardest on Klaviyo and SFMC, whose own documentation uses double quotes.

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
