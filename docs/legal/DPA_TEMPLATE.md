# Data Processing Agreement — template

> **DRAFT TEMPLATE — FOR LEGAL REVIEW (D-08).** Prepared by engineering to describe how MHRS
> actually processes data (P09-T12, 2026-11-17). Not legal advice; counsel must review against the
> Cyber and Data Protection Act [Chapter 12:07] and SI 155 of 2024 before use. Bracketed items
> `[…]` are to be completed per customer.

**Between**

- **[Employer legal name]**, registration number [ ], of [address] (the **Controller**); and
- **MudhoTech Solutions (Pvt) Ltd**, registration number [ ], of [address], Harare, Zimbabwe
  (the **Processor**),

in connection with the subscription agreement dated [ ] for MUDHOTECH HR RECRUITING SYSTEM
(the **Service**).

## 1. Definitions
Terms such as *personal data*, *processing*, *data subject*, *data controller*, *data processor*
and *personal data breach* have the meanings given in the Cyber and Data Protection Act
[Chapter 12:07] (the **Act**). **Applicant Data** means personal data of job applicants and of the
Controller's staff processed in the Controller's organisation account in the Service.

## 2. Roles and scope
2.1 The Controller determines the purposes and means of processing Applicant Data; the Processor
processes it only on the Controller's documented instructions, which are this Agreement, the
Controller's configuration of the Service (vacancies, rubrics, policies, retention) and the actions
of its authorised users.
2.2 The Processor is a controller in its own right only for platform account data (candidate and
user accounts, authentication, security logs) as described in its privacy notice.
2.3 Details of the processing are in **Annex 1**.

## 3. Processor obligations
The Processor shall:
1. process Applicant Data only on documented instructions, including for transfers, and inform the
   Controller if an instruction appears to infringe the Act;
2. ensure persons authorised to process are bound by confidentiality, and limit MudhoTech staff
   access to approved, time-limited, read-only support access that is logged and visible to the
   Controller's staff;
3. implement the technical and organisational measures in **Annex 2**;
4. not engage another processor without the Controller's prior general written authorisation;
   the current sub-processors are listed in **Annex 3**, and the Processor gives [30] days' notice
   of changes, during which the Controller may object;
5. assist the Controller in responding to data-subject requests (access/export, correction,
   deletion, objection) — the Service provides self-service tools and routes requests to the
   Controller's administrators with SLA tracking;
6. assist with security, breach notification, DPIAs and prior consultation, taking into account the
   nature of processing;
7. at the Controller's choice, delete or return Applicant Data at the end of the Service, unless law
   requires storage, and certify deletion;
8. make available information necessary to demonstrate compliance (including audit logs and
   decision reconstructions) and allow audits [once per year, on [30] days' notice].

## 4. Automated processing and AI
4.1 The Service's AI screening **only recommends**. It cannot shortlist, decline, make offers or
hire; these actions require an authorised user of the Controller and a recorded reason.
4.2 The Controller decides whether AI screening and any external language model are enabled for its
organisation. External language models are disabled by default; if enabled, contact details are
removed before data is sent and the provider is listed in Annex 3.
4.3 Applicants may object to automated processing; their application is then reviewed manually with
no AI output shown.
4.4 Applicant Data is never used to train AI models.
4.5 The Controller remains responsible for its recruitment decisions and for not adding questions
that collect protected attributes.

## 5. Personal data breaches
The Processor shall notify the Controller without undue delay and in any case within [48] hours of
becoming aware of a personal data breach affecting Applicant Data, with the information then
available (nature, categories and approximate numbers, likely consequences, measures taken), and
shall support the Controller's notification of the Authority and data subjects [timelines per
counsel].

## 6. International transfers
Applicant Data is hosted in AWS `af-south-1` (South Africa). [Counsel: transfer conditions under the
Act, authorisation if required.] Any transfer to another country requires the Controller's prior
written consent and appropriate safeguards.

## 7. Retention
Applicant Data is retained according to the Controller's retention settings (default: unsuccessful
applications anonymised 12 months after the vacancy closes), subject to legal holds the Controller
places. Backups are overwritten within [35] days.

## 8. Liability, term and law
[Liability as in the subscription agreement.] This Agreement lasts as long as the Processor processes
Applicant Data. Governed by the laws of Zimbabwe; courts of [Harare].

## Signatures

| | Controller | Processor |
|---|---|---|
| Name | | |
| Title | | |
| Signature | | |
| Date | | |

---

## Annex 1 — Details of processing

| | |
|---|---|
| Subject matter | Hosting and operating an applicant tracking system with AI-assisted screening |
| Duration | Term of the subscription plus the retention period |
| Nature | Collection, storage, extraction from documents, matching to vacancy criteria, scoring, display, notification, export, anonymisation, deletion |
| Purpose | Receiving and assessing job applications for the Controller's vacancies |
| Data subjects | Job applicants; Controller staff users; referees [if enabled] |
| Categories | Identity and contact details, CVs and documents, questionnaire answers, extracted claims and evaluations, assessment notes and decisions, interview feedback, offers, audit logs |
| Special categories | Not requested. Inadvertently supplied special-category data in documents is excluded from AI processing |

## Annex 2 — Technical and organisational measures

- Tenant isolation enforced server-side on every request, with database row-level security.
- Role-based access, least privilege, multi-factor authentication for staff roles.
- Encryption in transit (TLS) and at rest (database, object storage, field-level encryption of CV
  text and assessments, key rotation).
- Virus scanning, type checks and sandboxed parsing of uploaded files; private storage, short-lived
  download links.
- Append-only, hash-chained audit log of sensitive actions and views of candidate data.
- Blind review by default; conflict-of-interest declarations.
- Security testing: static analysis, dependency and container scanning, dynamic scanning (OWASP
  ZAP), OWASP ASVS Level 2 checklist.
- Backups, monitoring, incident response and AI kill-switch runbooks.
- Staff confidentiality undertakings and security training.

## Annex 3 — Authorised sub-processors [to confirm]

| Sub-processor | Service | Location |
|---|---|---|
| Amazon Web Services | Hosting, storage, email (SES) | South Africa (`af-south-1`) |
| [Error monitoring provider, e.g. Sentry] | Error tracking (no personal data in events) | [ ] |
| [LLM provider — only if the Controller enables it] | Summaries of evaluations (redacted) | [ ] |
