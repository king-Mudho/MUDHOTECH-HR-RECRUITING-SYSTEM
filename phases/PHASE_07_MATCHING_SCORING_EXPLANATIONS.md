# PHASE 07 — Matching, Scoring & Explainable Evaluation (AI Part 2)

**Release:** MVP · **Modules:** M10, M11, M24 · **Depends on:** Phase 06
**Read first:** `docs/05_AI_ENGINE.md §8–14`, `docs/03 screening`, `docs/04 HR screening`, `docs/07 F`

## Goal
Each application receives a deterministic, versioned, evidence-cited evaluation against its job version's approved
rubric, with coverage, confidence, a non-rejecting band, grounded explanations and clarification suggestions.

## Tasks
- [ ] **P07-T01** — `matching/rules.py` deterministic checks: qualification rank vs required (equivalence + "or equivalent experience"), certifications/licences (expiry → flag), min experience months, language.
- [ ] **P07-T02** — `matching/skills_match.py` cascade exact → alias → relations (`implies`, `narrower`) → semantic (threshold from engine config); output method + confidence + evidence ids; distinguish skill listed-only vs used-in-role/project (band 50 vs 75/100) (EC-DOC-24).
- [ ] **P07-T03** — `matching/experience_match.py` role relevance (title/responsibility similarity, HR equivalent titles) + months via interval union; internships/attachments per rubric config.
- [ ] **P07-T04** — `matching/answers.py` question scoring per rubric mode (exact/options/range/rubric_text keyword-criteria/human) ; knock-out → `eligibility_unmet`; `matching/conflicts.py` CV vs answers conflicts (years, skills claimed, qualifications) (EC-AI-03).
- [ ] **P07-T05** — `evaluation/scoring.py` criterion bands, category aggregation over assessable criteria, total with re-normalisation, coverage, essentials summary, confidence; `evaluation/bands.py` per `docs/05 §10` (configurable thresholds in org policy, defaults); objection to automated processing → `manual_review_requested` (EC-AI-12).
- [ ] **P07-T06** — `explanations/templates.py` deterministic strengths/gaps/conflicts sentences with citations; `explanations/grounding.py` validator (every sentence has ≥1 valid evidence id whose snippet supports it); `explanations/clarifications.py` suggestions from gaps/conflicts.
- [ ] **P07-T07** — `ai_engine/llm/` provider interface + `null_adapter` (default) + `anthropic_adapter` + `openai_adapter` (behind platform flag AND org `llm_enabled`), redaction, data/instruction separation, pydantic schema validation, retries, circuit breaker, caching by (prompt_hash,input_hash,model); versioned prompts in `llm/prompts/*.md`; used only for summary phrasing and low-confidence section assist. Tests use mocked providers incl. malicious/malformed outputs (EC-AI-07).
- [ ] **P07-T08** — `versioning.py` input_hash; determinism test (EC-AI-08); counterfactual fairness tests: swap names/genders/locations/institution-town in synthetic CVs → identical scores (EC-AI-13).
- [ ] **P07-T09** — Django `apps.screening`: ScreeningRun, Evaluation, CriterionResult, EvaluationEvidence, HumanVerification models; task `evaluate_application` (ai queue, idempotent upsert by (application, version)); on success set application `under_review` + denormalised band/score/coverage + outbox `screening.completed`; on failure retries → `processing_error`.
- [ ] **P07-T10** — Screening runs API: start/retry for scope (all/pending/failed/selected) with chunking (50) and progress counts; re-evaluation on job new version (HR choice + reason) (EC-AI-09/EC-JOB-06), on claim verification/correction, on clarification answer — each creates a new evaluation version; previous marked `superseded` but retained.
- [ ] **P07-T11** — Human verification API (`/hr/claims/{id}/verify`): confirm/correct/reject → evidence status `human_verified` → optional re-evaluation.
- [ ] **P07-T12** — Vacancy-level analytics for screening: score/band distribution, low-coverage warning (EC-AI-15), high-score saturation info (EC-AI-14).
- [ ] **P07-T13** — Frontend: `/hr/jobs/[id]/screening` (runs, progress bar, failures with retry, distribution chart with table alternative, warnings); evaluation view components `ScoreBreakdown` (category bars + coverage hatch), `CriteriaPanel` (status, band, method, confidence, evidence, verify actions), explanation with clickable citations; all labelled "AI-assisted suggestion — requires human review".
- [ ] **P07-T14** — Model registry seed entries (embedding model, rules engine version, null LLM) and `ai_quality` metrics capture hooks.
- [ ] **P07-T15** — Benchmark: matching & recall harness against gold labels → report `docs/reports/screening_benchmark_<date>.md`.

## Edge cases
EC-AI-01..17, EC-DOC-24.

## Exit criteria
- [ ] Blueprint example reproduces: 30/35, 20/25, 17/20, 8/10, 9/10 → 84/100 (unit test with constructed evidence).
- [ ] Recall of gold-qualified candidates in (recommended ∪ review_needed) ≥ 0.95 on synthetic set; grounding 100%; determinism 100%; counterfactual invariance 100%.
- [ ] Missing evidence never produces a 0 score for a criterion (property test).
- [ ] 100 applications evaluated after extraction in ≤ 5 min on dev machine (record).
