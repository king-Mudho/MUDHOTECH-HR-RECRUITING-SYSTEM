# Runbook — email deliverability (SES bounces, complaints, failures)

P11-T08. Code: `apps/notifications/` (delivery via outbox, `EmailSuppression`), SNS webhook
`/api/v1/webhooks/ses/` (P05-T04). Alarms: `mhrs-<env>-email-failures` (> 5 %/h), `-ses-bounces` (> 4 %),
`-ses-complaints` (> 0.08 %). SES pauses sending for the whole account at about 10 % bounces or 0.5 % complaints.

## Symptoms
Candidates say they get no emails (receipts, verification, outcomes); the email-failure alarm; SES console shows
reputation warnings or *sending paused*.

## Impact
Every message is also in the candidate's in-app notifications and application timeline, so nothing is lost —
but email verification and password resets depend on email.

## Immediate actions
1. **SES paused:** stop non-essential sending (bulk outcome notifications can wait — they are queued in the outbox),
   open an AWS support case with the cause and fix; essential mail (verification, reset) resumes when SES lifts it.
2. **Failures, not bounces** (`Notification.status=failed`, `last_error`): credentials or connectivity —
   `$DC exec backend python manage.py send_test_email --to <your address>`; check `EMAIL_URL` in SSM and SES SMTP
   credentials (rotated? IAM user deleted?).

## Diagnosis
| Check | Where |
|---|---|
| Recent failures | `/django-admin/notifications/notification/?status__exact=failed` (`last_error`) |
| Suppressed addresses | `/django-admin/notifications/emailsuppression/` (hard bounces, complaints) |
| Webhook receiving feedback? | app logs for `webhooks/ses`; SNS subscription *Confirmed*; `SES_SNS_TOPIC_ARNS` set (empty = every message refused) |
| Domain auth | SES identity: DKIM *verified*; SPF/DMARC records present (AWS_SETUP §5) |
| Reputation | SES → Reputation metrics; which configuration set / template caused it |

## Resolution
- **Hard bounce for a real candidate** (typo in address): the candidate updates the email in their account (the
  app shows an "update your email" banner when delivery failed, EC-NOT-01); then remove the suppression row in admin.
- **Complaints:** check the message that triggered them — unexpected bulk mail? Wrong template? Complaints are
  never removed from suppression without the person asking.
- **DNS/DKIM broken:** fix records at the DNS provider; SES re-verifies automatically.

## Verification
`send_test_email --to ...` arrives (check spam folder and headers: `dkim=pass`, `spf=pass`); `EmailFailureRatePercent` back
under 5; SES reputation metrics trending down.

## Follow-up
If sending was paused: incident record and the SES case reply. The no-reply mailbox receipt rule (docs/10 §6) must
never answer auto-replies (mail loops raise complaint rates).
