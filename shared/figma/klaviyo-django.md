## Klaviyo specifics

**Klaviyo runs Django, and Figma removes the one safety net you had.** In Klaviyo's own editor a bad tag comes back as an HTTP 400 from the render endpoint. Exported from Figma, the same tag rides into a template and only surfaces when you preview with a profile — or when the send goes out. The two that are hard errors rather than empty output are `{% elsif %}` (it is `{% elif %}`) and `{% assign %}` (there is none — use `{% with %}`). Those, the colon-spacing rule below, and `{{ items.size }}` rendering empty were all verified against Klaviyo's `/api/template-render` endpoint rather than read off a docs page; `references/troubleshooting.md` has the detail.

**`{% with %}` is a paired construct, so the nesting rule catches it too.** `{% with total=items|length %}` … `{% endwith %}` must be two Code Blocks at the same level, exactly like `{% if %}` / `{% endif %}`.

**The double-quote trap lands squarely on Klaviyo.** Klaviyo's documented default filter is written `{{ person.first_name|default:"there" }}`, and that is exactly right in a **text layer**. Put the same string in a **link field** and MJML truncates the href at the opening quote and ships a broken link with no error. In a link field write `default:'there'`.

**And the colon spacing is fatal in both places.** `{{ p|lookup: 'Name' }}` — with a space after the colon — is an HTTP 400. That form appears in Klaviyo's own custom-objects documentation. Write `{{ p|lookup:'Name' }}`.

**`{{ items.size }}` renders empty rather than erroring.** It is `{{ items|length }}`. Silent-empty is the common Klaviyo failure mode in Figma, because an empty string in an exported template looks like missing data rather than broken code.

**Django variable names cannot contain spaces or hyphens.** A Figma text layer reading `{{ person.Favorite-Color }}` fails. Klaviyo property names with hyphens need `{{ person|lookup:'Favorite-Color' }}`.

**The preference centre is text-matched, and unsubscribe is not.** Any text in the design reading **"preferences"** — "Manage your preferences" in a footer, for instance — is linked to Klaviyo's preference centre on export. No merge tag and no link needed. Unsubscribe works the other way round: it is matched on a link pointing at `unsubscribe.com`, whatever the words say. So a "Manage preferences" button that you also linked to `unsubscribe.com` gets the unsubscribe tag and never reaches the preference centre. Put your own URL on that text layer in the Properties tab and the plugin respects it instead.

**Nothing goes in the Head of email field except CSS.** Django has no unscoped declaration form — `{% with %}` is paired and its scope ends at `{% endwith %}`, so it cannot be opened in the head and used in the body. Every Klaviyo variable is set where it is used.

**Every export creates a new template.** "Each time you export from Figma, a new template is created in Klaviyo. You may want to periodically clean up old versions from your templates library." Iterable, by contrast, upserts. Iterate freely, then clean up the templates library.

**HTML only, deliberately.** The plugin dropped Klaviyo drag-and-drop support because it "frequently broke custom HTML code." That is the right call for personalization work specifically — a drag-and-drop editor is exactly the thing that would mangle a Code Block.

**Liquid tags only render through a campaign or flow with the event data attached.** A template previewed cold shows nothing. Test with a real profile in Klaviyo's preview tool, not by looking at the exported HTML.
