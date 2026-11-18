# Runbook — compromised credentials or secrets

P11-T08. Covers a user account, an administrator account, an application secret (`SECRET_KEY`, database
password, SES SMTP credentials, GHCR token, Sentry DSN) and AWS access. If personal data may have been read,
run `incident-data-leak.md` in parallel.

`DC="docker compose -f /opt/mhrs/docker-compose.prod.yml --env-file /opt/mhrs/.env"`

## Symptoms
New-device sign-in emails the user did not expect (EC-ACC-11), lockouts, unknown sessions in *Account →
Sessions*, a secret committed or pasted somewhere, AWS GuardDuty/CloudTrail findings, unexpected SES sending.

## A. One user account (candidate or staff)
1. Revoke every session of the user (they must sign in again; audited):
   ```bash
   $DC exec backend python manage.py shell -c "from apps.accounts.models import User; from apps.accounts.sessions import revoke_all_sessions; print(revoke_all_sessions(User.objects.get(email='<email>')))"
   ```
2. Ask the user to reset their password (*Forgot password*); a reset also clears lockouts. For staff with MFA,
   an organisation admin resets it (HR → Team → member → *Reset MFA*; audited, reason required) once the person's
   identity is confirmed out of band.
3. Staff account: review what it did — HR → Audit (filter by actor), especially exports, shortlist decisions and
   identity reveals; suspend the membership if needed (HR → Team).

## B. Platform administrator account
As A, plus: list support-access grants and revoke any not expected
(*Platform admin → Support access*, `/admin/support-access`); review platform audit events;
check `PLATFORM_ADMIN_*` were never left in SSM after bootstrap.

## C. Application secrets (rotate, then redeploy)
Each secret lives in SSM `/mhrs/<env>/…`; `deploy.sh <current tag>` re-renders `.env` and restarts everything.

| Secret | Rotate | Side effects |
|---|---|---|
| `SECRET_KEY` | new value: `python -c "import secrets;print(secrets.token_urlsafe(64))"` | all sessions and password-reset links become invalid (everyone signs in again) — intended |
| `DATABASE_URL` password | `ALTER ROLE mhrs_app PASSWORD '<new>'` (as `mhrs_admin`), then SSM | brief errors until the redeploy finishes |
| `EMAIL_URL` (SES SMTP) | create new SMTP credentials, update SSM, redeploy, **delete the old IAM SMTP user** | none |
| `GHCR_READ_TOKEN` | revoke on GitHub, create a new read-only token, SSM | none (used at deploy only) |
| `SENTRY_DSN` | rotate the client key in Sentry | none |
| `FIELD_ENCRYPTION_KEYS` | `rotate-keys.md` (never just replace it — old data would be unreadable) | none if done as described |
| GitHub deploy SSH key | new key pair; update `~mhrs/.ssh/authorized_keys` and the environment secret; remove the old key | none |

## D. AWS credentials
Deactivate the access key in IAM immediately, check CloudTrail for its activity (all regions), rotate it, and
review IAM users/roles created recently. The instance role has no long-lived keys; if the instance itself is
suspected, snapshot its volume for analysis and rebuild from `ec2-bootstrap.sh`.

## Verification
The compromised credential no longer works (try it); `deploy.sh` smoke tests pass after rotation; no new
unexpected activity in the audit log / CloudTrail for 24 h.

## Follow-up
Incident record; how was it exposed? (secret scanning — `detect-secrets` runs in CI — leaked laptop, phishing);
enforce MFA where missing.
