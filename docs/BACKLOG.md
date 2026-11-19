# Post-release backlog (P16-T08)

Ideas and known follow-ups after v1.2. Nothing here blocks the release; owner-dependent go-live steps
live in `docs/deployment/GO_LIVE_CHECKLIST.md`.

## Product ideas

| Idea | Notes |
|---|---|
| ATS / HRIS sync connectors | Push hires to payroll/HRIS (e.g. Sage, Belina); the outbound webhooks and public API are the base |
| Assessments & tests module | Timed skills tests and work samples linked to rubric criteria; results stay evidence for human review |
| Video interview integration | Generate Google Meet / Teams links from the connected calendars; no AI analysis of video |
| Mobile app | Candidate app for applications, interview booking and offers (the API already supports it) |
| EEO / diversity reporting by jurisdiction | Only with a lawful basis and owner decision D-10 (ADR-031): voluntary, separate, aggregate-only (k >= 10) |
| EU AI Act conformity pack | If the platform expands to the EU: risk management file, technical documentation, logging and human-oversight evidence (most already exists) |
| Locale-aware routing | Server-rendered text in Shona/Ndebele once the catalogues are reviewed (today client components only) |
| In-app OAuth consent for calendars | "Connect with Google/Microsoft" storing refresh tokens automatically (needs the owner's OAuth apps) |
| Platform UI for AI drift indicators | Available through `GET /api/v1/platform/ai/quality/` and `manage.py ai_quality_report` today |

## Technical follow-ups

| Item | Origin |
|---|---|
| Human translation and review of `sn.json` / `nd.json` and translated email templates | P15-T07 |
| Real-world calibration of AI bands with HR-labelled real applications | P10 |
| Reconstruct tables in PDFs without ruling lines; raise equivalent-wording recall (0.76) | P06/P10 |
| On-demand revalidation of cached public job pages (today up to 60 s stale) | P03 |
| Nonce/hash CSP once Next.js supports it with Cache Components | P09 |
| Frontend Sentry SDK | P11 |
| Platform console: assign an organisation's plan (today via Django admin → Subscriptions) | P14 |
| Browser (Playwright) journeys for hiring, billing, reports and talent pool on staging | P12-P15 |
| Re-evaluate Django 6.x LTS / Node 26 | P16 |
| Worker image size (3.3 GB with CPU torch) | P06 |
| Size production API hosts for submission bursts (seen on shared CI runners) | P10 |
