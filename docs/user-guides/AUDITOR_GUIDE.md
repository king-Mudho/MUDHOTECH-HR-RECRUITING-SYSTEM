# Auditor guide

Auditors have **read-only** access to an organisation's records for governance and compliance. They
cannot change vacancies, applications or decisions.

## 1. What you can see

- Vacancies, their versions and rubrics (criteria, weights, essential flags and justifications).
- Applications and their status history, with candidate personal details **redacted by default**.
- **Audit log** (Settings → Audit): every sensitive action with actor, time, before/after values and
  request id; the log is hash-chained and can be exported to CSV.

## 2. Reconstructing a decision

On an application choose **Reconstruct decision** to see, for that point in time: the job version and
rubric, each AI evaluation version (engine, configuration, model and taxonomy versions, input hash,
evidence references), who made each status change and why, shortlist decisions (approver, applied
time) and the notifications sent. Download it as a PDF for a file.

## 3. Checks worth running

- **Human control**: consequential outcomes (shortlisted, not selected, offer, hired) always show a
  human actor and a reason. Platform staff can run `manage.py check_human_decisions` (exits non-zero
  if any exist without one).
- **Overrides**: Reports → AI suggestions and human decisions shows how often people went against the
  AI band, by band and vacancy.
- **Privacy**: rights requests and their deadlines, legal holds, retention runs and consent records.
- **Access**: the access log records who viewed candidate data and CVs.

## 4. Limits

Auditors never see AI scores presented as decisions, protected attributes (none are collected), or
data from other organisations.
