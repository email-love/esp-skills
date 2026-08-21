# Iterable Handlebars — Troubleshooting

Symptom → cause → fix, plus the send-skip reason codes and how to reproduce a problem in Preview.

## Contents

1. [Symptom lookup](#1-symptom-lookup)
2. [Send-skip reason codes](#2-send-skip-reason-codes)
3. [The constructs that stop a send](#3-the-constructs-that-stop-a-send)
4. [Escaping and character issues](#4-escaping-and-character-issues)
5. [Whitespace and URL corruption](#5-whitespace-and-url-corruption)
6. [Data feed rendering failures](#6-data-feed-rendering-failures)
7. [WYSIWYG editor issues](#7-wysiwyg-editor-issues)
8. [Reproducing a bug in Preview](#8-reproducing-a-bug-in-preview)
9. [Limits of proof sends](#9-limits-of-proof-sends)
10. [Review checklist](#10-review-checklist)

---

## 1. Symptom lookup

### Blank where a value should be

| Cause | Check | Fix |
|---|---|---|
| Field name case wrong | Open the user's profile and read the exact key | Match the case exactly |
| Field name has a space, period, or leading digit | Look at the raw field name | Bracket notation: `{{[First Name]}}` |
| Field genuinely empty on this profile | Preview against the affected user | `{{defaultIfEmpty field "fallback"}}` |
| Expecting an event field in a blast campaign | Campaign type | Blasts have no event context — use a profile field |
| Event overwrote the profile value with an empty one | Compare event payload to profile | `{{profile.fieldName}}` |
| Data feed field, wrong brace style | Template's "Merge the Data Feed and User Contexts" setting | Match braces to the setting — see §6 |
| Value is `0`, `false`, or `[]` inside an `{{#if}}` | These are **falsy** in Iterable | Test existence differently, e.g. `{{#ifGte (defaultIfEmpty qty 0) 0}}` |

### Literal `{{firstName}}` visible in the sent message

| Cause | Fix |
|---|---|
| Mismatched or missing braces | Count them; `{{{` must close with `}}}` |
| Handlebars placed in a field that doesn't render it | Check the surface supports personalisation |
| A merge tag accidentally wrapped in an HTML comment by the WYSIWYG editor | See §7 — never comment out value-producing tags |
| Typo in a helper name | Iterable renders unknown helpers unpredictably — verify against `helpers.md` |

### `&#x27;`, `&amp;`, or a broken link in the output

Double braces HTML-escape. Any value containing an apostrophe, ampersand, or HTML needs `{{{triple braces}}}`. This is the single most common cosmetic bug — see §4.

### Raw HTML tags showing as text

The inverse: a snippet or HTML field rendered with `{{ }}`. Switch to `{{{ }}}`.

### Message never arrived for some recipients

This is a send skip, not a rendering bug. Go to §2 and §3, and check the affected user's **Event History** tab for the skip reason.

### Template won't save

Unbalanced block helpers — an opening `{{#if}}` without its `{{/if}}`, or a mismatched helper name on the close tag. Iterable validates block balance at save time, so this fails loudly and is quick to find.

### Wrong value rendering (right field, wrong data)

Event fields override same-named profile fields at send time. Use `{{profile.fieldName}}` to force the profile value. Also check whether a data feed with merged contexts is colliding — on a merge, the **user profile wins** over the feed.

---

## 2. Send-skip reason codes

Found on the user profile → **Event History** tab, in the `reason` field of a send skip event.

| Reason | Meaning | Where to look |
|---|---|---|
| `HandlebarsExecutionError` | The Handlebars expression was invalid **after** merge tags were applied | A comparison helper or `#ifContainsStr` hit a null/missing field — see §3 |
| `DataFeedError` | Feed returned a non-200 response | Feed URL, auth, the dynamic URL's merge tags for that user |
| `RetriesExhaustedError` | Feed didn't respond within 10 seconds across 5 attempts | Feed performance; consider enabling caching |
| `InvalidHostedUnsubscribeUrl` | Hosted unsubscribe URL wasn't a valid URL after rendering | Query-string construction — `&` vs `?`, unencoded values |
| `CatalogLookupError` | `#catalog` with `required=true` found nothing | The key value on that profile; catalog contents |
| `CatalogCollectionLookupError` | `#catalogCollection` with `required=true` found nothing | Collection definition and filters |
| `MetadataLookupError` | Metadata lookup with `required=true` failed | The referenced metadata key |
| `SnippetLookupError` | Snippet with `required=true` not found | Snippet name spelling; whether it was deleted |
| `SendAborted` | An explicit `{{sendSkip}}` fired | Your own skip logic — check the `cause` you set |
| `TemplatePausedOrDisabled` | WhatsApp template paused/disabled for low engagement | WhatsApp template status |

`HandlebarsExecutionError` affecting only *part* of a list is the signature of a null-guard problem: the template is fine for users who have the field and fails for users who don't.

---

## 3. The constructs that stop a send

Most Handlebars mistakes degrade to blank output. These do not — they fail the template and the message is not sent to that user.

**Comparison helpers on a non-existent or null field:**

`#lt` · `lt` · `#lte` · `lte` · `#gt` · `gt` · `#gte` · `gte`

```handlebars
<!-- fails for any user without lifetimeValue -->
{{#ifGt lifetimeValue 500}}VIP{{/ifGt}}

<!-- safe -->
{{#if lifetimeValue}}{{#ifGt lifetimeValue 500}}VIP{{/ifGt}}{{/if}}
{{#ifGt (defaultIfEmpty lifetimeValue 0) 500}}VIP{{/ifGt}}
```

**`#ifContainsStr` on an empty or missing field:**

```handlebars
<!-- fails when plan is empty -->
{{#ifContainsStr plan "enterprise"}}…{{/ifContainsStr}}

<!-- safe -->
{{#ifContainsStr (defaultIfEmpty plan "") "enterprise"}}…{{/ifContainsStr}}
```

**`required=true` lookups** on catalogs, collections, snippets, and metadata: by design, a miss skips the send. That's often what you want — better no message than a broken one — but be deliberate about it.

**Notably safe:** `#ifEq`, `#if`, `#unless`, `#each`, and plain `{{field}}` all handle nulls without failing. When you only need equality, `#ifEq` avoids the whole problem.

---

## 4. Escaping and character issues

Iterable HTML-encodes certain characters in `{{ }}` output. Apostrophes become `&#x27;`. Ampersands in URLs become `&amp;`, which breaks query strings.

**Always use `{{{ triple braces }}}` for:**

- URLs of any kind — product links, image sources, deep links
- Values that legitimately contain HTML
- Snippets you want rendered as HTML: `{{{ snippet "name" }}}`
- Product names, subject-line values, or any copy that may contain `'` or `&`

```handlebars
<!-- broken: & becomes &amp;, apostrophe becomes &#x27; -->
<a href="{{productUrl}}">{{productName}}</a>

<!-- correct -->
<a href="{{{productUrl}}}">{{{productName}}}</a>
```

**Quote nesting.** Inside a double-quoted HTML attribute or JSON value, string literals in the expression must be single-quoted:

```handlebars
<!-- broken: the inner " closes the attribute -->
<img src="{{defaultIfEmpty imageUrl "https://cdn.example.com/fallback.png"}}">

<!-- correct -->
<img src="{{defaultIfEmpty imageUrl 'https://cdn.example.com/fallback.png'}}">
```

---

## 5. Whitespace and URL corruption

Handlebars preserves every space, tab, and newline. Inside a URL, a deep link, or a JSON payload that is fatal — the link 404s or the app fails to parse the payload.

| Action | Syntax |
|---|---|
| Strip leading | `{{~tag}}` |
| Strip trailing | `{{tag~}}` |
| Strip both | `{{~tag~}}` |

```handlebars
<!-- the newlines inside this block end up inside the href -->
<a href="{{#if isVip}}
  https://example.com/vip
{{else}}
  https://example.com/sale
{{/if}}">Shop</a>

<!-- corrected -->
<a href="{{~#if isVip~}}https://example.com/vip{{~else~}}https://example.com/sale{{~/if~}}">Shop</a>
```

Rule of thumb: any conditional or loop that spans lines **inside an attribute value or a JSON body** needs tildes on every tag in it.

---

## 6. Data feed rendering failures

**First check: brace style vs template setting.** "Merge the Data Feed and User Contexts" governs everything.

| Setting | Correct syntax |
|---|---|
| Disabled (default) | `[[fieldName]]`, `[[#each items]]…[[/each]]`, raw HTML `[[{field}]]` |
| Enabled | `{{fieldName}}`, `{{#each items}}…{{/each}}`, raw HTML `{{{field}}}` |

The setting applies to **all** feeds in the template — it can't be toggled per feed. A template that mixes `[[ ]]` and `{{ }}` for feed data will only half-render.

**Second: is the feed actually returning data for this user?** Preview loads attached feeds and shows what came back. Dynamic feeds whose URL is built from merge tags fail per-user when the profile lacks the field the URL needs.

**Third: check the reason code.** `DataFeedError` means non-200. `RetriesExhaustedError` means slower than 10s across 5 attempts.

**Name collisions.** With contexts merged, a profile field with the same name as a feed field wins. Use the feed's alias — `{{alias.fieldName}}` — to disambiguate.

**Caching.** Responses are cached for 1 hour, non-configurable. If you just fixed the feed and the old data is still rendering, that's why.

**Empty results.** Handle them explicitly rather than mailing an empty grid:

```handlebars
{{#if items}}
  [[#each items]]…[[/each]]
{{else}}
  {{sendSkip cause="empty recommendation feed"}}
{{/if}}
```

---

## 7. WYSIWYG editor issues

The visual editor can mangle Handlebars that isn't wrapped in HTML comments. Iterable's documented pattern is to comment out **non-outputting** Handlebars:

```handlebars
<!--{{#if [First Name]}}-->
    Hi, {{[First Name]}}!
<!--{{/if}}-->
```

**Only comment lines that don't output a value** — conditionals, loop openers, closing tags. Never comment a tag that produces output like `{{email}}` or `{{firstName}}`; it will be sent as a literal HTML comment and the value will vanish.

If a template is heavily Handlebars-driven, editing the HTML directly rather than through the WYSIWYG avoids this class of problem entirely.

---

## 8. Reproducing a bug in Preview

**Content → Templates → (overflow menu) → Preview with data**, or open the template and click **Preview**.

1. Enter the email address (or `userId`, for userId-based projects) of a user who actually experienced the problem, then **Load user data**.
2. Edit the loaded values in place to test edge cases. This does **not** modify the real profile — so blanking `firstName` to check a fallback is safe.
3. Attached data feeds load here too, and their returned values are editable. Feeds with aliases display alongside their data.
4. For dynamic feeds, preview with a profile whose fields satisfy the feed URL.
5. Push and in-app: the **Raw data (JSON)** panel shows the payload with Handlebars rendered. Load user data first or the expressions stay unresolved.
6. Email: device previews across clients and OSes. Previews show **destination URLs, not tracked links** — tracked links may be longer or shorter, which matters if you're debugging length limits.

Edge cases worth testing on any personalised template: a profile missing the key field; a numeric field equal to `0`; an array with one element and with many; a value containing an apostrophe; and, for triggered campaigns, a user who has genuinely fired the event.

---

## 9. Limits of proof sends

Proofs go to yourself, an internal list, random users from a list, or another address. A proof to yourself resolves Handlebars against **your own** Iterable profile — which is why proofs often look fine when the campaign is broken for real users.

Known proof limitations:

- `{{viewInBrowserUrl}}` and `{{unsubscribeUrl}}` do **not** behave as they do in a real send.
- Selective In-App and Push settings are ignored.
- Email proofs may not reflect final live-send size — a proof that looks unclipped can still clip in Gmail on a live send.

For personalisation bugs, Preview against the affected user beats a proof to yourself.

---

## 10. Review checklist

Run this over any Iterable template before it ships.

**Sends at all**

- [ ] Every `#lt` / `#lte` / `#gt` / `#gte` (and bare forms) is guarded by an outer `{{#if}}` or `defaultIfEmpty`
- [ ] Every `#ifContainsStr` is guarded the same way
- [ ] `required=true` appears only where skipping the send is genuinely preferable
- [ ] Data feed empty-result case is handled

**Renders correctly**

- [ ] Every URL and image src uses `{{{ }}}`
- [ ] Every value that might contain `'` or `&` uses `{{{ }}}`
- [ ] Snippets use `{{{ snippet "name" }}}` where HTML should render
- [ ] String literals inside double-quoted attributes are single-quoted
- [ ] Conditionals inside URLs use `{{~ ~}}` whitespace control
- [ ] Prices go through `numberFormat … "currency"`
- [ ] Date comparisons use a numeric-only format and a pinned `tz`

**Data is right**

- [ ] Field names match the profile exactly, including case
- [ ] Fields with spaces/periods/leading digits use bracket notation
- [ ] Cart data uses the right path for the context: `profile.shoppingCartItems` vs `updatedShoppingCartItems` vs `shoppingCartItems`
- [ ] Event fields are only used in triggered or journey campaigns
- [ ] Data feed braces match the template's merge-contexts setting
- [ ] Channel-restricted tags (`{{sentAt}}`, `{{viewInBrowserUrl}}`) are only in email

**Verified**

- [ ] Previewed against a user with the field populated
- [ ] Previewed against a user with the field missing or empty
- [ ] Block helpers are balanced (the template saves)

---

## Sources

Iterable Support: [Troubleshooting Handlebars Code](https://support.iterable.com/hc/en-us/articles/36530857619348) · [Reasons for Send Skip Events](https://support.iterable.com/hc/en-us/articles/360021169631) · [Troubleshooting Campaigns](https://support.iterable.com/hc/en-us/articles/360023927232) · [Previewing Templates with Data](https://support.iterable.com/hc/en-us/articles/115002807783) · [Sending Proofs](https://support.iterable.com/hc/en-us/articles/360044426191) · [Conditional Logic Helpers](https://support.iterable.com/hc/en-us/articles/115003884806) · [Using Data Feeds in Templates](https://support.iterable.com/hc/en-us/articles/39206002278932)
