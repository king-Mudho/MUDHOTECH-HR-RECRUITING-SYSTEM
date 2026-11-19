# Public API v1 and job feeds (P15-T06)

## API keys

Organisation admins create keys in **Settings → Integrations → API keys**. A key looks like
`mhrs_<prefix>_<secret>`; it is shown **once** (only a hash is stored) and can be revoked at any time.

| Scope | Gives |
|---|---|
| `jobs:read` | The organisation's open, public vacancies |
| `applications:read` | Application id, reference, vacancy id, status, submitted/updated times |

Keys never expose candidate names, contact details, documents, answers or AI output.

```
curl -H "Authorization: Bearer mhrs_ab12cd34_…" https://<host>/api/v1/public-api/jobs/
curl -H "Authorization: Bearer mhrs_ab12cd34_…" \
     "https://<host>/api/v1/public-api/applications/?job=<id>&updated_since=2026-11-01T00:00:00Z"
```

Rate limit: 600 requests per hour per key (`API_KEY_RATE`); a 429 response carries `Retry-After`.
The OpenAPI description is at `/api/v1/schema/` (tag `public-api`).

## Job feeds (no key needed)

- `GET /api/v1/feeds/<organisation-slug>/jobs.xml` – Indeed-style XML (`<source><job>…</job></source>`)
- `GET /api/v1/feeds/<organisation-slug>/jobs.json` – the same vacancies as JSON

Only public, published vacancies whose closing date has not passed are listed. Responses are cacheable
for 5 minutes. Give the XML URL to job boards that accept feeds.
