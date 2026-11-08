# 03 — Database Schema (PostgreSQL via Django ORM)

Conventions: every table has `id uuid pk`, `created_at timestamptz`, `updated_at timestamptz`.
Tenant tables add `organisation_id uuid not null fk` + index `(organisation_id, …)`. `created_by` / `updated_by`
nullable FK to users where relevant. Enums are Django `TextChoices`. JSON = `jsonb`. Soft delete is NOT used
generally — use explicit statuses; anonymisation for privacy deletes.

---

## core
**outbox_events** — event_type, aggregate_type, aggregate_id uuid, organisation_id null, payload jsonb, dedupe_key unique, status(pending|published|failed), attempts int, available_at, published_at, last_error text. Index (status, available_at).
**processed_events** — consumer str, event_id uuid; unique(consumer, event_id).
**idempotency_keys** — user_id, key str, endpoint str, request_hash, response_status, response_body jsonb, expires_at; unique(user_id, key, endpoint).
**feature_flags** — key unique, enabled bool, organisation_id null (override), rollout jsonb.
**dead_letters** — task_name, args jsonb, error, traceback, organisation_id, resolved_at, resolved_by.

## accounts
**users** (custom `AbstractBaseUser`) — email citext unique, email_verified_at, first_name, last_name, preferred_name, phone_e164 null, is_active, is_staff (Django admin only), platform_role (none|platform_admin|platform_support), last_login, password, locale default 'en', timezone default 'Africa/Harare', deleted_at null (anonymised marker).
allauth tables (email addresses, MFA authenticators), django sessions.
**user_session_meta** — session_key, user_id, ip (truncated /24 after 30 days), user_agent, created_at, last_seen_at, revoked_at.

## organisations
**organisations** — name, slug unique, legal_name, registration_number null, industry, size_band, country default 'ZW', city, address, website, logo_key, description (sanitised), status(pending_verification|active|suspended|closed), verified_at, verified_by, default_timezone, default_currency, plan_id null (v1.1), settings jsonb (see policies).
**organisation_policies** — organisation_id unique, privacy_notice md, retention_months int default 12, duplicate_policy(one_active|allow_resubmit_replace|allow_multiple), shortlist_dual_control bool default false, rubric_dual_control bool default false, ai_enabled bool default true, llm_enabled bool default false, blind_review_default bool default true, notification_delay_minutes int default 15, hide_ai_from_panelists bool default true, rights_request_sla_days int default 30, version int.
**departments** — organisation_id, name; unique(org, name).
**locations** — organisation_id, name, city, country, workplace_type_default.
**memberships** — organisation_id, user_id, role(org_admin|hr_manager|recruiter|hiring_manager|panelist|auditor), status(active|deactivated), invited_by, joined_at; unique(org, user).
**invitations** — organisation_id, email citext, role, token_hash unique, expires_at, accepted_at, revoked_at, invited_by, vacancy_ids jsonb.

## taxonomy
**skills** — taxonomy_version, canonical_name, slug unique, category, description, embedding vector(384), is_active, organisation_id null (org custom).
**skill_aliases** — skill_id, alias citext, unique(alias, organisation_id).
**skill_relations** — from_skill, to_skill, relation(broader|narrower|related|implies), weight float.
**qualification_levels** — code (e.g. ZW_OLEVEL, ZW_ALEVEL, ZW_NC, ZW_ND, ZW_HND, BACHELOR, HONOURS, PGDIP, MASTERS, PHD), name, rank int, framework (ZW|INTL), description.
**qualification_aliases** — level_id, alias citext (e.g. "BSc Hons", "B.Tech", "HND", "Ordinary Level", "5 O' Levels").
**professional_bodies** — code (ACCA, CIMA, ICAZ, CIPS, ECZ, NCZ, LSZ, …), name, country, designations jsonb.
**taxonomy_versions** — version str unique, notes, published_at.

## jobs
**jobs** — organisation_id, department_id, title, slug, reference_code, status(draft|in_review|approved|scheduled|published|paused|closed|archived), current_version_id, published_version_id, workplace_type, employment_type, seniority, openings int, location_ids (m2m `job_locations`), closes_at timestamptz, timezone, publish_at null, published_at, closed_at, close_reason, salary_min, salary_max, salary_currency, salary_period, salary_disclosed bool, start_date, lock_version int (optimistic), search_vector tsvector (GIN), created_by.
  - unique(organisation_id, slug); index(status, closes_at); GIN(search_vector).
