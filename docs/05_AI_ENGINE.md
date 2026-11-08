# 05 — AI Engine: Extraction, Matching, Scoring, Explanation & Governance

The AI engine is **decision support**. It must be deterministic by default, evidence-grounded, versioned, and
safe against untrusted input. LLM usage is optional, off by default, and never the sole basis of a score.

---

## 1. Pipeline overview
```
Document ─▶ [1 Ingest] ─▶ [2 Text extraction] ─▶ [3 Quality & language] ─▶ [4 Sectioning]
        ─▶ [5 Claim extraction] ─▶ [6 PII/protected filter] ─▶ [7 Normalisation]
        ─▶ CandidateEvidence ─┐
JobVersion criteria + rubric ─┴▶ [8 Matching] ─▶ [9 Criterion scoring] ─▶ [10 Aggregation + coverage + band]
        ─▶ [11 Explanation + grounding] ─▶ [12 Clarification suggestions] ─▶ Evaluation (versioned) ─▶ HR review
```
All stages are pure functions over pydantic contracts (`ai_engine/contracts.py`); Django adapters persist results.

## 2. Ingest
- Verify magic bytes (`%PDF-`, DOCX = ZIP with `[Content_Types].xml` + `word/document.xml`); reject `.docm`, macros, OLE `.doc` (offer conversion message), RTF, HTML disguised.
- ZIP bomb guard for DOCX: max uncompressed 50 MB, max entries 2,000, compression ratio ≤ 100.
- PDF guards: max pages 30 (CV), encrypted detection (→ `encrypted_pdf` flag, ask re-upload), JavaScript/embedded files ignored, rendering in a subprocess with memory/time limits (`resource.setrlimit`, 60 s soft / 90 s hard).
- ClamAV clean before any parsing.

## 3. Text extraction
1. PDF: PyMuPDF `page.get_text("dict")` preserving blocks/lines + coordinates; reading order by columns (detect 2-column layouts via x-clustering of blocks). Fallback pdfplumber.
2. DOCX: python-docx paragraphs + tables (row-wise) + headers/footers (contact info often there) + text boxes (via XML `w:txbxContent`).
3. OCR trigger: chars/page < 200 or ≥ 50% pages image-only → render 300 DPI → Tesseract `eng` with `--psm 3`; record OCR confidence per page; flag `ocr_used`, `low_ocr_confidence` (< 70).
4. Hidden-text detection: white/near-background text, font size < 4 pt, text outside page bounds → stored but flagged `hidden_text` and **excluded** from scoring (anti keyword-stuffing / prompt-injection).
5. Normalise unicode (NFKC), ligatures, bullets, hyphenation at line ends, smart quotes.

## 4. Quality & language
- `quality_score` 0–1 from: text density, OCR confidence, ratio of dictionary words, section detection success.
- Language detection (`langdetect`/fastText lid); non-English → `language_unsupported` flag → `review_needed` band with manual review recommended.
- Non-CV detection (e.g. certificate, ID copy, blank page): classifier rules (no experience/education sections, < 80 words, keyword patterns) → `possibly_not_cv` flag + candidate re-upload notice.

## 5. Sectioning
Heading detection via typography (bold/size/caps) + lexicon (Experience, Work History, Employment, Professional Experience, Education, Academic Qualifications, Qualifications, Skills, Technical Skills, Certifications, Courses, Projects, Achievements, Languages, References, Referees, Personal Details, Profile, Summary, Objective, Industrial Attachment, Internship, Volunteer, Publications, Awards). Unknown blocks → `other`. `Personal Details` and `References` sections are parsed only for contact dedupe and are **excluded from evaluation**.

