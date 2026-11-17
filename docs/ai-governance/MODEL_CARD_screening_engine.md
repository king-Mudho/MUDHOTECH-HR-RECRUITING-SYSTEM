# Model card — MHRS screening engine

| | |
|---|---|
| System | MUDHOTECH HR RECRUITING SYSTEM (MHRS) — AI-assisted application screening |
| Owner | MudhoTech Solutions (Pvt) Ltd, Harare, Zimbabwe |
| Versions covered | Engine `0.3.1`, matching thresholds `2026.11.2` (calibrated P10-T03, ADR-028), embedding model per `EMBEDDING_MODEL` (local sentence-transformers in production, `hashing-384` in tests), LLM provider `none` (default, ADR-026) |
| Live registry | `/admin/model-registry` (`ModelRegistryEntry`; every evaluation stores `engine_version` + `model_ids`) |
| Card date | 2026-11-17 (Phase 09, P09-T11). Review at every engine/threshold/model change and at least quarterly |

## 1. What it is

A **decision-support** pipeline, not a decision-maker. For one application against one published
vacancy it:

1. extracts text from the CV and other documents (PyMuPDF / pdfplumber / python-docx, Tesseract OCR
   fallback) inside a sandboxed subprocess;
2. extracts claims (experience, education, skills, certifications, languages) with rules, a skills
   taxonomy and dates normalisation; every claim links to its source (document, page, snippet);
3. matches claims and questionnaire answers to the vacancy's **HR-approved, versioned rubric**
   (exact taxonomy matches, synonyms/related skills, and local embedding similarity labelled
   *inferred*);
4. scores each criterion 0–100 (missing evidence = *not assessable*, never 0), aggregates by
   category weights, computes coverage and confidence;
5. assigns a **routing band** — `recommended_for_review`, `review_needed`, `eligibility_review`,
   `lower_match` or `manual_review_requested` — and template explanations whose every sentence cites
   evidence (grounding validator drops anything uncited).

There is **no reject band** and the engine can never set a consequential status (shortlisted, not
selected, offer, hired): those require an authenticated person and a recorded reason
(`check_human_decisions` verifies 0 exceptions).

An optional LLM (provider adapter: Anthropic / OpenAI) can write a short summary of an already
computed evaluation. It is **off by default**, needs both the platform flag and the organisation's
`llm_enabled` policy, receives redacted text only, and its output passes the same grounding check.

## 2. Intended use

- Help recruiters at employer organisations find and verify evidence across many applications and
  prioritise their reading.
- Users: HR managers, recruiters, hiring managers (shortlist-onward), platform staff (governance).

**Out of scope / not intended:** automatic rejection or ranking without review; any assessment of
protected attributes; personality, emotion, video or voice analysis; predicting job performance;
use outside the vacancy the candidate applied to; credit, immigration or law-enforcement purposes.

## 3. Inputs it never uses

Name, photo, age/date of birth, gender, marital status, pregnancy, ethnicity/tribe, religion,
political opinion, health/HIV status, disability, national ID. A PII filter removes or masks these
before matching and before any LLM call; the benchmark measures `protected_leaks = 0`.
Career gaps and CV layout are not scored.

## 4. Evaluation (synthetic data only — no real candidates)

Extraction benchmark (`docs/reports/extraction_benchmark_2026-11-15.md`, 150 synthetic CVs):
parse success 100 %, experience F1 0.948, education level accuracy 1.0, skill precision 0.983 /
recall 0.993, grounding 100 %, determinism 100 %, protected leaks 0.

Screening benchmark (`docs/reports/screening_benchmark_2026-11-16.md`, 135 CVs, gold labels):

| Metric | Result | Target |
|---|---|---|
| Recall of gold-suitable in recommended ∪ review needed | 100 % | ≥ 95 % |
| Explanation grounding | 100 % | 100 % |
| Determinism (re-evaluation identical) | 100 % | 100 % |
| Counterfactual invariance (name / gender / town swaps) | 121/121 | 100 % |
| Gold not-suitable placed in recommended | 0 % | informational |
| Criterion agreement with gold evidence | 95.8 % | informational |

Both benchmarks run nightly (`.github/workflows/nightly.yml`, `ai-benchmark` job) and fail the job
when a target is missed.

## 5. Known limitations

- Calibrated on a **synthetic** labelled set (`docs/reports/AI_VALIDATION_REPORT.md`); real-world
  calibration needs HR-labelled real applications. Treat bands as routing hints only.
- Conservative by design: missing essentials are *unknown*, so *review needed* is the largest band
  (95/135 in the benchmark). This costs reviewer time rather than excluding people.
- English-centric extraction and embeddings; other languages are flagged for manual review.
- Taxonomy coverage: skills outside the taxonomy match only literally or via embeddings (labelled
  inferred). Organisations can add custom skills.
- OCR quality varies on poor scans; low OCR confidence routes to *review needed*.
- Questionnaire answers are self-declared; conflicts with the CV are flagged, not resolved.

## 6. Fairness and safety controls

- Counterfactual invariance tests in CI/nightly; no protected data collected; proxy audit
  (institution, location, gaps) in the quarterly AI quality report.
- Blind review by default (ADR-013); hiring managers see shortlisted applications only.
- Prompt-injection detection on CV text (`ai_engine/security/injection.py`); CV instructions are
  never followed; a detected attempt is a flag for human review, not a penalty.
- Candidates may object to automated processing → `manual_review_requested` with no AI numbers
  anywhere (EC-AI-12).
- Override analytics (alert when > 30 % of AI suggestions are overridden for a vacancy).
- **Kill-switch** (platform and per organisation): `docs/runbooks/disable-ai.md`.

## 7. Versioning and traceability

Rubrics, job versions, evaluations, prompts and model versions are immutable once used.
Re-evaluation creates a new version with trigger and reason. Each evaluation stores the input hash,
engine version, taxonomy version, model ids and (if used) prompt hash, so any outcome can be
reconstructed (`/hr/audit/reconstruct`).

## 8. Data handling

Runs inside MHRS infrastructure. Candidate data is never used to train models. CV text, claims,
snippets and explanations are encrypted at rest (`EncryptedTextField`). Retention follows the
organisation's policy (P09-T05); erasure removes extracted data and evaluations (P09-T04).

## 9. Contacts

AI governance owner: MudhoTech Solutions — governance contact recorded in the DPA. Incidents:
`docs/runbooks/disable-ai.md`.
