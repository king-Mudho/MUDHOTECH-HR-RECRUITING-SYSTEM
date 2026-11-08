# 07 — Edge Cases & Business Rules Catalog

Each case has an ID referenced by phase tasks. Every case must have **at least one automated test** in the phase
that implements it (test name should include the EC id, e.g. `test_ec_app_04_double_submit_idempotent`).

## A. Accounts & identity (EC-ACC)
| ID | Scenario | Required behaviour |
|---|---|---|
| EC-ACC-01 | Same email with different case/whitespace | Normalise (lower+trim) + citext unique; login case-insensitive |
| EC-ACC-02 | Signup with existing email | Generic "check your email" response; send "you already have an account" email (no enumeration) |
| EC-ACC-03 | Unverified candidate tries to submit | Allow drafting; block submit with `email_unverified`; resend link |
| EC-ACC-04 | Verification link expired/used | Friendly page + resend |
| EC-ACC-05 | Brute-force login | Throttle per IP+account; progressive lockout 15 min after 10 fails; notify user |
| EC-ACC-06 | Password reset for non-existent email | Same generic response |
| EC-ACC-07 | User changes email while applications in progress | Re-verify new email; notifications go to verified address only; audit |
| EC-ACC-08 | Lost MFA device | Recovery codes; else org_admin/platform reset with identity check + audit |
| EC-ACC-09 | User is candidate AND staff in an org | Allowed; staff cannot view/evaluate own application (conflict-of-interest guard, 403 + audit) |
| EC-ACC-10 | Staff member applies to own company job | Application visible to HR managers only; the applicant-staff loses access to that vacancy's applications |
| EC-ACC-11 | Session hijack suspicion (new device/country) | Notify user; session list allows revoke |
| EC-ACC-12 | Deactivated staff with open sessions | All sessions revoked immediately |
| EC-ACC-13 | Account deletion request with active applications | Route via rights workflow; withdraw active applications after confirmation; anonymise per retention & legal holds |

## B. Organisations & team (EC-ORG)
| EC-ORG-01 | Two orgs same name | Allowed; slug de-duplicated (`acme-2`) |
| EC-ORG-02 | Remove/demote last org_admin | Blocked `conflict.last_admin` |
| EC-ORG-03 | Invitation to email already a member | Error `already_member` |
| EC-ORG-04 | Invitation expired / revoked / reused | Clear message; token single-use |
| EC-ORG-05 | Invitee signs up with different email than invited | Accept only if logged-in verified email matches (or org_admin explicitly allows) |
| EC-ORG-06 | User in multiple orgs sends request with X-Org-Id of org they don't belong to | 404/403, audit `tenant_violation_attempt` |
| EC-ORG-07 | Org suspended mid-recruitment | Public jobs hidden; candidates see "recruitment paused"; drafts preserved; staff read-only; processing paused |
| EC-ORG-08 | Unverified org tries to publish | Blocked `org_unverified` (default policy) |
| EC-ORG-09 | Recruiter leaves company with assigned vacancies | Deactivation prompts reassignment; unassigned vacancies surface on HR manager dashboard |
| EC-ORG-10 | Org deleted/closed | Closed state; data retained per policy then anonymised; candidates notified their applications are closed |

## C. Vacancies (EC-JOB)
| EC-JOB-01 | Publish with missing mandatory fields/approvals | Lint lists every failing check; publish 422 |
| EC-JOB-02 | Rubric weights ≠ 100 | Validation error; UI shows running total |
| EC-JOB-03 | All criteria essential | Allowed with warning (narrow funnel); requires justification each |
| EC-JOB-04 | Deadline in past / < 24 h | Past blocked; < 24 h warning |
| EC-JOB-05 | Deadline timezone differs from candidate timezone | Display both job TZ and viewer local; enforce in job TZ |
| EC-JOB-06 | Edit criteria after applications received | Creates new job version; existing applications keep old version; HR chooses re-evaluate all/new only, with reason |
| EC-JOB-07 | Two recruiters edit same draft | Optimistic lock → 409 with merge prompt |
| EC-JOB-08 | Pause during active drafts | Drafts kept; submit blocked with "paused" message; resume restores |
| EC-JOB-09 | Deadline extended | Drafts reactivated if abandoned within window; draft holders notified |
| EC-JOB-10 | Closed early (position filled) | Drafts abandoned with notice; submitted processed normally |
| EC-JOB-11 | Delete vacancy with applications | Not allowed; archive only |
| EC-JOB-12 | Job description with script/HTML injection | Sanitised; tests for XSS payloads |
| EC-JOB-13 | Slug collision / title change after publish | Slug stable after publish; old slugs redirect |
| EC-JOB-14 | Repost a closed job | Duplicate as new job; previous applicants not auto-moved |
| EC-JOB-15 | Salary in USD and ZWG | Multi-currency display; no FX conversion stored as fact |
| EC-JOB-16 | Job with zero applicants at deadline | Close normally; dashboard shows 0; option to extend |
| EC-JOB-17 | Vacancy with 5,000+ applications | Pagination/cursor, chunked screening, indexed filters, async exports |
| EC-JOB-18 | Scheduled publish time passes while system down | Beat catches up on restart (publish_at ≤ now) |
| EC-JOB-19 | Multiple openings (e.g. 5 nurses) | Shortlist desired size suggestion scales; offers until openings filled |
| EC-JOB-20 | Internal-only vacancy | Visibility `internal` (org members only) — v1.1; MVP: unlisted link option |

