# Languages – English, Shona, Ndebele (P15-T07)

- All interface text lives in `frontend/messages/<locale>.json`; a test fails if JSX text or accessible
  labels are hard-coded (`frontend/tests/i18n.test.tsx`).
- `sn.json` (chiShona) and `nd.json` (isiNdebele) are **machine-drafted partial catalogues**
  (`_meta.status = "machine-draft"`) covering navigation, common actions, footer and states. Every
  key they do not translate falls back to English. Users choosing them see a note that the
  translation awaits review.
- The language switcher (footer) stores the choice in the `NEXT_LOCALE` cookie and on the account
  (`PATCH /api/v1/me/ {locale}`), so emails use it too: notification templates are looked up for the
  user's locale and fall back to English when no translated template exists.
- Pages are server-rendered in English so public pages stay statically prerendered (Next.js Cache
  Components); `LocaleBoundary` applies the chosen language to client components right after the page
  loads. Text rendered only on the server (page titles, a few static headings) stays English until
  locale-aware routing is introduced (follow-up, after the catalogues are reviewed).

## Translator workflow

1. Copy the keys to translate from `en.json` into `sn.json`/`nd.json` (same nesting; keep
   `{placeholders}` and ICU plural syntax exactly).
2. Have a qualified translator review the machine-drafted strings; when a catalogue is fully reviewed
   change `_meta.status` to `"reviewed"`.
3. For emails, add translated platform templates (`NotificationTemplate`, `locale = "sn"`/`"nd"`) in
   the Django admin or through the template API.

The test `drafts only translate keys that exist in English` keeps catalogues from drifting.