**job_versions** — job_id, number int, status(draft|approved|superseded), snapshot jsonb (all ad fields), summary, responsibilities_html, requirements_html, benefits_html, required_documents jsonb, approved_by, approved_at, rubric_id, questionnaire_id; unique(job_id, number). Immutable after approved (enforced in service + DB trigger optional).
**job_criteria** — job_version_id, organisation_id, order, type(skill|experience|qualification|certification|competency|language|licence|eligibility), importance(essential|preferred), title, description, evidence_guidance, justification (required when essential), skill_id null, qualification_level_id null, min_months null, equivalents jsonb, rubric_category(technical|experience|competency|qualification|answers), weight_within_category numeric.
**rubrics** — organisation_id, job_version_id, version int, categories jsonb [{key, label, weight, bands:[{score, descriptor}]}], sum check = 100 (DB check via service + constraint on stored total), status(draft|approved|locked), approved_by, approved_at.
**job_approvals** — job_version_id, step, approver_id, decision(approved|rejected|changes_requested), comment, decided_at.
**job_assignments** — job_id, membership_id, role_on_job(recruiter|hiring_manager|approver).
**job_events** — job_id, from_status, to_status, actor_id, reason, at.

## candidates
**candidate_profiles** — user_id unique, headline, summary, city, country, phone_e164, links jsonb, availability, notice_period_days, open_to_relocation, profile_completeness int, default_resume_id.
**candidate_experiences** — profile_id, employer, title, location, start_date, end_date null, is_current, description, source(manual|cv_import), source_claim_id null.
**candidate_educations** — profile_id, institution, qualification_text, qualification_level_id null, field, start_date, end_date, grade, source.
**candidate_certifications** — profile_id, name, body_id null, issued_at, expires_at, credential_id, source.
**candidate_skills** — profile_id, skill_id null, raw_name, proficiency null, years null, source; unique(profile, skill).
**candidate_languages** — profile_id, language, proficiency.

## documents
**upload_sessions** — owner_user_id, organisation_id null, purpose(cv|supporting|logo|message_attachment|offer_letter), declared_name, declared_mime, declared_size, object_key, status(pending|uploaded|scanning|accepted|rejected|expired), expires_at.
**documents** — owner_user_id, organisation_id null (null for candidate-library docs; access via application link), purpose, original_filename (sanitised), mime_detected, size_bytes, sha256, storage_key, bucket, page_count, scan_status(pending|clean|infected|error|skipped), scan_engine_version, scanned_at, rejected_reason, encrypted bool, language_detected.
  - index(sha256) for duplicate detection.

## applications
**applications** — organisation_id, job_id, job_version_id, candidate_user_id, candidate_profile_snapshot jsonb (frozen at submit), reference unique, status (see SRS §3.3), source(utm jsonb, channel), submitted_at, withdrawn_at, withdraw_reason, assigned_recruiter_id null, is_assisted bool, assisted_by null, consent_record_id, duplicate_of_id null, current_evaluation_id null, ai_band null (denormalised), coverage null, score null, flags text[] , tags text[], lock_version.
  - Partial unique index for `one_active` policy: unique(job_id, candidate_user_id) WHERE status NOT IN ('withdrawn','abandoned') — enforced only for jobs with that policy via service + this index on `active_key` column (nullable) to support policies.
  - index(organisation_id, job_id, status), index(organisation_id, ai_band), index(candidate_user_id).
**application_documents** — application_id, document_id, role(cv|cover_letter|certificate|transcript|portfolio|other), required_doc_key.
**application_status_events** — application_id, organisation_id, from_status, to_status, actor_id null (null only for system-safe transitions like processing), actor_type(human|system), reason_code, reason_text, metadata jsonb, at. Append-only.
**application_notes** — application_id, organisation_id, author_id, body, mentions uuid[], visibility(team|private).
**application_drafts_autosave** — (fields on application; drafts are applications in `draft`).