## D. Applications & submission (EC-APP)
| EC-APP-01 | 100 applicants submit simultaneously | All persisted; queue absorbs load; no request-path heavy work |
| EC-APP-02 | Applies twice (policy one_active) | Return existing draft/submitted application; 409 `duplicate_application` with link |
| EC-APP-03 | Re-apply after withdrawal | Allowed if job open and policy allows |
| EC-APP-04 | Double-click/retry submit | Idempotency-Key → single application, same response |
| EC-APP-05 | Submit exactly at deadline / clock skew | Server time authoritative; ≤ closes_at accepted; grace 0 s default (configurable) |
| EC-APP-06 | Session expires mid-wizard | Autosaved draft; re-login returns to same step |
| EC-APP-07 | Network drop during upload | Retry upload; presigned URL renew; partial uploads never attached |
| EC-APP-08 | Upload completed but not confirmed | Orphan cleanup job after 24 h |
| EC-APP-09 | Document still scanning at submit | Submit allowed; processing waits for scan; if infected → candidate asked to re-upload; application kept |
| EC-APP-10 | Required document missing | Submit blocked with field-level error |
| EC-APP-11 | Candidate edits after submit | Not allowed (except via clarification/correction or `allow_resubmit_replace` policy before deadline) |
| EC-APP-12 | Withdraw while processing | Processing tasks check status and stop; evaluation not shown to HR as active |
| EC-APP-13 | Withdraw after shortlist/offer | Allowed; recruiter notified; offer withdrawn |
| EC-APP-14 | Job closed while candidate on review step | Submit fails `deadline_passed`; draft kept read-only |
| EC-APP-15 | Same CV file used by two different accounts (sha256 match) | Flag `duplicate_document_across_accounts` for HR review (possible fraud or shared CV); no auto action |
| EC-APP-16 | CV name differs from account name | Flag `identity_mismatch_possible` (low severity), never auto-penalise |
| EC-APP-17 | Assisted application by staff | Flag is_assisted; candidate consent recorded; candidate gets account invite |
| EC-APP-18 | Candidate with no email (phone-only) | MVP requires email; assisted application path for those without (staff-created email-less record not allowed in MVP) |
| EC-APP-19 | Back button / multiple tabs editing draft | lock_version conflict → reload latest |
| EC-APP-20 | Very slow/low-bandwidth connection | Small payloads, autosave debounce, resumable uploads, progress indicators |
| EC-APP-21 | Browser without JS / old browser | Public job pages SSR readable; wizard requires JS with notice |
| EC-APP-22 | Candidate under minimum working age per job | Only via approved eligibility question; flagged for review, never auto-reject |
| EC-APP-23 | Referral/source tracking missing | Source = `direct` |

