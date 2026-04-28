# PatronAI Branding Assets

## Drop the two PNGs here

Save the uploaded brand assets into this folder with these exact filenames so
docs and the Streamlit dashboard can reference them without further edits:

| File                      | Source (uploaded)          | Used by                                      |
|---------------------------|----------------------------|----------------------------------------------|
| `patronai-icon.png`       | Circular shield glyph      | Streamlit `page_icon`, favicons, HTML docs   |
| `patronai-logo.png`       | Full PatronAI wordmark     | Sidebar header, cover pages, docx spec, PDFs |

Optional companions (produce later if needed):

- `patronai-icon-32.png` — 32x32 favicon crop
- `patronai-logo-dark.svg` — vector wordmark for print/high-DPI
- `patronai-logo-mono-white.png` — single-colour reversed lockup for dark decks

## Colour tokens (from the logo)

```
--patron-bg-deep     #0A0F1F   /* navy canvas behind the mark */
--patron-blue-1      #1F6FEB   /* primary brand blue */
--patron-blue-2      #58A6FF   /* cyan accent / shield outline */
--patron-shield      #BFD9FF   /* light shield wash */
--patron-text-hi     #E6EDF3   /* "Patron" wordmark white */
--patron-text-accent #58A6FF   /* "AI" wordmark accent */
```

These are aligned with the existing dark Bloomberg/Palantir palette used in
`dashboard/ghost_dashboard.py` — no CSS rewrite needed.

## Notes

- PNGs are not version-controlled as source of truth — keep the originals in
  your design tool (Figma / Affinity). This folder is the runtime asset drop.
- The Streamlit dashboard reads these via the `PATRONAI_BRANDING_DIR` env var
  if set, otherwise falls back to `ghost-ai-scanner/assets/branding/`.