## questionnaires
**questionnaires** — organisation_id, job_version_id null, name, is_template bool, version, status(draft|approved).
**questions** — questionnaire_id, section, order, type, prompt, help_text, required, config jsonb (min/max/word_limit/options/allowed_types/unit), branching jsonb ({show_if:{question_id, op, value}}), scoring jsonb ({mode: none|exact|options|range|rubric_text|human, points, expected, rubric_bands}), is_knockout bool, criterion_id null, protected_topic_flag null, protected_exception_reason null.
**question_options** — question_id, order, label, value, points.
**question_responses** — application_id, question_id, value jsonb, document_id null, answered_at, version; unique(application_id, question_id).

## resumes (extraction)
**extraction_runs** — organisation_id null, document_id, application_id null, engine_version, parser_used, ocr_used bool, status(queued|running|succeeded|partial|failed), quality_score float, text_chars int, language, flags text[], error_code, timings jsonb, started_at, finished_at.
**document_texts** — extraction_run_id, page int, text (encrypted at rest via pgcrypto or app-level Fernet for PII columns), layout jsonb.
**extracted_claims** — extraction_run_id, application_id null, claim_type(experience|education|certification|skill|language|project|licence|contact|summary), data jsonb (normalised), raw_text, page, char_start, char_end, method(rule|ner|section|ocr|llm), confidence float, evidence_status(explicit|inferred), excluded_reason null (e.g. protected_attribute).
**claim_corrections** — claim_id, corrected_by_user_id, role(candidate|staff), before jsonb, after jsonb, reason, status(pending|accepted|rejected), at.

## screening
**screening_runs** — organisation_id, job_id, job_version_id, rubric_id, trigger(auto|manual|reevaluation|clarification), requested_by, engine_version, taxonomy_version, model_ids jsonb, status, counts jsonb, started_at, finished_at.
**evaluations** — organisation_id, application_id, screening_run_id, version int, status(succeeded|partial|failed|superseded), total_score numeric(5,2) null, coverage numeric(5,2), confidence(low|medium|high), band(recommended_for_review|review_needed|eligibility_review|lower_match), flags text[], summary text, summary_citations jsonb, clarification_suggestions jsonb, input_hash, engine_version, prompt_hash null, llm_used bool, created_at; unique(application_id, version).
**criterion_results** — evaluation_id, criterion_id, category, score numeric null, assessable bool, evidence_status, match_method(exact|alias|related|semantic|rule|answer|human), confidence, rationale, gaps text.
**evaluation_evidence** — criterion_result_id, claim_id null, question_response_id null, document_id null, page null, snippet, weight.
**human_verifications** — organisation_id, application_id, claim_id null, criterion_result_id null, verifier_id, decision(confirmed|corrected|rejected), note, at.

## shortlisting
**shortlists** — organisation_id, job_id, job_version_id, desired_size, status(draft|pending_approval|approved|rejected|superseded), proposed_by, approved_by (array for dual), approved_at, notes.
**shortlist_entries** — shortlist_id, application_id, decision(shortlist|not_selected|hold), reason_code, reason_text, ai_band_at_decision, score_at_decision, override bool, decided_by, decided_at.
**decision_reasons** — organisation_id null, code, label, applies_to(shortlist|not_selected|hold|override), active.

## messaging
**clarification_requests** — organisation_id, application_id, criterion_id null, questions jsonb, due_at, status(open|answered|expired|cancelled), requested_by, answered_at.
**message_threads** — organisation_id, application_id, subject, status.
**messages** — thread_id, sender_user_id, sender_role(staff|candidate|system), body (sanitised), attachment_document_ids uuid[], read_at.

## notifications
**notification_templates** — organisation_id null (platform default), key, channel(email|inapp|sms|whatsapp), locale, subject, body_md, variables jsonb, version, active.
**notifications** — recipient_user_id, organisation_id null, key, channel, payload jsonb, status(queued|sent|delivered|failed|suppressed), dedupe_key unique, provider_message_id, attempts, last_error, scheduled_for, sent_at, read_at (in-app).
**email_suppressions** — email citext unique, reason(bounce|complaint|manual), at.