## E. Documents & CV parsing (EC-DOC)
| EC-DOC-01 | Image-only/scanned PDF | OCR; flag `ocr_used`; low confidence → `review_needed` |
| EC-DOC-02 | Corrupted/unreadable file | `processing_error` on document; candidate notified to re-upload; application kept |
| EC-DOC-03 | Password-protected PDF | `encrypted_pdf` flag; ask re-upload without password |
| EC-DOC-04 | .doc (legacy), .docm, .odt, .pages, .rtf | Reject at upload with guidance (save as PDF/DOCX) |
| EC-DOC-05 | File extension spoofing (exe renamed .pdf) | Magic-byte check rejects |
| EC-DOC-06 | Malware detected | Quarantined, never parsed; candidate notified generically; security audit event |
| EC-DOC-07 | ZIP bomb DOCX | Rejected by size/ratio guards |
| EC-DOC-08 | 100+ page PDF | Rejected > 30 pages for CV (configurable); supporting docs up to 50 |
| EC-DOC-09 | Two-column / table-heavy / creative template | Column-aware reading order; lower quality → flag |
| EC-DOC-10 | Contact info only in header/footer | Header/footer parsed |
| EC-DOC-11 | Non-English CV | `language_unsupported` → manual review band |
| EC-DOC-12 | Uploaded certificate/ID instead of CV | `possibly_not_cv` flag + re-upload request |
| EC-DOC-13 | Hidden white text keyword stuffing | Detected, excluded, flagged |
| EC-DOC-14 | Prompt injection text in CV | Detected, flagged, LLM skipped, deterministic path only, no penalty automatically |
| EC-DOC-15 | Photo on CV | Ignored; never processed for face/appearance |
| EC-DOC-16 | DOB, ID number, marital status, religion in CV | Excluded from evaluation (stored with excluded_reason) |
| EC-DOC-17 | Ambiguous dates ("2019–21", "Since 2020", "03/04/2019") | Parser rules + precision flag; impossible dates flagged |
| EC-DOC-18 | Overlapping jobs | Interval union for total months; both roles shown |
| EC-DOC-19 | Future dates / end before start | `date_anomaly` flag; excluded from months; clarification suggestion |
| EC-DOC-20 | Career gaps | Not penalised; not highlighted by default |
| EC-DOC-21 | Internships / industrial attachment / volunteer / freelance | Classified and shown; counted per rubric config, never discarded |
| EC-DOC-22 | Abbreviations (B.Sc, BSc Hons, HND, NC, ND) | Qualification alias table |
| EC-DOC-23 | Foreign qualifications | Mapped to levels where known; unknown → `needs_verification` |
| EC-DOC-24 | Very long CV with many skills listed but no context | Skills explicit-listed get lower confidence than skills used in roles/projects (rubric band 50 vs 75+) |
| EC-DOC-25 | Duplicate upload of same file | Deduplicate by sha256 per user; reuse extraction |
| EC-DOC-26 | Parser crash / timeout / OOM | Subprocess isolation; retry with fallback parser; then `processing_error` |
| EC-DOC-27 | Candidate corrects extraction | Correction stored; original retained; re-evaluation queued |
| EC-DOC-28 | Text-extractable but garbled encoding (CID fonts) | Quality low → OCR fallback |

## F. Screening & evaluation (EC-AI)
| EC-AI-01 | Exact keyword missing but equivalent skill present | Alias/relation/semantic match with method recorded |
| EC-AI-02 | Unconventional career path | Transferable evidence considered; band `review_needed` if coverage low |
| EC-AI-03 | CV vs answer conflict | `conflicting` + clarification suggestion |
| EC-AI-04 | Missing evidence for essential criterion | `not_assessable`; band `review_needed`; never automatic fail |
| EC-AI-05 | Knock-out answer unmet | `eligibility_review` band; human decides |
| EC-AI-06 | AI engine/model unavailable | Retry → fallback deterministic → manual review; application unaffected |
| EC-AI-07 | LLM returns malformed/uncited output | Schema validation fails → retry ×2 → deterministic template |
| EC-AI-08 | Re-run screening with same inputs | Same results (input_hash cache) |
| EC-AI-09 | Rubric changed after evaluations | New version on explicit re-evaluation only |
| EC-AI-10 | Duplicate queue message | processed_events dedupe; no duplicate evaluation |
| EC-AI-11 | Worker dies mid-evaluation | acks_late → redelivered; idempotent upsert by (application, version) |
| EC-AI-12 | Candidate objects to automated processing | AI evaluation hidden; manual review UI; band `manual_review_requested` |
| EC-AI-13 | Counterfactual: change name/gender/location in CV | Score identical (test) |
| EC-AI-14 | Very high scores for many (easy rubric) | Dashboard shows distribution; desired shortlist size guidance; no auto cut-off |
| EC-AI-15 | All candidates low coverage (bad rubric/CV quality) | Vacancy-level warning "Low evidence coverage — review rubric or request info" |
| EC-AI-16 | Expired certification | Flag `expired_or_unverified` → review; not fail |
| EC-AI-17 | Skills taxonomy updated | New taxonomy_version; old evaluations reference old version |

## G. Review, shortlist & decisions (EC-REV)
| EC-REV-01 | Recruiter attempts bulk not-selected | Requires confirmation, reason, shows count and uncertain/low-coverage subset separately |
| EC-REV-02 | Two approvers act concurrently | Row lock; second gets 409 `already_processed` |
| EC-REV-03 | Dual control: proposer tries to approve own shortlist | 403 `self_approval_forbidden` |
| EC-REV-04 | Approve then realise mistake | Undo within notification delay window; after that, reopen with reason (new events) |
| EC-REV-05 | Override AI band | Reason required; override analytics |
| EC-REV-06 | Blind mode enabled | Server-side redaction (not just CSS); reveal action logged |
| EC-REV-07 | Candidate withdraws after shortlist approved, before notification | Notification suppressed; entry marked withdrawn |
| EC-REV-08 | Shortlist larger than openings×N | Allowed; info only |
| EC-REV-09 | Hiring manager tries to see full pool | Only shortlist unless granted |
| EC-REV-10 | Panelist tries to view AI score | Hidden by default policy |
| EC-REV-11 | Recruiter reviews own relative (conflict of interest) | "Declare conflict" action reassigns; audit |

