# Data Protection Impact Assessment (DPIA) — MUDHOTECH HR RECRUITING SYSTEM

> **DRAFT — FOR LEGAL REVIEW (D-08).** Prepared by engineering from the implemented system
> (Phase 09, P09-T12, 2026-11-17). It is not legal advice. Counsel must confirm applicability of
> the Cyber and Data Protection Act [Chapter 12:07] ("CDPA") and the Cyber and Data Protection
> (Licensing of Data Controllers and Appointment of Data Protection Officers) Regulations, SI 155
> of 2024, POTRAZ licensing/registration, DPO appointment and cross-border transfer conditions
> before go-live. Bracketed items `[…]` need owner or counsel input.

## 1. Overview

| | |
|---|---|
| Processing | Online recruitment (applicant tracking) with AI-assisted, human-controlled screening |
| System | MUDHOTECH HR RECRUITING SYSTEM (MHRS), multi-tenant SaaS |
| Vendor / processor | MudhoTech Solutions (Pvt) Ltd, Harare, Zimbabwe |
| Controllers | Each employer organisation (tenant) for its applicants' data; MudhoTech for platform account data (candidate accounts, staff accounts, security logs) |
| Hosting | AWS `af-south-1` (Cape Town) — D-07; implies a cross-border transfer from Zimbabwe |
| DPIA owner | [MudhoTech DPO — to be appointed] |
| Why a DPIA | Large-scale processing of applicants' personal data, automated evaluation that can affect access to employment, use of new technology (AI), vulnerable data subjects (job seekers in an unequal relationship with employers) |

## 2. Description of the processing

### 2.1 Data subjects
Job candidates (including people under 18 only where a vacancy allows it — no date of birth is
collected), employer staff (HR managers, recruiters, hiring managers, interview panelists),
referees named by candidates [if reference checks are enabled], platform staff.

### 2.2 Personal data

| Category | Examples | Source | Notes |
|---|---|---|---|
| Identity & contact | Name, email, phone (E.164), town | Candidate | Masked in blind review |
| Application content | CV and documents, cover letter, questionnaire answers, salary expectation, availability | Candidate | CV text encrypted at rest |
| Derived data | Extracted claims with source snippets, criterion results, scores, bands, explanations, clarification questions | System | Versioned; encrypted text fields |
| Assessment & decisions | HR notes, verifications, shortlist decisions with reasons, interview scorecards, offers, hire records | Employer staff | Consequential decisions always by a person |
| Account & security | Password hash, MFA secrets, sessions, IP addresses, audit and access logs | System | Hash-chained, append-only audit |
| Consent & rights | Notice versions accepted, objection to automated processing, rights requests | Candidate | Kept as evidence of compliance |

**Not collected:** date of birth, national ID, gender, marital status, religion, ethnicity/tribe,
political opinion, health/HIV status, disability, photo. If such data appears inside a CV it is
excluded from matching by the protected-data filter and removed at retention.

### 2.3 Purposes and lawful basis [counsel to confirm]

| Purpose | Proposed basis |
|---|---|
| Receive and assess applications for a vacancy | Steps at the candidate's request before entering a contract; employer's legitimate interest; consent recorded for the notice version |
| AI-assisted screening (evidence extraction, scoring, bands) | Legitimate interest with the right to object (fully manual review on request); no solely-automated decisions |
| Talent pool / future vacancies | Separate, optional consent |
| Notifications | Necessary for the application; marketing never |
| Security, audit, fraud prevention | Legal obligation / legitimate interest |

### 2.4 Lifecycle
1. Candidate creates an account, reads the privacy notice and `/how-we-use-ai`, applies.
2. Files are quarantined, virus-scanned (ClamAV), type-checked and parsed in a sandbox.
3. Screening engine evaluates against the HR-approved rubric (unless the candidate objected or AI is
   switched off).
4. HR reviews evidence (blind by default), clarifies, approves a shortlist; candidates are notified
   after a delay that allows undo.
5. Interviews, offers, hire.
6. Retention: unsuccessful applications anonymised 12 months after vacancy close (D-03);
   legal holds pause deletion; candidates can export or erase their data at any time.

### 2.5 Recipients and processors
Employer staff with a role on the vacancy (RBAC, hiring managers see shortlisted applications only);
MudhoTech platform staff only through approved, time-boxed, read-only break-glass access visible to
the tenant; sub-processors: AWS (hosting, S3, SES email) [list and DPAs to confirm]; optional LLM
provider (off by default; contact details redacted before any call).

## 3. Necessity and proportionality

- **Minimisation:** fixed, job-related fields; employers cannot add protected-attribute questions
  (validation); no social-media scraping.
- **Purpose limitation:** data used only for the vacancy applied for unless talent-pool consent.
- **Accuracy:** candidates review and correct extracted CV data before submitting; HR verification
  records; conflicts flagged, not resolved automatically.
- **Storage limitation:** retention engine with weekly dry-run preview, anonymisation, erasure
  verification (`verify_erasure`), legal holds.
