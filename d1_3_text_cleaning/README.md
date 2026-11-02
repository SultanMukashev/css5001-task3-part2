# D1.3 Text cleaning and PII masking

Run: `python -m d1_3_text_cleaning.solution [orders.csv]` → `analytics.csv`.

- Phones: `\D` stripped with `sub`, leading `8` → `7`, a 10-digit local number gets `7` added, then
  `7(\d{3})(\d{3})(\d{4})` is regrouped to `+7-701-123-4567`. Anything else raises `InvalidPhone` and the row is rejected.
- Emails: pragmatic `local@domain.tld` pattern with `fullmatch` (not RFC 5322). Invalid emails are kept but flagged `email_valid=false`.
- Masking (with `sub` + replacement function): `aru@example.com` → `a***@example.com`; phones keep the last 4 digits: `+*-***-***-4567`.
- `strip_html` removes `<...>` tags, unescapes entities (`&nbsp;`, `&amp;`) and collapses whitespace.

Why a regex is fine for stripping tags *here*: the column holds short product descriptions written by our
own staff, with simple tags like `<b>` and `<p>`, and we only need plain text for analytics — a slightly
imperfect result is harmless. It is **not** a general HTML parser: HTML is not a regular language (nesting,
comments, `<script>` bodies, `>` inside quoted attributes, malformed markup), so a regex can leave text
behind or delete real content, and must never be used for sanitising untrusted HTML (XSS). For that use
`html.parser.HTMLParser` or a proper sanitiser.