## H. Notifications & messaging (EC-NOT)
| EC-NOT-01 | Email bounce | Suppress address; in-app banner asks candidate to update email; staff sees delivery failure |
| EC-NOT-02 | Provider outage | Outbox retry with backoff up to 24 h; then dead letter + alert |
| EC-NOT-03 | Duplicate send risk on retry | dedupe_key unique |
| EC-NOT-04 | Notification to withdrawn/anonymised user | Suppressed |
| EC-NOT-05 | Template variable missing | Render fails safe (validation at template save + fallback to default template) |
| EC-NOT-06 | Candidate replies to no-reply email | Auto-response directing to portal messages |
| EC-NOT-07 | Clarification request past due | Status `expired`; recruiter decides; candidate can still message |
| EC-NOT-08 | Message attachment malicious | Scanned like uploads |
| EC-NOT-09 | Night-time sending | Non-urgent candidate emails sent 07:00–20:00 in candidate TZ (configurable) |

## I. Privacy & governance (EC-PRV)
| EC-PRV-01 | Deletion request while application under legal hold | Request recorded, hold explained, completed after release |
| EC-PRV-02 | Deletion request during active recruitment | Offer withdrawal + deletion; confirm |
| EC-PRV-03 | Access/export request | Export bundle (JSON + PDF summary + their documents) within SLA; download link 24 h |
| EC-PRV-04 | Correction disputes | Staff can reject with reason; candidate can add statement |
| EC-PRV-05 | Retention run deletes files but audit must remain | Audit retains ids + minimal data only; files deleted from S3 (versioned buckets: delete markers + lifecycle expiry) |
| EC-PRV-06 | Auditor views evaluation | PII redacted by default; reveal requires reason + log |
| EC-PRV-07 | Platform support needs to debug tenant data | Break-glass grant ≤ 4 h, reason, tenant-visible log |
| EC-PRV-08 | Export with formula injection payload in names | Escaped |
| EC-PRV-09 | Consent notice version changes | New applications get new version; old stay linked to old version |
| EC-PRV-10 | Backup contains deleted data | Backups expire per schedule (35 days); documented in privacy notice |

## J. Platform, operations & performance (EC-OPS)
| EC-OPS-01 | Redis down at submit time | Submission still commits (outbox in DB); relay resumes later |
| EC-OPS-02 | S3 unavailable | Upload sessions fail gracefully with retry message; submitted data unaffected |
| EC-OPS-03 | DB failover/restart | Connection retry; idempotency protects retries |
| EC-OPS-04 | Deploy during processing | Graceful worker shutdown (`SIGTERM` warm shutdown), acks_late redelivery |
| EC-OPS-05 | Migration on large table | Expand/contract; concurrent index creation |
| EC-OPS-06 | Clock drift between servers | NTP (chrony) enforced; server time authoritative |
| EC-OPS-07 | Dead-letter growth | Alert at > 10; admin UI retry |
| EC-OPS-08 | Disk full on EC2 | Monitoring alert at 80%; log rotation; docker prune in maintenance |
| EC-OPS-09 | ClamAV signature DB outdated | freshclam daily; alert if > 48 h old; scanning continues but flags |
| EC-OPS-10 | Traffic spike from viral job post | Cached public pages (ISR/revalidate 60 s), rate limits, CDN optional |

## K. Billing (v1.1) (EC-BIL)
| EC-BIL-01 | Paynow callback spoofed | Verify hash with integration key; poll status URL before marking paid |
| EC-BIL-02 | EcoCash payment pending for long | Poll with backoff up to 15 min; then `pending_manual_check` |
| EC-BIL-03 | Plan limit reached (active vacancies) | Block publish with upgrade prompt; never block candidate submissions to already-published jobs |
| EC-BIL-04 | Subscription lapses | Grace 7 days → read-only for staff; public jobs stay until deadline (protect candidates) |
| EC-BIL-05 | Currency changes (USD/ZWG) | Price snapshot on invoice |

## L. Interviews & offers (v1.1) (EC-INT / EC-OFF)
| EC-INT-01 | Panelist double-booked | Conflict warning |
| EC-INT-02 | Candidate in different TZ | Invitations show both TZs; ICS in UTC with TZID |
| EC-INT-03 | Candidate no-show | Mark no_show; reschedule option; no automatic rejection |
| EC-INT-04 | Panelist submits after seeing others | Scores hidden until own submission |
| EC-OFF-01 | Offer issued without approval | Blocked |
| EC-OFF-02 | Offer expires | Auto `expired`; HR notified |
| EC-OFF-03 | Two offers accepted for one opening | Openings counter warns; HR decides |
| EC-OFF-04 | Candidate accepts then withdraws | Status `withdrawn`; hire record not created/cancelled |
