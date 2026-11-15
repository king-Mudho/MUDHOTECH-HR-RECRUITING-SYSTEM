# Extraction benchmark — 2026-11-15

Engine `0.3.0` · synthetic corpus v1.0.0 (seed 2026, 150 CVs) · Tesseract: yes · semantic model: yes · 12 CPUs

## Targets (docs/09 §5)

| Metric | Value | Target | Result |
|---|---|---|---|
| parse_success_text | 1.0 | >= 0.98 | pass |
| parse_success_all | 1.0 | >= 0.9 | pass |
| experience_f1 | 0.948 | >= 0.85 | pass |
| education_level_accuracy | 1.0 | >= 0.9 | pass |
| skill_precision | 0.9831 | >= 0.85 | pass |
| skill_recall | 0.9932 | >= 0.8 | pass |
| grounding_rate | 1.0 | >= 1.0 | pass |
| determinism | 1.0 | >= 1.0 | pass |
| protected_leaks | 0 | <= 0 | pass |
| seconds_per_100_cvs | 129.0 | <= 600 | pass |

## All metrics

| Metric | Value |
|---|---|
| parse_success_text | 1.0 |
| parse_success_all | 1.0 |
| expected_failures_detected | 1.0 |
| experience_precision | 0.9518 |
| experience_recall | 0.9442 |
| experience_f1 | 0.948 |
| employment_kind_accuracy | 0.9916 |
| total_months_exact | 0.9571 |
| total_months_mean_abs_error | 0.41 |
| education_found | 0.9972 |
| education_level_accuracy | 1.0 |
| foreign_qualifications_flagged | 1.0 |
| certification_recall | 0.9881 |
| language_recall | 1.0 |
| skill_precision | 0.9831 |
| skill_recall | 0.9932 |
| equivalent_wording_recall | 0.7556 |
| protected_recall | 1.0 |
| protected_false_positive_cvs | 0 |
| protected_leaks | 0 |
| injection_precision | 1.0 |
| injection_recall | 1.0 |
| hidden_text_precision | 1.0 |
| hidden_text_recall | 1.0 |
| grounding_rate | 1.0 |
| determinism | 1.0 |
| claims | 2160 |
| ms_per_cv_median | 21.9 |
| ms_per_cv_p95 | 249.3 |
| seconds_per_100_cvs | 129.0 |

## Throughput

100 CVs, 2 parallel sandboxed workers: **129.0 s** (0 failed).

## Notes

- skill_precision counts skills read from the skills section against the labelled skills; mentions inside duties are real but unlabelled, so they are not counted.

## Misses (first 40)

- cv_005_hr_officer_strong.pdf: missed role ('Human Resources Officer', 'Delta Beverages')
- cv_005_hr_officer_strong.pdf: missed role ('Human Resources Officer', 'CBZ Services')
- cv_005_hr_officer_strong.pdf: missed role ('Industrial Attachment Student', 'Zimplats Holdings')
- cv_041_software_developer_weak.pdf: missed role ('Junior Software Developer', 'Msasa Systems')
- cv_053_registered_nurse_partial.pdf: missed role ('Senior Nursing Sister', 'Chitungwiza Central Hospital')
- cv_053_registered_nurse_partial.pdf: missed role ('Industrial Attachment Student', 'Avenues Clinic')
- cv_090_hr_officer_weak.pdf: missed role ('HR Intern', 'Zimplats Holdings')
- cv_100_hr_officer_partial.pdf: missed role ('Part-time Human Resources Officer (weekends)', 'Freelance')
- cv_100_hr_officer_partial.pdf: missed role ('Senior HR Officer', 'Meikles Hospitality')
- cv_100_hr_officer_partial.pdf: missed role ('HR Business Partner', 'Zimplats Holdings')
- cv_112_accountant_partial.pdf: missed role ('Finance Officer', 'Hunyani Retail')
- cv_130_hr_officer_partial.pdf: missed role ('Industrial Attachment Student', 'Zimplats Holdings')
- cv_147_accountant_weak.pdf: missed role ('Part-time Accountant (weekends)', 'Freelance')
- cv_147_accountant_weak.pdf: missed role ('Assistant Accountant', 'Lowveld Sugar Estates')
