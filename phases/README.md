# Implementation Phases — Index

| # | Phase | Release | Modules | Key outcome |
|---|---|---|---|---|
| 01 | [Foundation & Dev Environment](PHASE_01_FOUNDATION.md) | MVP | core | Running Dockerised skeleton, CI, outbox, idempotency |
| 02 | [Identity, Tenancy & Access Control](PHASE_02_IDENTITY_TENANCY_ACCESS.md) | MVP | M01–M03, M22 | Auth + MFA, orgs, teams, RBAC, audit chain |
| 03 | [Vacancies, Taxonomy & Job Board](PHASE_03_VACANCIES_JOB_BOARD.md) | MVP | M04, M05, M08, M24 | Job wizard, approvals, public SEO job board |
| 04 | [Candidate Portal & Applications](PHASE_04_CANDIDATE_PORTAL_APPLICATIONS.md) | MVP | M06–M08 | Safe uploads, 6-step wizard, idempotent submission |
| 05 | [ATS, Notifications & Messaging](PHASE_05_ATS_NOTIFICATIONS_MESSAGING.md) | MVP | M13, M14, M23 | Pipeline, emails, clarifications, messages |
| 06 | [CV Extraction (AI 1)](PHASE_06_CV_EXTRACTION.md) | MVP | M09, M24 | Evidence-linked claims, OCR, PII exclusion |
| 07 | [Matching, Scoring & Explanations (AI 2)](PHASE_07_MATCHING_SCORING_EXPLANATIONS.md) | MVP | M10, M11 | Versioned, grounded evaluations & bands |
| 08 | [Shortlist, Dashboard & Audit](PHASE_08_SHORTLIST_DASHBOARD_AUDIT.md) | MVP | M12, M15, M22 | Human-approved shortlist — **MVP feature-complete** |
| 09 | [Privacy, Governance & Security](PHASE_09_PRIVACY_GOVERNANCE_SECURITY.md) | MVP | M22 | Rights, retention, DPIA, hardening |
| 10 | [QA, AI Validation & Pilot](PHASE_10_QA_AI_VALIDATION_PILOT.md) | MVP | — | 100-application benchmark, load/fault tests |
| 11 | [Production Deployment](PHASE_11_PRODUCTION_DEPLOYMENT.md) | MVP | — | AWS live, backups, monitoring — **v1.0** |
| 12 | [Interviews, Offers & Hiring](PHASE_12_INTERVIEWS_OFFERS_HIRING.md) | v1.1 | M16, M17 | Panels, scorecards, offers, hires |
| 13 | [Talent Pool & Analytics](PHASE_13_TALENT_POOL_ANALYTICS.md) | v1.1 | M18, M19 | Consent pool, reports, exports |
| 14 | [Platform Admin & Billing](PHASE_14_PLATFORM_ADMIN_BILLING.md) | v1.1 | M20 | Plans, entitlements, Paynow/EcoCash |
| 15 | [Integrations & Localisation](PHASE_15_INTEGRATIONS_LOCALISATION.md) | v1.2 | M21 | Calendar, SSO, SMS/WA, webhooks, public API, sn/nd |
| 16 | [Final Hardening & Release](PHASE_16_FINAL_HARDENING_RELEASE.md) | v1.2 | — | Regression, docs, handover — **project complete** |

Task ID format: `PNN-TNN`. Edge case IDs (`EC-…`) refer to `docs/07_EDGE_CASES.md`.
Mapping from the original Blueprint's 8 phases: Blueprint Phase 1 (design) = `docs/` (done); 2 → 01–02; 3 → 03–05; 4 → 06–07; 5 → 08–09; 6 → 10; 7 → 11; 8 → 12–16.
