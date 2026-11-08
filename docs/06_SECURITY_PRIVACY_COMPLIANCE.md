# 06 — Security, Privacy & Compliance

## 1. Threat model (summary)
| Asset | Threats | Key controls |
|---|---|---|
| Candidate PII & CVs | Cross-tenant leak, IDOR, bulk scraping, insider browsing | Tenant scoping, object perms, access logs, blind mode, rate limits, presigned 60 s URLs, break-glass only for platform |
| Accounts | Credential stuffing, phishing, session theft | Rate limits, lockout, breached-password check, MFA for privileged, HttpOnly/Secure cookies, session revoke |
| Uploads | Malware, parser exploits, zip bombs, polyglots | Magic bytes, ClamAV, quarantine bucket, sandboxed parsing w/ limits, no execution, re-encode images |
| AI pipeline | Prompt injection, keyword stuffing, data exfiltration via LLM | Hidden text exclusion, injection detection, redaction, schema validation, LLM off by default |
| Job ads & messages | Stored XSS, phishing links | `nh3` sanitisation allow-list, `rel="noopener nofollow ugc"`, CSP |
| Exports | CSV/formula injection, leaked files | Prefix-escape `= + - @ \t \r`, expiring links, permission + audit |
| Billing (v1.1) | Fake payment callbacks | Paynow hash verification, poll status server-side, idempotent |
| Infra | Secret leakage, open ports | Secrets in env/SSM, least-privileged IAM, SG only 80/443 (+22 restricted IP), fail2ban, unattended-upgrades |

## 2. Security baseline (OWASP ASVS L2 oriented)
- **Transport**: TLS 1.2+ only, HSTS (max-age 1y, includeSubDomains after verification), redirect HTTP→HTTPS.
- **Headers**: CSP (`default-src 'self'; img-src 'self' data: <s3-public>; frame-ancestors 'none'; object-src 'none'`), `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy` minimal, `Cross-Origin-Opener-Policy: same-origin`.
- **Sessions**: HttpOnly, Secure, SameSite=Lax; idle timeout 30 min staff / 7 days candidate (remember-me), absolute 12 h staff; rotate on login/privilege change.
- **CSRF**: Django CSRF on all unsafe methods; trusted origins configured.
- **Passwords**: Argon2id hasher; min 10; breached list (top 100k offline); reset tokens single-use 1 h.
- **MFA**: TOTP mandatory for platform_admin, platform_support, org_admin, hr_manager (enforced at login once org role assigned; grace 7 days).
- **Authorisation**: deny-by-default DRF permissions; object-level checks; 404 for cross-tenant; automated tests per endpoint.
- **Input validation**: serializers strict (no unknown fields), size limits, enum validation, rich text sanitised server-side.
- **Rate limiting**: DRF throttles + Nginx `limit_req` for auth and public search; upload quotas.
- **Secrets**: `.env` never committed; prod secrets in AWS SSM Parameter Store; rotation runbook.
- **Field encryption**: CV text, messages, rights-request notes encrypted with Fernet keys (`FIELD_ENCRYPTION_KEYS`, key-id prefixed) ; S3 SSE-S3/SSE-KMS; RDS encryption at rest.
- **Logging**: no PII in logs (email hashed, ids only); request_id correlation; audit separate from app logs.
- **Dependencies**: `pip-audit`, `npm audit`, Dependabot, Trivy image scan, Bandit/Semgrep in CI.
- **Admin**: Django admin restricted to platform_admin + IP allow-list + MFA; disabled in prod by default (`ENABLE_DJANGO_ADMIN=false`).

## 3. File upload controls (OWASP File Upload Cheat Sheet)
Allow-list extensions **and** MIME **and** magic bytes; rename to UUID keys; store outside web root in private bucket; quarantine → scan → promote; size/page limits; strip metadata for images (re-encode via Pillow); never serve with `inline` for untrusted types except PDF via sandboxed viewer (pdf.js in iframe `sandbox`) ; `Content-Disposition: attachment` on downloads; antivirus signature updates daily (freshclam).

## 4. Privacy — Zimbabwe Cyber and Data Protection Act [Chapter 12:07] & SI 155 of 2024
> Engineering controls below support compliance; legal counsel must confirm applicability (registration/licensing with POTRAZ as Data Protection Authority, DPO appointment, cross-border transfer conditions) before production — tracked as `OWNER-DECISION` D-08.

| Principle / obligation | Implementation |
|---|---|
| Lawfulness, purpose limitation | Purpose-specific consent/notice records (`consent_records`), privacy notice versioned per org; data used only for the applied vacancy unless talent-pool consent |
| Controller / processor roles | Employer org = controller of its applicants' data; MudhoTech = processor (DPA template in docs); platform = controller for account data |
| Data minimisation | No DOB/ID/gender/marital/religion fields; protected-data detector excludes from processing |
| Accuracy | Candidate correction workflow; human verification records |
| Storage limitation | Retention engine; default 12 months post-closure for unsuccessful; hires per employer HR policy; anonymisation job; legal holds |
| Security | §2–3 |
| Data subject rights | Access/export (JSON+PDF), correction, deletion, objection; SLA tracking (default 30 days) |
| Automated decision-making | No solely-automated consequential decisions; candidate can request fully manual review (objection flag ⇒ AI evaluation hidden from reviewers for that application); explanation available on request |
| Transparency | Candidate-facing "How we use AI" page; notice at application start; status timeline |
| Cross-border transfer | Hosting region decision (D-07); LLM disabled by default; if enabled, provider/region documented, DPA, redaction |
| Breach notification | Incident runbook: detect → contain → assess → notify authority & affected (timelines per counsel) → post-mortem |
| Sensitive data | Not collected; if uploaded inadvertently in CVs, excluded from processing and anonymised at retention |
| Children | Platform for job seekers 16+/18+ per job; no DOB collection; eligibility questions only where job-related |
| DPIA | `docs/dpia/DPIA.md` produced in Phase 9 |

## 5. Responsible AI controls (NIST AI RMF mapping)
- **Govern**: model registry, AI policy page, roles (AI owner = platform; rubric owner = HR manager), incident log.
- **Map**: documented intended use/limitations in model registry; prohibited uses list.
- **Measure**: Phase 10 benchmark, counterfactual fairness tests, recall of qualified, grounding, override monitoring.
- **Manage**: feature flags to disable AI per org instantly; fallback manual review; versioned rollouts; quarterly review.
- EU AI Act note: if serving EU employers later, recruitment AI is high-risk (Annex III) — requires risk management, data governance, logging, human oversight, transparency, accuracy/robustness documentation; architecture already logs needed artefacts.

## 6. Accessibility (WCAG 2.2 AA)
Keyboard operable, visible focus (2.4.11/2.4.13 considerations), target size ≥ 24 px (2.5.8), accessible authentication (no cognitive tests; allow password managers/paste) (3.3.8), redundant entry avoidance in wizard (3.3.7), consistent help (3.2.6), error identification & suggestions, labels, contrast ≥ 4.5:1, reduced motion, screen-reader-tested tables/charts with text alternatives, time-limit warnings for sessions with extend option.

## 7. Incident response & operations security
Severity levels S1–S4; on-call contact (owner); runbooks in `docs/runbooks/`: data leak, credential compromise, malware upload outbreak, AI misbehaviour (disable flag), outage, DB restore. Post-incident review template.