## audit
**audit_events** — organisation_id null, actor_user_id null, actor_type(human|system|platform_support), action (e.g. `application.status_changed`, `cv.viewed`, `rubric.approved`, `export.created`), target_type, target_id, before jsonb (minimised), after jsonb (minimised), reason, ip_trunc, user_agent_hash, request_id, prev_hash, hash, at. Append-only (DB: revoke UPDATE/DELETE from app role; trigger rejects updates).
**access_logs** — high-volume PII view log (user, org, target, at) partitioned monthly.

## privacy
**consent_records** — user_id, organisation_id null, purpose(application_processing|ai_assisted_screening|talent_pool|marketing|sms|whatsapp), notice_version, granted bool, granted_at, withdrawn_at, ip_trunc.
**rights_requests** — user_id, organisation_id null, type(access|export|correction|deletion|objection_automated|consent_withdrawal), status(received|verifying|in_progress|completed|rejected), due_at, handled_by, resolution, export_document_id null.
**retention_runs** — organisation_id, started_at, finished_at, counts jsonb, dry_run bool.
**legal_holds** — organisation_id, target_type, target_id, reason, placed_by, released_at.

## platform / ai governance
**model_registry** — name, version, kind(embedding|ner|llm|rules), purpose, provider, data_policy, limitations, evaluation_report_doc_id, active_from, active_to.
**ai_quality_reports** — organisation_id null, job_id null, metrics jsonb (recall, precision, override_rate, grounding_rate, parse_success), period, created_by.
**support_access_grants** (break-glass) — platform_user_id, organisation_id, reason, granted_at, expires_at, revoked_at, approved_by.

## v1.1+ (interviews, offers, talent pool, billing, integrations)
**interviews** — organisation_id, application_id, stage, mode(in_person|video|phone), location_or_link, starts_at, ends_at, timezone, status(proposed|scheduled|completed|cancelled|no_show), created_by.
**interview_slots** — interview_id or job_id, starts_at, ends_at, capacity, booked_application_id.
**interview_panelists** — interview_id, membership_id, role(lead|member).
**scorecards** — interview_id, panelist_membership_id, criterion_scores jsonb, overall(1-5), recommendation(strong_yes|yes|no|strong_no), notes, submitted_at; unique(interview, panelist).
**offers** — organisation_id, application_id, status(draft|pending_approval|approved|issued|accepted|declined|expired|withdrawn), salary_amount, currency, period, start_date, contract_type, conditions, expires_at, letter_document_id, accepted_at, acceptance_meta jsonb, decline_reason.
**offer_approvals** — offer_id, approver_id, decision, comment, at.
**hire_records** — organisation_id, application_id unique, offer_id, start_date, recorded_by.
**talent_pool_entries** — organisation_id, candidate_user_id, consent_record_id, expires_at, tags, status; unique(org, candidate).
**plans** — code, name, limits jsonb, price_usd, price_zwg, interval, active.
**subscriptions** — organisation_id, plan_id, status(trialing|active|past_due|cancelled), current_period_start/end, cancel_at.
**usage_counters** — organisation_id, metric, period, value; unique(org, metric, period).
**invoices** — organisation_id, number unique, amount, currency, status(draft|open|paid|void), due_at, paid_at, pdf_document_id.
**payments** — invoice_id, provider(paynow|manual|stripe), method(ecocash|onemoney|card|bank), provider_reference, poll_url, status, amount, raw jsonb (no card data).
**webhook_endpoints** — organisation_id, url, secret_encrypted, events text[], active; **webhook_deliveries** — endpoint_id, event_id, status, attempts, response_code.
**api_keys** — organisation_id, name, prefix, key_hash, scopes text[], last_used_at, revoked_at.

## Integrity rules
1. All state transitions in services with `select_for_update()` on the row + status precondition.
2. Check constraints: salary_min ≤ salary_max; openings ≥ 1; rubric weights sum 100; score 0–100.
3. Unique public reference numbers via sequence per org/year (`application_ref_counters` table with row lock).
4. Encrypt sensitive text columns (CV text, messages) with app-level field encryption (key from env/KMS); key rotation supported via key id prefix.
5. Never store files in DB. Never store raw card data.
6. Migrations must be backward compatible for zero-downtime deploys (expand → migrate → contract).
