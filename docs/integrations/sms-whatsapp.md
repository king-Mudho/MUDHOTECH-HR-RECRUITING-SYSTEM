# SMS and WhatsApp notifications (P15-T04, ADR-032)

## What candidates get

Only after they **opt in** (Settings → SMS and WhatsApp updates, which needs a mobile number), a
short message is sent for action-needed events: interview invitation, reminder, reschedule and
cancellation, clarification requests and job offers. Emails and in-app messages are unchanged.

- Consent is recorded per channel (`sms`, `whatsapp`) with the notice version and is re-checked at send
  time.
- Replying **STOP** (also STOPALL, UNSUBSCRIBE, QUIT, END, CANCEL, OPTOUT) withdraws that channel's
  consent immediately.
- Message texts are fixed templates (no free text, no outcomes such as "not selected"); WhatsApp uses
  pre-approved templates only.
- Every message sent is counted on the organisation's usage (`sms_messages`, `whatsapp_messages`).
- A provider failure marks that message failed; nothing else is affected.

## Organisation setup

Organisation admins connect **SMS (local aggregator)** and/or **WhatsApp Business (Cloud API)** in
Settings → Integrations, with the credentials from the provider. Without a connection, opted-in
candidates simply keep getting email and in-app messages.

## Platform setup (owner, decision D-14)

### SMS aggregator

The adapter speaks a small JSON protocol; point it at the chosen aggregator (or a thin proxy in front
of it):

| | |
|---|---|
| `SMS_AGGREGATOR_BASE_URL` | e.g. `https://sms.example.co.zw/api/v1` |
| Send | `POST {base}/messages` `{to, message, sender_id, reference, callback_url}` with `Authorization: Bearer <api key>` → `{id, status, cost}` |
| Balance (test button) | `GET {base}/balance` |
| Delivery receipts | aggregator → `POST /api/v1/integrations/sms/receipt/` `{id, status}` with header `X-MHRS-Webhook-Secret: <SMS_WEBHOOK_SECRET>` |
| Inbound (STOP) | aggregator → `POST /api/v1/integrations/sms/inbound/` `{from, text}` with the same header |

### WhatsApp Business Cloud API (Meta)

1. Meta Business Manager → WhatsApp → add a phone number; note the **phone number id** and create a
   permanent **access token** (system user).
2. Create and get approval for these templates (body parameters in this order, language `en`):
   `mhrs_interview_invitation` (organisation, job), `mhrs_interview_reminder` (job, when),
   `mhrs_interview_rescheduled` (organisation, job, when), `mhrs_interview_cancelled` (organisation,
   job), `mhrs_clarification_requested` (organisation, job, due date), `mhrs_offer_issued`
   (organisation, job, deadline).
3. Webhook: callback `https://<host>/api/v1/integrations/whatsapp/webhook/`, verify token =
   `WHATSAPP_VERIFY_TOKEN`; set `WHATSAPP_APP_SECRET` (signature check of every event); subscribe to
   `messages`.

Development and tests run in sandbox mode: messages are recorded, not sent.
