---
name: iterable-handlebars
description: Write, review, and debug Handlebars personalization code for Iterable email, SMS, push, in-app, and snippet templates. Use this skill whenever someone is writing merge tags or dynamic content for Iterable, asks why a personalization is rendering blank or showing raw {{curly braces}} in a sent message, is building abandoned-cart or product-recommendation loops over shoppingCartItems, catalogs, collections, or data feeds, needs conditional or date-based content in an Iterable template, hits a HandlebarsExecutionError or an unexplained send skip, or shares an Iterable template snippet and wants it checked. Trigger even when the user just says "Iterable merge tag", "why isn't my first name showing", "dynamic content in Iterable", or pastes Handlebars alongside an Iterable campaign question, without naming Handlebars explicitly. Iterable-only — do not use it for Klaviyo, Customer.io, or Braze, which use incompatible Liquid-style templating. Also covers Figma, the Email Love plugin, and mj-raw export.
---

# Iterable Handlebars

Iterable runs **handlebars.java (jknack)**, not JavaScript Handlebars. Most syntax you know carries over, but the helper set is Iterable's own and several standard idioms are missing. Writing "normal" Handlebars in Iterable is the single most common source of broken templates — so work from the helper reference in this skill rather than from memory.

The stakes are unusual for a templating language: some mistakes render blank, some render as literal `{{curlyBraces}}` in a customer's inbox, and some silently **stop the message from sending at all**. Knowing which failure class you're looking at is most of the debugging work.

## The two jobs

Most requests are one of these. Identify which before you start.