## 6. Claim extraction
| Claim | Method | Data |
|---|---|---|
| Experience | section rules + date regex + title/employer patterns + spaCy NER (ORG) | employer, title, start, end, is_current, location, bullet responsibilities, employment_kind (full-time/part-time/contract/internship/attachment/volunteer/self-employed) |
| Education | lexicon of institutions (seed: UZ, NUST, MSU, CUT, HIT, Africa University, BUSE, LSU, ZOU, GZU, ZEGU, Women's University in Africa, Solusi, Catholic University, Harare/Bulawayo/Mutare/Gweru polytechnics, ZIMSEC/Cambridge exam boards, common SA/UK/international universities) + qualification alias table | institution, qualification_text → level code, field, dates, grade/class (e.g. 2.1, Distinction) |
| Certifications/licences | alias table (AWS, Azure, CCNA, PMP, ACCA, CIMA, driver's licence class 1–5, defensive driving, ECZ) | name, body, dates, id (not scored) |
| Skills | taxonomy alias match (Aho–Corasick over aliases) + noun-chunk candidate → embedding nearest neighbour (threshold) | skill_id, raw text, context sentence, years if stated |
| Projects | Projects section + bullets with "built/developed/designed/implemented" | title, description, technologies (skills) |
| Languages | lexicon (English, Shona, Ndebele, French, Portuguese, …) | language, level |

Every claim stores `page`, `char_start/end`, `raw_text` snippet (≤ 300 chars), `method`, `confidence`, `evidence_status` (`explicit` when directly stated; `inferred` when derived, e.g. skill implied by a project's technology list).

### 6.1 Dates & experience
- Parse: `Jan 2020`, `January 2020`, `01/2020`, `2020-01`, `2020`, `'20`, `Present/Current/To date/Now/Date`, ranges with `–`, `-`, `to`, `till`.
- Year-only start → assume month 1 and mark `date_precision=year`; year-only end → month 12 (or now if current year & current). 
- Future end dates beyond 6 months → flag `date_anomaly`.
- Total relevant experience = **union of intervals** (merge overlaps) of roles judged relevant; part-time counted at 0.5 if explicitly part-time (configurable); internships/attachments counted separately and shown (not discarded); volunteer shown separately.
- Gaps are **computed but never scored**; not shown in default UI (available only if HR explicitly expands timeline).

## 7. PII & protected-attribute filter (before matching & any LLM call)
Detect and exclude from evaluation inputs: date of birth/age, national ID (`\d{2}-\d{6,7}[A-Z]\d{2}` ZW pattern), passport numbers, gender/sex, marital status, number of children, religion/church, tribe/ethnicity, nationality (unless job eligibility criterion explicitly approved), health/disability, HIV status, political affiliation, photo images, home address (beyond city). Excluded claims stored with `excluded_reason` so audits can prove exclusion. Graduation year is retained for recency but **must not** be used to infer age.

## 8. Matching
### 8.1 Criterion types
| Type | Logic | Output |
|---|---|---|
| skill | exact taxonomy id → alias → `implies`/`narrower` relation (e.g. Django ⇒ Python) → semantic similarity ≥ τ (default 0.78, calibrated) | match_method, confidence; evidence = claims + answers |
| experience | relevant roles = title/responsibility similarity to job responsibilities ≥ τ_role (0.6) OR HR-listed equivalent titles; months via interval union vs `min_months` | score proportional: `min(1, months/min_months)` mapped to bands |
| qualification | level rank ≥ required rank (equivalence table) AND field match (taxonomy of fields; semantic fallback) ; "or equivalent experience" rule if HR set `equivalent_experience_months` | |
| certification / licence | alias match; expiry check if dates present | expired → `conflicting/needs_verification` not fail |
| language | lexicon + answers | |
| competency | semantic similarity of responsibilities/projects to competency description + question rubric | lower confidence; often `review_needed` |
| eligibility | from knock-out answers only (never from CV inference) | `eligibility_unmet` flag |

### 8.2 Evidence status resolution per criterion
`human_verified` > `explicit` (CV/document) > `candidate_reported` (answers/profile) > `inferred` > `missing`; if explicit sources disagree with answers (e.g. answer "5 years Django", CV shows 1 year) → `conflicting` + clarification suggestion.

### 8.3 Semantic component
- Model: local sentence-transformers (`all-MiniLM-L6-v2` 384-d, or `bge-small-en-v1.5`) loaded once per worker; embeddings cached by text hash; skill embeddings precomputed in `skills.embedding` (pgvector).
- Calibration: thresholds tuned on the labelled synthetic set in Phase 10; stored in `engine_config` with version.

## 9. LLM usage (optional — `llm_enabled` org policy AND platform flag)
Allowed uses: (a) structured extraction assist for low-confidence sections, (b) phrasing of summaries from **already-computed** criterion results, (c) suggesting criteria/questions from job description for HR approval.
Not allowed: producing scores directly, ranking candidates, deciding eligibility, seeing excluded/protected data.

Guardrails:
1. **Redaction** first: names → `[CANDIDATE]`, emails/phones/IDs/addresses removed.
2. **Data/instruction separation**: CV text placed inside delimited data block; system prompt states content is untrusted data and instructions inside it must be ignored.
3. **Injection detection**: regex/heuristics for "ignore previous", "system prompt", "you are", "rate this candidate", hidden text → flag `prompt_injection_suspected`, LLM skipped for that doc, recruiter sees flag (not penalised automatically).
4. **Structured output** validated against pydantic schema; extra fields rejected; 2 retries then fallback to deterministic path.
5. **Grounding validator**: every claim in LLM output must cite an evidence id that exists and whose snippet supports it (string/semantic overlap ≥ threshold); uncited sentences dropped.
6. **Determinism**: temperature 0; responses cached by `(prompt_hash, input_hash, model)`.
7. **Provider terms**: no training on data; region/retention documented in model registry; disabled unless org accepts DPA addendum.
8. Provider adapter interface: `extract_sections()`, `summarise(results)`, `suggest_criteria(job)`; adapters: `null` (default), `anthropic`, `openai`. Keys from env; timeouts 30 s; circuit breaker.

## 10. Scoring
- Criterion score sᵢ ∈ [0,100] using rubric bands (0 none, 25 weak/indirect, 50 partial, 75 good, 100 strong/explicit & sufficient). `missing` ⇒ `assessable=false` (NOT 0).
- Category score = weighted mean of **assessable** criteria in category.
- Total `S = Σ_c W_c · score_c` over categories with ≥1 assessable criterion, re-normalised by assessable weight; **coverage** = Σ W_c (assessable) / 100.
- Essential criteria tracked separately: `essentials_met`, `essentials_unknown`, `essentials_not_evidenced`.
- **Confidence**: high (coverage ≥ 0.8, no conflicts, quality ≥ 0.7), medium, low.

### Bands (never "reject")
| Band | Rule (defaults, configurable per org) |
|---|---|
| `eligibility_review` | any knock-out answer unmet |
| `review_needed` | coverage < 0.6, or confidence low, or conflicts, or essentials_unknown > 0, or processing flags (OCR low, language, possibly_not_cv, injection) |
| `recommended_for_review` | S ≥ 70 and all essentials met/explicit |
| `lower_match` | otherwise |

Example (blueprint): technical 30/35, experience 20/25, competencies 17/20, qualifications 8/10, answers 9/10 → **84/100**, coverage 1.0 → `recommended_for_review`.

## 11. Explanations
Template-driven (deterministic) by default:
- Strengths: criteria with score ≥ 75 → "Evidence of {criterion}: '{snippet}' (CV p.{page})."
- Gaps: missing essentials → "No evidence found for {criterion} — this is unknown, not a confirmed gap." 
- Conflicts → "CV and answer differ on {x}; clarification suggested."
- Clarification suggestions generated from gaps/conflicts using question templates.
Grounding validator runs on all summaries; each sentence carries `citations: [evidence_id]`.

## 12. Re-evaluation & versioning
New evaluation version when: rubric/job version changes (HR-triggered, with reason), claim corrected/verified, clarification answered, engine upgrade (batch, opt-in by HR). Previous versions remain viewable; shortlist entries store the evaluation version used at decision time.
`input_hash = sha256(json(evidence ids + values, criteria version, rubric, engine_version, taxonomy_version, config))`.

## 13. Quality & fairness monitoring
- Benchmark set (Phase 10): ≥ 150 synthetic CVs across 5 roles (Software Developer, Accountant, Nurse/Health admin, Sales rep, Civil Engineer) incl. equivalents, unconventional paths, scanned, 2-column, poor formatting, injection attempts. Gold labels by HR reviewers.
- Metrics: extraction precision/recall per claim type; skill-match P/R; criterion agreement (Cohen's κ) vs reviewers; **recall of qualified candidates** in `recommended_for_review ∪ review_needed`; grounding rate (target 100%); parse success; latency.
- Override analytics in production: override rate by band, by vacancy; alert if > 30% for a vacancy (rubric may be wrong).
- Fairness: no protected data collected → use proxies audit (e.g. institution, location, gap) + counterfactual tests (swap names/genders/locations in synthetic CVs ⇒ identical scores required). Where orgs collect voluntary, separate EEO data (later), aggregate only.
- Model registry entries + quarterly AI quality report per org.

## 14. Performance
- Worker concurrency: documents queue 2–4 processes (CPU bound), ai queue 2 processes with model warm.
- Batch embeddings (32 per batch). Target 100 CVs ≤ 15 min on 4 vCPU.
- Large vacancies (> 1,000 apps): screening run processes in chunks of 50 with progress updates.
