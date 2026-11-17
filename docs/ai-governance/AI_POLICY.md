# AI policy — MUDHOTECH HR RECRUITING SYSTEM

Owner: MudhoTech Solutions (Pvt) Ltd. Version 1.0, 2026-11-17 (P09-T11). Applies to every AI or
automated feature in MHRS and to everyone who builds, operates or configures it. Read with the model
card (`MODEL_CARD_screening_engine.md`), `docs/05_AI_ENGINE.md` and
`docs/06_SECURITY_PRIVACY_COMPLIANCE.md`. Legal basis: Cyber and Data Protection Act [Chapter 12:07]
and SI 155 of 2024 (including the right not to be subject to a decision based solely on automated
processing).

## 1. Principles

1. **People decide.** AI recommends and finds evidence. No consequential status (shortlisted, not
   selected, offer, hired) is set without an authenticated person and a recorded reason. This is
   enforced in code and verified by `check_human_decisions`.
2. **Evidence first.** Every AI finding links to its source or is labelled missing, inferred or
   conflicting. Uncited text is not shown.
3. **Missing is not negative.** Absent information is unknown, never an automatic fail.
4. **No protected attributes.** AI never infers, uses or scores race, ethnicity, tribe, religion,
   gender, age, marital status, pregnancy, disability, political opinion, HIV/health status or
   appearance. Career gaps and CV formatting are not penalised.
5. **Transparency.** Candidates see the public notice `/how-we-use-ai` before applying; AI content
   in the product is labelled "AI-assisted suggestion — requires human review".
6. **Candidate choice.** Candidates can request a fully manual review (no AI output is then shown to
   anyone), an explanation, and access, correction or deletion of their data.
7. **Untrusted input.** CV text may contain prompt injection or malware; it is sandboxed, scanned and
   never obeyed.
8. **Versioned and reconstructable.** Every evaluation can be traced to its inputs, rubric, engine,
   models and prompts.

## 2. Roles and responsibilities

| Role | Responsibility |
|---|---|
| MudhoTech AI governance owner | Approves engine/threshold/model releases, owns this policy and the model card, reviews the quarterly AI quality report, decides on kill-switch use for the platform |
| Platform admins | Operate the kill-switch and model registry (`/admin/model-registry`), MFA mandatory, actions audited |
| Organisation admins (employer) | Decide whether AI screening and the optional LLM are on for their organisation (policy), approve rubrics, can switch AI off for their organisation |
| HR users | Review evidence, verify or correct claims, record reasons for every decision, report suspected AI errors |
| Engineers | Follow `docs/05_AI_ENGINE.md` guardrails; keep benchmarks green; bump `ENGINE_VERSION` on output changes |

## 3. Release gate for AI changes

An engine, taxonomy, threshold, prompt or model change ships only when:

- the extraction and screening benchmarks meet their targets (nightly `ai-benchmark` job);
- counterfactual invariance is 100 % and protected leaks are 0;
- grounding is 100 %;
- the model registry entry is created (automatic on migrate) and the model card is updated;
- material changes are recorded as an ADR in `docs/11_DECISIONS_LOG.md`.

Existing evaluations are never rewritten; HR opts in to re-evaluation, which creates new versions.

## 4. External AI providers (LLM)

Off by default (ADR-026). May be enabled only when the platform flag **and** the organisation's
`llm_enabled` policy are on, with a provider whose terms exclude training on customer data and a
signed data processing agreement. Contact details are removed and protected attributes masked
before any call; outputs pass the grounding validator; prompts are versioned and hashed.

## 5. Monitoring

- Daily AI quality counters per organisation and vacancy (bands, grounding drops, verification
  overrides); quarterly AI quality report.
- Alert when more than 30 % of AI suggestions are overridden for a vacancy (the rubric may be wrong).
- Candidate and HR complaints about AI are logged and reviewed by the governance owner.

## 6. Kill-switch

AI screening can be switched off for the whole platform or one organisation at any time (platform
admins, or the organisation itself through its policy). While off, applications go to manual review
with no AI output and nothing is lost. Procedure: `docs/runbooks/disable-ai.md`. Use it without
hesitation when output may be harmful; switching back on requires the release gate in §3.

## 7. Prohibited uses

Automatic rejection or ranking without human review; emotion, personality, voice or video analysis;
social-media scraping; inferring protected attributes; using candidate data to train models; using
an assessment for any vacancy other than the one applied for without the candidate's consent.

## 8. Review

This policy is reviewed at least yearly and whenever the law, the engine or a provider changes.
