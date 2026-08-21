## Braze specifics

**Braze mixes two syntaxes and both survive export unchanged.** `{{ ${first_name} | default: 'there' }}` — Liquid on the outside, Braze's `${...}` attribute reference on the inside — goes straight into a text layer. Note that Braze's documented default filter uses single quotes, so unlike Klaviyo's, it is also safe in a link field.

**Content Blocks strip the `<head>`, and that takes your Head-of-email code with it.** "When exporting as a content block, the plugin strips out the `<head>`, `</body>`, and `</html>` tags." So any `{% assign %}` or `{% capture %}` you put in the **Head of email** field is gone from a Content Block export, along with every `@media` query and embedded style. Put Liquid that later blocks depend on in a body-level Code Block instead, and add the CSS directly to the template in Braze.

**Reference a Content Block with `{{content_blocks.${your_block_name}}}`** in a Code Block, wherever the block should appear.

**Liquid does have a head-safe declaration form**, unlike Django: `{% assign %}` is not scoped to a block, so a declaration in the **Head of email** field is still in effect in the body. Just remember the Content Block caveat above — that field's contents do not survive a Content Block export.

**Content Blocks work best single-column.** Multi-column content dropped into an arbitrary template needs its own testing.

**The localization checkbox does not tag Code Blocks.** With "Add localization tag" enabled, the plugin wraps text content in `{% translation %}` tags and gives each element a unique ID — headings, paragraphs, buttons, footer text. "Tags are only applied to text content. Images and code blocks are not tagged." So copy you wrote inside a Code Block is invisible to Smartling, Lokalise, or Crowdin. If a conditional branch contains real copy, put the copy in ordinary text components between the Code Blocks rather than inside them — which is what the nesting rule wants anyway.

Worth testing once on your own file: a text layer that carries both Liquid and a `{% translation %}` wrapper is a nesting the plugin's docs do not describe.

**Unsubscribe is merged automatically and the export fails without a footer.** To pin it yourself, type `{{${email_unsubscribe_url}}}` into the link field.

**Braze implements Liquid 5 partially.** `{% render %}` and `{% include %}` are not available — Content Blocks are the substitute, and they are referenced, not included. Nothing about designing in Figma changes that; it just means the workaround a general model reaches for will not work and will not say so.

**`{% abort_message %}` cancels the send.** Placed in a Code Block it will do so silently as far as Figma is concerned — the design looks complete and the message never arrives.
