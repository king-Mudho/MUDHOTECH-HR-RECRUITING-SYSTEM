# 12 — Glossary

| Term | Meaning |
|---|---|
| Organisation / Tenant | An employer account; all its data is isolated by `organisation_id` |
| Vacancy / Job | A position advertised by an organisation |
| Job version | Immutable snapshot of a vacancy's ad, criteria, rubric and questionnaire once approved |
| Criterion | A job requirement (skill, experience, qualification…) marked essential or preferred |
| Rubric | Weighted categories + scoring bands used to compute indicators |
| Claim | A fact extracted from a document (e.g. a job held) with source evidence |
| Evidence status | explicit · candidate-reported · inferred · missing · conflicting · human-verified |
| Evaluation | Versioned AI-assisted assessment of one application against one rubric version |
| Coverage | Share of rubric weight for which evidence was assessable |
| Band | AI suggestion category: recommended_for_review, review_needed, eligibility_review, lower_match |
| Knock-out question | Eligibility question; unmet answers trigger human eligibility review (never auto-reject) |
| Clarification | Structured request to a candidate for missing/conflicting information |
| Shortlist | Human-approved set of applications moving to the next stage |
| Override | A human decision that differs from the AI band (reason required) |
| Blind review | Review mode hiding identity details server-side |
| Outbox | DB table of events written in the business transaction, relayed to Celery |
| Break-glass | Time-limited, logged platform support access to tenant data |
| Attachment (industrial) | Zimbabwean term for a student work placement/internship |
| NC / ND / HND | National Certificate / National Diploma / Higher National Diploma (Zimbabwe polytechnic qualifications) |
| ZIMSEC | Zimbabwe School Examinations Council (O-Level / A-Level) |
| CDPA | Zimbabwe Cyber and Data Protection Act [Chapter 12:07] |
| SI 155/2024 | Statutory Instrument 155 of 2024 — Cyber and Data Protection regulations (data controller licensing, DPOs and related obligations); confirm exact obligations with counsel |
| ZWG | Zimbabwe Gold currency code |
| Paynow | Zimbabwean payment gateway supporting EcoCash, OneMoney and cards |
