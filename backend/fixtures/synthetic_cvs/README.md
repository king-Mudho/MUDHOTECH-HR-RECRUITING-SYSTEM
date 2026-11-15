# Synthetic CV corpus (P06-T01, docs/09 §3)

**Every person, phone number, e-mail address and document here is invented.** Never add real CVs
or real personal data to this folder (or anywhere in the repository).

Regenerate (deterministic: the same seed gives byte-identical files, except the encrypted PDFs,
whose AES salt is random by design):

```
backend/.venv/Scripts/python scripts/generate_synthetic_cvs.py          # 150 CVs, seed 2026
```

`backend/tests/test_synthetic_corpus.py` fails if this folder no longer matches the generator.
After regenerating without changing the generator, only the five encrypted PDFs differ; restore
them (`git checkout -- backend/fixtures/synthetic_cvs`) rather than committing that churn.

## What is in it

- 150 CVs: 5 roles (software developer, accountant, registered nurse, data analyst, HR officer)
  x strong / partial / weak profiles; formats PDF (text), DOCX and scanned (image-only PDF).
- Variations, each at least 5 times: two-column layout, experience tables, scanned, French,
  encrypted, corrupted (truncated), hidden text (white, 1.5 pt, off-page), prompt injection,
  employment gaps, overlapping jobs, attachment-only experience, Zimbabwean qualifications
  (ZIMSEC, HND, National Diploma/Certificate, RGN, IPMZ), foreign qualifications, equivalent
  wording (synonyms instead of skill names), personal/protected details, DOCX header/footer contact.
- `labels.json` - gold data per CV: expected parse outcome, OCR need, experience (titles,
  employers, ISO months, kind), total experience with overlaps counted once, education with
  levels, certifications, skills and the exact phrases used, languages, protected fields present,
  hidden/injected text, per-criterion expected evidence (`met` / `partial` / `missing` /
  `needs_verification` / `not_assessable` - missing evidence is never a fail) and an HR reference
  suitability. Used by the extraction benchmark (P06-T15).
