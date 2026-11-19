# Organisation admin guide

Setting up your organisation, managing your team, privacy requests and security.

## 1. Set up the organisation
1. **For employers → Create organisation.** Enter the legal name, registration number, city and
   website. MudhoTech verifies new organisations before they can publish vacancies.
2. **Settings → Organisation:** logo, description and public company page.
3. Add **departments** and **locations** used in vacancies.

## 2. Team and roles
**Settings → Team** — invite colleagues by email and choose a role:

| Role | Can |
|---|---|
| Org admin | Everything below, plus team, policy, privacy requests, legal holds |
| HR manager | Approve vacancies and shortlists, decide outcomes, see all vacancies |
| Recruiter | Create vacancies, review applications on assigned vacancies, propose shortlists |
| Hiring manager | See shortlisted applications of their vacancies (or the full pool if granted) |
| Interview panelist | Interview tasks and scorecards only (AI hidden by default) |
| Auditor | Read-only audit trail and reconstructions |

Privileged roles must use two-factor authentication. Remove access when someone leaves; their past
decisions stay attributed to them.

## 3. Organisation policy
**Settings → Organisation policy:** blind review default, notification delay (undo window), dual
control for shortlists and rubrics, duplicate-application rule, upload limits, AI screening on/off,
external language model (off by default), retention period (default 12 months after a vacancy
closes), and your candidate privacy notice. Changing the notice creates a new version; candidates'
consent records keep the exact wording they accepted.

## 4. Privacy requests and legal holds
**Settings → Privacy** shows data requests from candidates who applied to you, with due dates (30
days by default, reminders before).
- **Start**, then **Complete** with an outcome the candidate will see, or **Decline with reason**.
- Completing a **deletion** removes the candidate's data from your organisation's records and
  files, unless a **legal hold** applies — then the request waits *On hold* and the candidate is told
  why. Release the hold when the matter ends.
- **Exports** are prepared automatically after the candidate confirms by email.

The daily retention run anonymises applications after your retention period; you get a weekly
preview of what is due.

## 5. Support access
If you ask MudhoTech support for help, a support engineer may request temporary **read-only** access.
A second MudhoTech admin must approve it, it lasts at most 4 hours, every page they open is logged,
and your staff see a banner while it is active. **Settings → Privacy** lists every grant; you can
revoke one at any time.

## 6. Leaving the platform
Ask MudhoTech to close your organisation. Vacancies close, your staff become read-only, candidates
with open applications are told, and data is anonymised when your retention period ends.

## 7. Plan and billing (v1.1)

**Settings → Plan & billing** shows your plan, trial end, usage against limits, invoices (PDF) and
**Pay now** (EcoCash, OneMoney or card through Paynow; bank transfer also accepted). Choosing a plan
creates an invoice and the plan starts when it is paid. If an invoice stays unpaid, there is a 7-day
grace period, after which your team can view but not change data until payment; published vacancies
stay open to candidates throughout.

## 8. Integrations (v1.2)

**Settings → Integrations**: staff connect their own Google or Microsoft calendar; you can connect
SMS and WhatsApp for candidate updates, add signed **webhooks** for your own systems and create
**API keys** (read-only scopes). **Settings → Policies → Single sign-on** lets members sign in with
Google or Microsoft for the email domains you list. See `docs/integrations/` for details.