**Authoring** — someone wants dynamic content: a personalized greeting, a cart loop, a conditional block, a countdown, a recommendation grid. Go to [Writing Handlebars](#writing-handlebars).

**Debugging** — something already renders wrong, or the send skipped. Go to [Debugging Handlebars](#debugging-handlebars).

If a request is both ("here's my template, fix it and add X"), debug first — a fix that sits on top of a broken data assumption doesn't hold.

## Reference files

Read the one you need; don't load all three. Each is a lookup table, not a narrative.

| File | Read it when |
|---|---|
| `references/helpers.md` | You need exact helper names, argument order, or named arguments. **Read this before writing any helper you haven't used in this conversation** — argument order varies between helpers and guessing produces code that saves fine and fails at send time. |
| `references/data-sources.md` | You need field paths: user vs event vs profile precedence, `shoppingCartItems` variants, catalogs and collections, data feeds, built-in merge tags, snippets. |
| `references/troubleshooting.md` | You're diagnosing a symptom, decoding a send-skip reason, or want the full failure-mode catalogue. |
| `references/figma-export.md` | The email is being designed in **Figma with the Email Love plugin** and exported from there. **Read before advising on placement** — the nesting rule for paired Code Blocks, the link-field quoting trap, and the specifics of this platform's export target are all Figma-only, and none of them are visible in the plugin's preview. |

---

## Writing Handlebars

### 1. Pin down the data contract first

Handlebars can only render what's actually in scope at send time, and the most common "bug" is code that references a field that was never going to be there. Before writing anything, establish:

- **Where does this field live?** User profile, triggering event, catalog, or data feed. These have different syntax and different precedence.
- **What's the exact field name, including case?** Field names are case-sensitive. `firstName` and `FirstName` are different fields.
- **Can it be missing or empty?** For most real-world lists the honest answer is yes, and that determines whether you need a fallback or a conditional.
- **What campaign type is this?** Blast, triggered, journey. A triggered campaign has event fields; a blast doesn't. `{{liveData.*}}` only exists in journeys. `{{sentAt}}` and `{{viewInBrowserUrl}}` are email-only.

When the user hasn't said, ask — one question covering all of it beats writing code against a guess. If they can't answer (common for a customer mid-troubleshoot), write the code defensively and flag the assumption explicitly in your response so they can check it in Preview.

### 2. Write it

Reach for `references/helpers.md` for exact syntax. A few patterns worth internalising because they come up constantly:

```handlebars
<!-- Greeting with a fallback: defaultIfEmpty catches null, undefined, AND empty string -->
Hi {{defaultIfEmpty firstName "there"}},

<!-- Field name with a space needs bracket notation -->
{{[First Name]}}

<!-- URLs and any value containing HTML need TRIPLE braces, or the & and ' get escaped -->
<a href="{{{productUrl}}}">Shop now</a>

<!-- Cart loop: @index is zero-based, so add 1 for human-readable numbering -->
{{#each shoppingCartItems}}
  <tr>
    <td><img src="{{{imageUrl}}}" alt="{{name}}" width="120"></td>
    <td>{{name}} &times; {{quantity}}<br>{{numberFormat price "currency"}}</td>
  </tr>
{{/each}}

<!-- Conditional with an else branch -->
{{#if loyaltyTier}}
  You're a {{loyaltyTier}} member.
{{else}}
  Join our loyalty program.
{{/if}}
```

### 3. Guard against missing data — this is where messages get lost

Three specific constructs turn a missing field into a **send failure**, not a blank space. This is the highest-value thing to get right, because the symptom (a chunk of the list silently not receiving the campaign) looks nothing like a template bug.

```handlebars
<!-- DANGEROUS: if lifetimeValue is null or absent, the send is skipped -->
{{#ifGt lifetimeValue 500}}VIP offer{{/ifGt}}

<!-- SAFE: the outer #if proves the field exists before any comparison runs -->
{{#if lifetimeValue}}
  {{#ifGt lifetimeValue 500}}VIP offer{{/ifGt}}
{{/if}}
```

The rule: `#lt`, `lt`, `#lte`, `lte`, `#gt`, `gt`, `#gte`, `gte` against a non-existent or null field fail the template. So does `#ifContainsStr` on an empty or missing field. Wrap them in `{{#if fieldName}}`, or feed them through `defaultIfEmpty` first — `{{#ifGt (defaultIfEmpty lifetimeValue 0) 500}}`.

Everything else (`#if`, `#each`, plain `{{field}}`) degrades gracefully to blank or skipped-block.

### 4. Sanity-check the four traps

Run this pass on anything before handing it over. Each of these produces output that looks fine in the editor and breaks in the inbox.

**Escaping.** Any merge tag holding a URL, an ampersand, an apostrophe, or HTML needs `{{{triple braces}}}`. Double braces turn `'` into `&#x27;` and mangle query strings. Product names, subject lines pulled from a catalog, and every `imageUrl` and `productUrl` are the usual victims.

**Whitespace.** Handlebars preserves newlines and indentation. Inside a URL or a JSON payload that breaks it. Use `{{~tag~}}` to strip surrounding whitespace when a block spans lines inside a link:

```handlebars
<a href="{{~#if isVip~}}https://ex.com/vip{{~else~}}https://ex.com/sale{{~/if~}}">
```

**Quotes.** Inside a double-quoted HTML attribute or JSON value, string literals in the expression must be single-quoted: `src="{{defaultIfEmpty imageUrl 'https://cdn.example.com/fallback.png'}}"`. Double quotes inside double quotes break the attribute.

**Balanced blocks.** Every `{{#x}}` needs its `{{/x}}`. Iterable refuses to save an unbalanced template, so this one at least fails loudly.

### 5. Tell them how to verify

Never hand over Handlebars without saying how to prove it works — Preview is cheap and catches almost everything. Close with a short verification note naming the specific edge cases to try:

> Test in Content → Templates → **Preview with data**. Load a real user, then edit the loaded values in place (this doesn't touch their profile) to check: a user with no `firstName`, a cart with exactly one item, and a cart with six. For triggered campaigns, preview against a user who has actually fired the event.

---

## Debugging Handlebars

Work from symptom to cause. The symptom tells you which of three failure classes you're in, and each class has a small, distinct set of causes — so identifying the class first saves reading the whole template.

### Start by classifying the symptom

| What the recipient saw | Failure class | Most likely causes |
|---|---|---|
| Blank where a value should be | Field resolved to nothing | Wrong field name or case; field genuinely empty on that profile; event field expected but campaign is a blast; `[[ ]]` vs `{{ }}` mismatch on a data feed |
| Literal `{{firstName}}` in the message | Expression never parsed | Handlebars typed into a plain-text field that doesn't render it; broken/mismatched braces; a merge tag commented out by the WYSIWYG editor |
| Broken link, `&#x27;` or `&amp;` visible, mangled URL | HTML escaping | Double braces on a value containing `'`, `&`, or HTML — needs `{{{ }}}` |
| Raw HTML tags shown as text | Escaping, inverse | Snippet or HTML field rendered with `{{ }}` instead of `{{{ }}}` |
| **Message never arrived for some users** | Send skip | Comparison helper on null; `#ifContainsStr` on empty; `required=true` lookup that missed; data feed error/timeout; explicit `{{sendSkip}}` |
| Nothing renders from a data feed | Context mismatch | The template's "Merge the Data Feed and User Contexts" setting doesn't match the brace style used |
| Template won't save | Parse error | Unbalanced block helpers |

### Then confirm it against the evidence

Don't diagnose from the template alone — Iterable records what actually happened, and the record is usually decisive:

- **User profile → Event History tab** shows send skips with a `reason` field. `HandlebarsExecutionError`, `DataFeedError`, `RetriesExhaustedError`, `CatalogLookupError`, `SnippetLookupError`, `SendAborted` each point at a different cause. `references/troubleshooting.md` decodes them.
- **Preview with data**, loaded against a user who actually experienced the problem, reproduces most rendering bugs immediately.
- **The user's actual profile** settles field-name and case questions faster than any amount of reading.

Ask for whichever of these you're missing rather than guessing. "Which users didn't get it, and what does their Event History say?" is usually the fastest question in the whole process.

### Deliver the fix

State the cause in one line, give the corrected code, and explain what changed. When the same class of bug appears more than once in a template (it usually does — someone who missed one escaping issue missed all of them), fix every instance and say so, rather than fixing the one they pointed at.

If the root cause is data rather than code — the field is empty for 40% of the list, the event isn't firing — say that plainly. Handlebars can add a fallback, but it can't invent the value, and a customer is better served knowing which problem they actually have.

---

## In Figma, with the Email Love plugin

When the email is designed in Figma and exported with the [Email Love plugin](https://www.emaillove.com/figma-plugin), the language does not change. The plugin "simply inserts your templating language as raw code into the exported HTML" and validates none of it. What changes is *placement*.

- **Inline tags** — merge tags, and anything that opens and closes inside one string — go straight into the Figma text layer.
- **Anything structural** — a conditional or loop that wraps designed content — goes into paired **Code Blocks** (`mj-raw`), and the opening and closing blocks **must be siblings at the same nesting level**: both between wrappers, both between sections, or both inside the same column. A cross-level pair splices mismatched table markup and breaks the email in Outlook, on the branch you did not test.
- **A merge tag as a link destination** goes in the link field — but a **double-quoted string argument silently truncates the href**. Use single quotes there, or build the whole `<a>` in a Code Block.
- **Iterable:** `{{#if}}…{{/if}}` fits inside one text layer; `{{#each}}` needs paired Code Blocks. Snippets are `{{snippet "name"}}`, and a snippet carries no CSS of its own.

Code Blocks are skipped in the plugin's preview and invisible on the Figma canvas, so none of this shows up before export. Read `references/figma-export.md` before advising on any Figma-built email.

---

## Output style

These templates get handed to marketers, not just developers, and they get pasted into Iterable and shipped. So:

**Give complete, paste-ready code**, not fragments with `<!-- your content here -->` where the hard part goes. If you're showing a cart loop, show the table row markup inside it.

**Comment the non-obvious lines** with HTML comments (`<!-- ... -->`) — why triple braces here, why the outer `#if` guard, what `@index` is doing. Iterable doesn't document Handlebars-native comment syntax, so HTML comments are the safe choice in template bodies — just keep them short, since they ship in the sent message and count toward Gmail's clipping threshold. The comments are why a customer can maintain this after you're gone. Don't comment the obvious.

**Explain briefly in prose what the code does and the one thing most likely to break it.** A marketer needs to know that this loop assumes `shoppingCartItems` is on the profile, and that abandoned-cart events use a different path.

**Flag your assumptions.** If you assumed a field name, a campaign type, or a data source, say so in a line at the end. Being wrong about a field name is fine and easy to fix; being wrong silently is what produces a bad send.

**Match the depth to who's asking.** A one-line merge-tag question gets a one-line answer plus the gotcha. A "build me an abandoned cart email" gets the full treatment. Don't pad a small answer with the whole checklist.
