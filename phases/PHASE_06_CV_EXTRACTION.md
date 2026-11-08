# PHASE 06 — Document Ingestion & CV Extraction (AI Part 1)

**Release:** MVP · **Modules:** M09, M24 (normalisation) · **Depends on:** Phase 04 (Phase 05 for notifications)
**Read first:** `docs/05_AI_ENGINE.md §1–7`, `docs/03 resumes`, `docs/07 E`, `docs/09 §3`

## Goal
Every accepted CV becomes structured, evidence-linked claims (with page/snippet/confidence), robust to formats,
scans and adversarial content, with protected data excluded — without ever inventing facts.

## Tasks
- [ ] **P06-T01** — Synthetic CV corpus generator `scripts/generate_synthetic_cvs.py` (python-docx + reportlab + Pillow for scanned rasterisation) producing ≥ 150 CVs per `docs/09 §3` with `labels.json` gold data. Commit generator + generated fixtures (small) — **no real CVs**.
- [ ] **P06-T02** — `ai_engine/contracts.py` pydantic models (DocumentText, Page, Block, ExtractedClaim, CandidateEvidence…) + `ENGINE_VERSION`.
- [ ] **P06-T03** — `extraction/pdf.py` (PyMuPDF dict extraction, column-aware reading order, hidden-text detection: colour ≈ background, size < 4 pt, out-of-bounds), pdfplumber fallback; `extraction/docx.py` (paragraphs, tables, headers/footers, text boxes); guards (pages, encryption, zip bomb) — run in subprocess with rlimits/timeouts (`extraction/sandbox.py`).
- [ ] **P06-T04** — `extraction/ocr.py` (trigger rules, 300 DPI render, Tesseract, per-page confidence) + `extraction/quality.py` (quality score, language detection, garbled CID detection → OCR fallback, possibly_not_cv classifier).
- [ ] **P06-T05** — `extraction/sections.py` heading detection (typography + lexicon incl. Zimbabwean "Industrial Attachment", "Referees", "Personal Details") — personal/references excluded from evaluation.
- [ ] **P06-T06** — `extraction/dates.py` all formats in `docs/05 §6.1`, precision flags, anomalies; `normalisation/experience.py` interval union, employment-kind classification (full-time/part-time/contract/internship/attachment/volunteer/self-employed).
- [ ] **P06-T07** — `extraction/parser.py` claim extraction for experience, education, certifications/licences, skills (Aho–Corasick over taxonomy aliases + embedding NN for candidates), projects, languages; each claim with page, offsets, snippet ≤ 300 chars, method, confidence, explicit/inferred.
- [ ] **P06-T08** — `normalisation/qualifications.py` map to qualification levels (ZIMSEC, NC/ND/HND, degrees, professional bodies, foreign → unknown/needs_verification); `normalisation/titles.py` job title normalisation (lowercase, seniority tokens, synonyms list).
- [ ] **P06-T09** — `extraction/pii.py` protected/irrelevant data detection (DOB/age, ZW national ID regex, passport, gender, marital, religion, tribe, health/HIV, political, photo) → `excluded_reason`; prompt-injection detector (`ai_engine/security/injection.py`) → flag. Unit tests with adversarial samples (EC-DOC-13/14/15/16).
- [ ] **P06-T10** — Embedding service (`matching/semantic.py` base): load model once per worker, batch encode, cache by hash (Redis), skill embeddings precompute command writing pgvector column.
- [ ] **P06-T11** — Django adapter `apps.resumes`: ExtractionRun, DocumentText (encrypted), ExtractedClaim, ClaimCorrection; task `extract_resume(document_id, application_id)` idempotent; orchestrator consuming `application.submitted` + `document.accepted` → when all required docs accepted → extract → emit `application.evidence_ready` or failure (`processing_error` after retries; candidate re-upload notification for corrupt/encrypted/not_cv). Application status `processing` set on start.
- [ ] **P06-T12** — Cross-application flags: same sha256 across different accounts (EC-APP-15), CV name vs account name mismatch (EC-APP-16) — low severity flags only.
- [ ] **P06-T13** — Candidate features: view "What we extracted from your CV" (wizard review step + documents page), submit corrections (EC-DOC-27), import to profile with confirmation.
- [ ] **P06-T14** — HR: extraction panel on application detail (claims grouped, snippet + page, flags banner), "Retry processing" action.
- [ ] **P06-T15** — Benchmark harness `ai_engine/tests/benchmark/run_extraction_benchmark.py` → metrics JSON + markdown report in `docs/reports/extraction_benchmark_<date>.md`; nightly CI job.

## Edge cases
EC-DOC-01..28, EC-AI-06 (extraction part), EC-AI-10/11 (idempotency), EC-OPS-04.

## Exit criteria
- [ ] Benchmark meets `docs/09 §5` extraction targets (parse success, experience F1, education mapping, skills P/R) or deviations are documented with an improvement plan approved in PROGRESS notes.
- [ ] 100 CVs extracted in ≤ 10 min on dev machine with 2 document workers (record timing).
- [ ] No claim without source snippet; protected data never present in evaluation inputs (test).
- [ ] Failures always visible to HR and candidate; no application lost.
