## Marketo specifics

**Velocity cannot go in a Code Block, because it cannot go in an email body at all.** This is the first thing to say to anyone doing Marketo work in Figma, and it is the opposite of what the workflow suggests. Velocity lives only inside an **Email Script My Token** on a program or campaign folder. What goes into the Figma design — text layer or Code Block — is the *reference*, `{{my.script name}}`, and nothing else. Email Love's docs point at "Marketo tokens and Velocity scripting" together; only the first half is something you author in Figma.

So the split is:

| In Figma | In Marketo |
|---|---|
| `{{lead.First Name:default=there}}` in a text layer | — |
| `{{my.Event Date}}` in a text layer | The My Token's value |
| `{{my.Order Table}}` in a Code Block, if it emits markup | The Email Script token holding the Velocity |

And the email must be a child of the program that owns the token, or inherit it from a marketing folder — otherwise `{{my.Order Table}}` arrives in the inbox as that literal string.

**The reserved-word trap is much easier to hit in Figma, and it breaks emails containing no scripting at all.** Every Marketo email is assembled through Velocity, so these thirteen strings are fatal *anywhere* in the email:

```
#if  #else  #elseif  #foreach  #end  #set  #define
#macro  #include  #parse  #break  #stop  #evaluate
```

In Figma that means two specific places nobody checks:

- **A link field.** `example.com/legal/#end-user-privacy-policy` is a perfectly ordinary URL that fails Marketo template validation. Percent-encode the first character after the `#`: `#%65nd`, `#if` → `#%69f`.
- **Body copy in a text layer.** "all the way to the #end" does it. Insert a word joiner: `#&#8288;end`.

Figma layer names are safe — they are not exported. Link URLs and visible text are not.

**Marketo is the one platform here where the double-quote trap does not bite.** `{{lead.First Name:default=there}}` carries no string literal, so it is safe in a link field as written. `{{ var }}` is one of the shapes the link validator accepts.

**But My Token URLs have their own collision with the plugin.** Marketo's rule is to store the URL *without* the protocol and write `https://{{my.My URL Token}}` in the email, because putting `https://` inside the token value breaks click tracking. The plugin, meanwhile, completes bare domains to `https://` and strips the `https://` that Figma adds in front of a merge tag. Whether `https://{{my.My URL Token}}` survives that intact is not documented either way — verify it once on a test export, and if it does not, build the `<a>` element in a Code Block where passthrough is exact.

**Exporting from Figma fixes Marketo's preheader limitation.** Marketo's own guidance is that tokens do not work in the preheader when using Marketo's email editor — "to use a token in the preheader, it must be via your own HTML in an email template." An Email Love export *is* your own HTML in an email template, with the preheader written into it. So a token typed into the plugin's preheader field should work where the same token typed into Marketo's editor does not. Worth confirming on a first send, and worth telling the customer about, because it is a real limitation lifted rather than a workaround.

**Nothing goes in the Head of email field.** Velocity is not authored in the email at all, and tokens are substituted wherever they appear — there is no declaration step to hoist. Use the field for CSS if you use it at all.

**Templates must be approved before use.** Design Studio → Email Templates → open → **Approve and Close**. A template sitting in Draft does not appear when creating a new email, and that is the most common "my export didn't work" report.

**The plugin maps Email Love components to Marketo editable regions**, so a marketer can edit text and images in Marketo without touching the layout. Code Blocks are not Email Love components — which means your conditional wrappers and token references are not editable in Marketo's editor. That is the behaviour you want. It also means a plain Figma frame, rather than a real component, produces a region nobody can edit; if editable areas do not show up in Marketo, that is the cause.

**A Velocity token renders as its raw token name in View as Web Page and Forward to a Friend.** Nothing about Figma changes it, but it is worth saying up front to anyone building a web-view-heavy template, because it looks like an export bug and is not.
