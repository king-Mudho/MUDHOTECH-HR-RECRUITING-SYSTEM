# OWASP ASVS 4.0.3 — Level 2 checklist (relevant items)

Status as of 2026-11-17 (Phase 09, P09-T10). **Met** = implemented and covered by a test or a CI gate;
**Met (config)** = enforced by production settings/infrastructure, verified by review;
**Accepted** = deviation recorded in `docs/11_DECISIONS_LOG.md`; **N/A** = not applicable to MHRS.
Evidence paths are relative to the repository root.

## Findings fixed during this review

| # | Finding | Fix |
|---|---|---|
| F1 | Django admin URL was mounted in every environment | Gated by `ENABLE_DJANGO_ADMIN` (off by default, on in dev only) — `backend/config/urls.py`, `apps/core/tests/test_security_headers.py::test_django_admin_is_gated` |
| F2 | API responses had no Content-Security-Policy | `apps/core/security_headers.py` (`default-src 'none'`, COOP/CORP, Permissions-Policy) — `test_api_responses_carry_a_locked_down_csp` |
| F3 | Frontend had no CSP / HSTS | `frontend/next.config.ts` CSP (ADR-027), COOP, HSTS in production |
| F4 | `.secrets.baseline` was stale (line drift) and stored Windows paths that would not match in CI | Regenerated, every entry reviewed (test placeholders, dev-only S3 keys, rate-limit strings), paths normalised; nightly `detect-secrets-hook` step |
| F5 | AI score copied to applications whose candidate objected to automated processing (EC-AI-12) | Cleared on store + backfill migration — `apps/screening/services.py`, `test_applicants.py::test_filters_and_ordering` |
| F6 | Name search in blind review could reveal who is behind an alias | Search limited to the reference in blind mode — `apps/applications/applicants.py`, `test_blind_search_matches_reference_only` |
| F7 | Retention query silently excluded rows (JSON key comparison with NULL) | Containment lookup — `apps/privacy/retention.py`, `test_retention.py` |
| F8 | Minimum password length was 10 (ASVS 2.1.1 asks for 12) | 12 in `AUTH_PASSWORD_VALIDATORS` and the frontend schema (`PASSWORD_MIN`) |
| F9 | Authenticated API responses did not forbid caching | `Cache-Control: no-store` for signed-in users (`apps/core/security_headers.py`) |
| F10 | RLS is bypassed by superuser DB roles | Documented requirement: non-superuser, non-BYPASSRLS app role (docs/10 §3.1); tests use a probe role |

## V1 Architecture

| Item | Requirement | Status | Evidence |
|---|---|---|---|
| 1.1.2 | Threat model | Met | `docs/06_SECURITY_PRIVACY_COMPLIANCE.md` §1 (asset/threat/control table) |
| 1.4.1 | Trusted enforcement points for access control | Met | Server-side RBAC `apps/organisations/rbac.py`, `HasOrgAction`; UI only hides |
| 1.4.4 | Single, vetted access-control mechanism | Met | `applications_visible_to` (one selector), `tests/permissions/test_matrix.py` derived from RBAC |
| 1.5.1 | Input/output handling defined | Met | Strict serializers (`StrictSerializer`), nh3 sanitisation, React escaping |
| 1.14.6 | No unsupported client-side tech | Met | Next.js/React only |

## V2 Authentication

| Item | Requirement | Status | Evidence |
|---|---|---|---|
| 2.1.1 | Passwords ≥ 12 characters | Met | `AUTH_PASSWORD_VALIDATORS` min_length 12 (F8) |
| 2.1.7 | Breached-password check | Met | `apps/accounts/password_validation.BreachedPasswordValidator` |
| 2.1.9 | No composition rules | Met | Length + breach only |
| 2.2.1 | Anti-automation / lockout | Met | `ACCOUNT_RATE_LIMITS`, allauth login throttling, `apps/accounts/tests` |
| 2.2.3 | Notify on credential changes | Met | Security emails (`apps/accounts`) |
| 2.5.x | Secure recovery | Met | allauth reset with key, rate-limited |
| 2.8.x | MFA (TOTP + recovery codes) mandatory for privileged roles | Met | `MfaEnforcementMiddleware`, `MFA_SUPPORTED_TYPES`, docs/06 §2 |
| 2.10.4 | No secrets in source | Met | detect-secrets baseline + nightly hook, all secrets from env (`django-environ`) |

