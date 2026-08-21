## Salesforce Marketing Cloud specifics

**Declarations belong in the Head of email field.** AMPscript runs top to bottom through the document, so a `%%[ VAR @tier SET @tier = AttributeValue("tier") ]%%` block has to appear before anything that reads `@tier`. In Figma the earliest point you can reach in the body is the first Code Block in the first column, which is fragile — it moves the moment someone reorders a section. The **Head of email** field (Properties / Template settings) injects raw code into the email's `<head>`, which is before the body by construction. Put declaration blocks there and the ordering stops being a design decision. Tick "Save as default for new templates" and every new template starts with them.

**A caution on the inline example in Email Love's own docs.** The [dynamic content](https://help.emaillove.com/plugin/components/dynamic-content) page gives `%%=IIF(NOT EMPTY(@firstName), @firstName, "there")=%%` as the SFMC merge tag. That is correct AMPscript, but `@firstName` is a variable — it renders empty unless something set it first. Either declare it in the Head field, or write the self-contained form in the text layer:

```
%%=IIF(NOT EMPTY(AttributeValue("firstName")), AttributeValue("firstName"), "there")=%%
```

**Never put quoted AMPscript in a link field.** AMPscript uses double quotes for every string literal, and a link field becomes a double-quoted MJML attribute — the href truncates at the first quote and MJML says nothing at its default validation level. Quote-free expressions like `%%=RedirectTo(@url)=%%` are fine. Anything with a string literal in it belongs in a Code Block as a complete `<a>` element.

**Four export toggles insert code into your HTML, and one of them is paired AMPscript you did not write.**

| Toggle | What it inserts |
|---|---|
| Content Slots | `<div data-type="slot" data-key="uniqueKeyHere" data-label="Drop Blocks or Content Here"></div>` |
| Alias Tags | `alias="Your Figma layer name"` on button, image, social, and navbar links |
| Conversion Tags | `conversion="true"` on **every** `<a>` tag |
| Impression Tags | `%%=BeginImpressionRegion("your_figma_layer_name")=%%` … `%%=EndImpressionRegion()=%%` around Row, Wrapper, and Hero layers |

Impression regions are the one to think about. They are paired AMPscript, inserted automatically around whole Row, Wrapper, and Hero layers — the same granularity your own conditionals use. A conditional whose Code Blocks are siblings of the row nests cleanly around the impression region; one placed at a different level can split the region in half. The nesting rule earns its keep here twice over.

They are also "automatically named based on your Figma layer name," which puts a layer name inside an AMPscript string literal. Whether a name containing a double quote or a `%%` breaks the export is untested — the docs' own example renders as `"your_figma_layer_name"`, lowercased and underscored, which suggests the plugin slugifies it. Treat it as a hypothesis, and keep punctuation out of Row and Wrapper layer names on an impressions-enabled export until you have checked.

**Content Slots hand editing rights to whoever opens the template in Content Builder.** Content dropped into a slot is outside your Figma design and outside your conditionals. That is usually the intent — just know that a design system you export with slots on is not the thing that sends.

**AMPscript and GTL are separate engines. Do not mix them in one Code Block.** `%%[ ]%%` and `{{#each}}` are evaluated by different substitution passes; interleaving them in the same block is the classic SFMC failure and it is no different in Figma.

**SSJS is not what the "avoid JavaScript" warning is about.** The Raw Code Component page is right about client-side script, which email clients strip or block. `<script runat="server">` is a different thing — Marketing Cloud executes it and removes it before the message is assembled, so it belongs in a Code Block like any other server-side code. It is simply harder to debug there than anywhere else, because Figma shows you nothing.

**The export uploads a template, and the unsubscribe requirement still applies:** "You will need to use an Email Love Footer with an Unsubscribe link for the export to work." The plugin's docs do not name the tag it substitutes for SFMC, so verify the Profile Center link in Content Builder on your first export.