- **Transparency:** versioned privacy notice per organisation, AI notice, status timeline.
- **Rights:** access/export (24-hour download link), correction, deletion, objection; identity
  re-confirmed by password and email; SLA tracking (default 30 days) with reminders.
- **Human oversight:** AI only recommends; every consequential state needs a person and a reason
  (`check_human_decisions` = 0 exceptions); full reconstruction of any decision.

## 4. Risk assessment

Likelihood (L) and severity (S): 1 low – 3 high. Residual risk after mitigations.

| # | Risk to individuals | L | S | Mitigations (implemented) | Residual |
|---|---|---|---|---|---|
| R1 | Unfair or discriminatory screening (bias, proxies) | 2 | 3 | No protected data; counterfactual invariance tests (121/121); missing evidence = unknown; no reject band; human decision with reason; override monitoring; kill-switch; model card | Low–medium |
| R2 | Solely automated decision affecting employment | 2 | 3 | Engine cannot set consequential states (code + audit check); objection → manual review with no AI output; explanation on request | Low |
| R3 | Inaccurate extraction harms a candidate | 2 | 2 | Evidence links, candidate correction before submit, HR verification, OCR/quality flags route to review | Low |
| R4 | Cross-tenant data exposure | 1 | 3 | Server-side tenant scoping, object-level checks, cross-tenant test suite on every endpoint, PostgreSQL RLS second line | Low |
| R5 | Breach of CVs / personal data (external attack) | 2 | 3 | ASVS L2 controls, MFA for staff, encryption at rest (fields + S3), TLS, private buckets with short presigned URLs, malware scanning, security scanning in CI/nightly, incident runbook | Low–medium |
| R6 | Insider misuse by employer staff | 2 | 2 | Least-privilege roles, blind review, conflict-of-interest declarations, view logging (`audit.log_view`), exportable audit trail | Low–medium |
| R7 | Platform staff access to tenant data | 1 | 3 | Break-glass only: second-admin approval, ≤ 4 h, read-only, every read logged, banner to tenant staff | Low |
| R8 | Excessive retention | 2 | 2 | Retention engine (D-03 default), anonymisation, erasure verification, legal-hold tracking | Low |
| R9 | Cross-border transfer (South Africa hosting, optional LLM) | 2 | 2 | Encryption, AWS DPA, LLM off by default with redaction; [counsel: transfer conditions/adequacy, POTRAZ authorisation] | Medium (pending legal) |
| R10 | Prompt injection / malicious files in CVs | 2 | 2 | Sandboxed parsing, ClamAV, injection detection, instructions in CVs never followed, flagged for human review | Low |
| R11 | Candidates not understanding AI use | 2 | 2 | Plain-language AI notice before applying, labelled AI content, explanations | Low |
| R12 | Formula injection in exported spreadsheets | 1 | 2 | `csv_safe` on every export, guard test | Low |
| R13 | Failure loses an application (availability) | 1 | 2 | Transactional outbox, idempotent tasks, dead letters, processing errors wait for HR | Low |

## 5. Residual risk and conclusion

With the mitigations in place, the residual risk is assessed as **low to medium**. The highest
residual items are R9 (cross-border transfer — legal conditions to confirm) and R1/R5 (inherent to
AI screening and to holding CVs at scale; monitored continuously). Engineering recommends
proceeding **subject to**:

1. counsel confirming lawful bases, POTRAZ licensing and DPO appointment (D-08);
2. counsel approving the cross-border transfer arrangement for `af-south-1` and any LLM provider;
3. signed DPAs with each employer (template `docs/legal/DPA_TEMPLATE.md`) and with sub-processors;
4. Phase 10 real-world calibration of screening bands with HR reviewers before general availability;
5. a DPIA review at least yearly and at every material change (new AI model or provider, new data
   category, new hosting region).

Prior consultation with the Data Protection Authority: [counsel to decide whether required].

## 6. Action plan

| Action | Owner | Due |
|---|---|---|
| Appoint DPO, register/licence with POTRAZ | MudhoTech management + counsel | Before go-live |
| Confirm transfer mechanism for AWS af-south-1 | Counsel | Before go-live |
| Finalise DPA template and sub-processor list | Counsel | Before first customer |
| Real-world calibration and fairness review | AI governance owner | Phase 10 |
| Penetration test by an external party | MudhoTech | Before go-live |
| Yearly DPIA review | DPO | Yearly |

## 7. Sign-off

| Role | Name | Decision | Signature | Date |
|---|---|---|---|---|
| Owner, MudhoTech Solutions (Pvt) Ltd | [ ] | [approve / approve with conditions / reject] | | |
| Legal counsel | [ ] | [ ] | | |
| Data Protection Officer | [ ] | [ ] | | |
| AI governance owner | [ ] | [ ] | | |

Evidence: `docs/06_SECURITY_PRIVACY_COMPLIANCE.md`, `docs/security/ASVS_CHECKLIST.md`,
`docs/ai-governance/`, `docs/reports/`, `docs/runbooks/`.