## V3 Session management

| Item | Requirement | Status | Evidence |
|---|---|---|---|
| 3.2.1 | New session token on login | Met | Django `cycle_key` on login |
| 3.3.1 | Logout invalidates session | Met | allauth logout; `usersessions` revoke |
| 3.4.1–3.4.3 | Secure, HttpOnly, SameSite cookies | Met (config) | `SESSION_COOKIE_SECURE/HTTPONLY`, `SameSite=Lax` (base/prod settings) |
| 3.5.x | No tokens in browser storage | Met | ADR-004 session cookies only |
| 3.7.1 | Re-authentication for sensitive actions | Met | Rights requests require the password (`apps/privacy/rights.py`), reauth dialog for security settings |

## V4 Access control

| Item | Requirement | Status | Evidence |
|---|---|---|---|
| 4.1.1 | Enforced server-side | Met | DRF permissions on every view; cross-tenant suite `tests/tenancy/test_cross_tenant.py` |
| 4.1.3 | Least privilege | Met | Role matrix tests; hiring managers see shortlist only (EC-REV-09) |
| 4.2.1 | IDOR protection | Met | Object lookups through tenant-scoped selectors; 404 for foreign ids |
| 4.2.2 | CSRF | Met | Django CSRF + `X-CSRFToken` (ADR-004) |
| 4.3.1 | Admin interfaces protected | Met | F1; platform admin requires MFA |
| 4.3.2 | Directory browsing disabled | Met (config) | Private buckets, presigned URLs only |
| — | Second line of tenant defence | Met | PostgreSQL RLS (ADR-012, P09-T07) `apps/core/tests/test_rls.py` |
| — | Break-glass support access | Met | Approved, ≤ 4 h, read-only, logged, tenant-visible (`apps/organisations/support_access.py`) |

## V5 Validation, sanitisation, encoding

| Item | Requirement | Status | Evidence |
|---|---|---|---|
| 5.1.3 | Server-side input validation | Met | Strict serializers reject unknown fields |
| 5.2.1 | Rich text sanitised | Met | `apps/core/sanitize.py` (nh3 allow-list), EC-JOB-12 tests |
| 5.2.4 | No eval of untrusted data | Met | pdf.js renders canvases only; no `eval` |
| 5.3.x | Output encoding | Met | React escaping; JSON-LD via `safeJsonLd` |
| — | CSV/formula injection (EC-PRV-08) | Met | `apps/core/csv_safe.py`, guard test `test_every_csv_writer_uses_the_safe_cell_helper` |
| — | Prompt injection in CVs | Met | `ai_engine/security/injection.py`, LLM guardrails (docs/05 §9) |

## V6 Cryptography

| Item | Requirement | Status | Evidence |
|---|---|---|---|
| 6.2.1 | Approved algorithms | Met | Fernet (AES-128-CBC + HMAC) for field encryption, SHA-256 tokens |
| 6.4.1 | Key management, rotation | Met | Key-id prefixed `EncryptedTextField` with `rotate()` (`apps/core/crypto.py`) |
| 6.3.1 | CSPRNG | Met | `secrets` for tokens (rights confirmation, references) |

## V7 Errors & logging

| Item | Requirement | Status | Evidence |
|---|---|---|---|
| 7.1.1 | No credentials/PII in logs | Met | Structured JSON logs with ids only; CLAUDE.md rule 8 |
| 7.2.x | Security events logged | Met | Append-only, hash-chained audit (`apps/audit`, ADR-018), `verify_audit_chain` |
| 7.3.3 | Log integrity | Met | DB trigger rejects UPDATE/DELETE on audit tables |
| 7.4.1 | Generic error responses | Met | Error envelope with request id, no stack traces |
| — | PII view logging | Met | `audit.log_view` on every candidate data view (P08-T12) |

## V8 Data protection

