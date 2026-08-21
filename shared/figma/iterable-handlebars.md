## Iterable specifics

**Structural Handlebars goes in paired Code Blocks; inline Handlebars does not have to.** `{{#if firstName}}{{firstName}}{{else}}there{{/if}}` opens and closes inside one string, so it belongs in the text layer. `{{#each catalogCollection}}` … `{{/each}}` wraps designed content, so it needs two Code Blocks at the same nesting level, with the repeating design in the column between them.

**Snippets: use `{{snippet "your-snippet-name"}}`, in a Code Block.** Note a discrepancy in Email Love's own docs — the [dynamic content](https://help.emaillove.com/plugin/components/dynamic-content) page shows `{{#inApp "content_block_name"}}{{/inApp}}` for Iterable snippets, while the [Iterable export](https://help.emaillove.com/plugin/export/iterable) page shows `{{snippet "your-snippet-name"}}`. The export page matches Iterable's documented snippet syntax; use that one.

**A snippet cannot carry its own CSS.** Iterable's Snippet API stores markup only, so custom fonts, animations, and media queries in the snippet do nothing. Email Love's documented fix is to export the snippet section as a full email once, copy the CSS out of the exported `<head>`, and paste it into the Properties section of every template that uses the snippet — which is what the **Head of email** field is for. Standard text, images, buttons, and layout need none of this.

**Handlebars has no declaration form to hoist**, so the **Head of email** field is for CSS only — which, per the snippet note above, is exactly what it is needed for.

**The Snippet API connection is separate from the Template API connection**, and has to be connected even when template exports already work.

**Unsubscribe is handled for you, and the export fails without it.** "You will need to use an Email Love Footer with an Unsubscribe link for the export to work. We will automatically merge in the Iterable Unsubscribe token." To pin a specific tag instead, type `{{hostedUnsubscribeUrl}}` into the link field and the plugin preserves it.

**Exports upsert.** Iterable is the one platform here where re-exporting updates the template in place rather than creating a duplicate — the frame's base name becomes the `clientTemplateId`. That makes Figma a genuine source of truth, and it makes editing directly in Iterable a real drift risk.

**Multi-locale is a frame-naming convention.** `{Base Name} - {locale}`, with **space-dash-space** as the delimiter and an ISO-style locale code. `Welcome_Email-en-US` does not parse; `Welcome Email - en-US` does. Every locale must already exist under Project Settings → Locales or the export fails for that locale, and **every locale frame needs its own footer** — the unsubscribe link is not carried over from the default variant. Personalization tokens are kept per variant, so a locale can carry different tags.

**Iterable is handlebars.java, not JavaScript Handlebars**, and the helpers that exist are a shorter list than a general model will offer you. That does not change in Figma — but it does get worse, because nothing between your Figma text layer and a live send will reject a helper that does not exist. It saves, it exports, it uploads, and it fails at send time.

**Handlebars comments do not belong in a Code Block.** Iterable does not document `{{!-- --}}`, and an HTML comment placed in a Code Block ships to the inbox rather than being stripped.