| Item | Requirement | Status | Evidence |
|---|---|---|---|
| 8.1.x | Sensitive data not cached by browsers/CDN | Met | `Cache-Control: no-store` on every authenticated response (F9), presigned downloads 60 s |
| 8.2.x | Client-side storage | Met | Only non-sensitive UI preferences / list order in `sessionStorage` |
| 8.3.1 | Data minimisation, retention | Met | Retention engine (P09-T05), export/erasure (P09-T03/T04), blind review |
| 8.3.4 | Encryption at rest of sensitive text | Met | `EncryptedTextField` for CV text, claims, snippets, explanations, notes in rights requests |

## V9 Communications

| Item | Requirement | Status | Evidence |
|---|---|---|---|
| 9.1.1 | TLS everywhere | Met (config) | `SECURE_SSL_REDIRECT`, HSTS preload (prod settings), Nginx TLS (docs/10) |
| 9.2.x | Server-to-server TLS | Met (config) | S3/SES/SMTP over TLS |

## V10 Malicious code

| Item | Requirement | Status | Evidence |
|---|---|---|---|
| 10.3.2 | Dependency integrity | Met | Lockfiles (`uv.lock`, `package-lock.json`), pinned GitHub Actions by SHA |
| — | Dependency vulnerabilities | Met | pip-audit `--strict`, `npm audit --audit-level=high` in CI (0 found 2026-11-17) |

## V12 Files and resources

| Item | Requirement | Status | Evidence |
|---|---|---|---|
| 12.1.1 | Size limits | Met | Per-purpose upload limits, `APPLICATION_TOTAL_BYTES` |
| 12.2.1 | Type checks (extension + MIME + magic bytes) | Met | `apps/documents` scan pipeline tests |
| 12.4.1 | Stored outside web root, private | Met | Private S3 buckets, UUID keys, quarantine → scan → promote |
| 12.5.2 | Untrusted files never served inline | Met | `Content-Disposition: attachment`; PDFs viewed as canvases (pdf.js) |
| — | Antivirus | Met | ClamAV pipeline (nightly real-ClamAV EICAR job) |
| — | Parsing in a sandbox | Met | `ai_engine.extraction.sandbox` (subprocess + limits) |

## V13 API

| Item | Requirement | Status | Evidence |
|---|---|---|---|
| 13.1.3 | No sensitive data in URLs | Met | Ids only; tokens POSTed (rights confirmation) |
| 13.2.1 | Methods restricted | Met | Explicit DRF views; support access read-only |
| 13.2.6 | Idempotency for consequential actions | Met | `@idempotent` (submit, shortlist approve) |
| 13.4.x | CORS | Met | Same-origin only, no CORS headers (`test_cors_is_closed`) |

## V14 Configuration

| Item | Requirement | Status | Evidence |
|---|---|---|---|
| 14.2.1 | Components up to date | Met | Weekly/nightly scans; Trivy image scans (nightly) |
| 14.3.2 | Debug off in production | Met (config) | `DEBUG=False` in `config/settings/prod.py` |
| 14.4.x | Security headers | Met | F2/F3; ZAP baseline nightly (`infrastructure/security/zap-rules.tsv`) |
| 14.4.3 | CSP | Accepted | ADR-027: no nonces (PPR/Cache Components); all other directives strict |
| 14.5.x | Request origin validation | Met | CSRF trusted origins, Host validation (`ALLOWED_HOSTS`) |

## CI gates (P09-T09)

Per push (`.github/workflows/ci.yml`): ruff, mypy, migrations check, tests ≥ 80 % coverage, EC coverage,
**bandit (medium+)**, **pip-audit --strict**, **npm audit (high+)**, schema drift.
Nightly (`.github/workflows/nightly.yml`): Playwright + axe on the Docker stack, **OWASP ZAP baseline**,
**semgrep** (default, Django, React, TypeScript, secrets), **detect-secrets**, **Trivy** filesystem +
backend/frontend images (CRITICAL/HIGH fail), real ClamAV, AI benchmarks.

Local run 2026-11-17: bandit 0 medium/high, pip-audit 0 vulnerabilities, npm audit 0 vulnerabilities,
detect-secrets 0 new findings.
