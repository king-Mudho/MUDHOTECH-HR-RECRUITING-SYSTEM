# What MHRS needs from the owner

MUDHOTECH HR RECRUITING SYSTEM v1.2.0 is live at https://hr.agribizframework.com. Everything that
could be done without the owner is done. This list is what is left, in order of priority, with the
exact steps. Updated 20 November 2026.

**Never send passwords, keys or tokens in chat or email.** Every item below that needs a secret
either prompts for it on the server or tells you exactly where to put it.

Commands are for **Git Bash** on your computer unless they say otherwise.

---

## Priority 1 — this week

### 1. Turn on two-factor authentication for the admin account (deadline 27 November 2026)

After 7 days the platform admin account cannot be used without it.

1. Install an authenticator app on your phone (Google Authenticator, Microsoft Authenticator or
   similar).
2. Sign in at https://hr.agribizframework.com/login as mudhotechsolutions@gmail.com.
3. Click the shield icon (**Account security**) at the top, choose **Set up two-factor
   authentication**, scan the QR code and type the 6-digit code.
4. Save the **recovery codes** it shows somewhere safe (a password manager), not on the server.

### 2. Switch on off-server backups (about 10 minutes)

Backups currently live only on the server; if the server is lost, so are they. This copies each
night's backup to Google Drive, encrypted before it leaves the server (Google only ever sees
scrambled data).

**Step 1.** Run, from your computer:

```bash
ssh -t -L 53682:127.0.0.1:53682 agribizframework "bash /srv/mhrs/infrastructure/vps/configure-offsite-backup.sh"
```

**Step 2.** Open the link it prints in your browser, choose the Google account that should hold the
backups and allow access. (Google may say rclone is "not verified": it is the standard open-source
tool; continue.)

**Step 3.** It uploads a backup, downloads it back and checks it restores. Wait for **"Off-server
backups are on."**

**Step 4.** Store the encryption key off the server. Show it:

```bash
ssh agribizframework "cat /etc/mhrs/offsite-backup-key.txt"
```

Copy the two passwords into your password manager, then delete the plain copy:

```bash
ssh agribizframework "rm /etc/mhrs/offsite-backup-key.txt"
```

Without that key nobody, including you, can read the Drive copies.

### 3. Apply the server's pending security updates (maintenance window, about 30 minutes)

The server has **88 pending operating-system security updates** and has not been restarted for
about four weeks, so kernel fixes are not active. All five sites on the server (agribizframework,
research, ama, mudhotech.com, hr) go offline for a few minutes during the restart, so choose a quiet
time and tell the other sites' users.

```bash
ssh agribizframework "dnf upgrade --security -y && reboot"
```

Wait about 3 minutes, then check every site answers:

```bash
for s in agribizframework.com research.agribizframework.com ama.agribizframework.com mudhotech.com hr.agribizframework.com; do curl -s -o /dev/null -w "%{http_code} $s\n" https://$s/; done
```

All should show `200`. MHRS starts by itself after a reboot; its monitor will email you if anything
does not come back.

Recommended afterwards (decide for the whole server): turn on automatic security updates,
`ssh agribizframework "dnf install -y dnf-automatic && sed -i 's/^upgrade_type.*/upgrade_type = security/; s/^apply_updates.*/apply_updates = yes/' /etc/dnf/automatic.conf && systemctl enable --now dnf-automatic.timer"`.
Kernel updates still need a planned restart.

### 4. Free disk space on the shared server (77 % full)

The server disk is **77 % full** (86 GB of 118 GB). MHRS uses 3.3 GB; **the Research Portal
(`/srv/agribiz-drp`) uses 71 GB**, most likely its backups or uploaded files. MHRS's monitor emails
you at 80 %. Check the DRP folder and its backup retention:

```bash
ssh agribizframework "du -sh /srv/agribiz-drp/* | sort -h | tail"
```

Delete or move only what that project no longer needs (old backups are the usual cause), or add
disk space with the hosting provider.

### 5. Restart Docker Desktop on your computer (developer machine)

Docker Desktop on this computer stopped responding on 21 November (commands time out), which also
affects your other local projects that use it. Restart it from its tray icon when convenient. The
live server does not use Docker and is not affected.

### 6. Sign off the go-live checklist (closes Phase 11)

1. Read the section **"Production on the shared VPS"** at the top of
   `docs/deployment/GO_LIVE_CHECKLIST.md`. Items 1 and 2 above are its two open lines.
2. When you accept it, tell me **"go-live signed"** (with any exceptions you accept). I record your
   sign-off in `PROGRESS.md` and close Phase 11.

---

## Priority 2 — before real candidates use the system

### 7. Legal and data protection (decision D-08)

Under the Cyber and Data Protection Act [Chapter 12:07] and SI 155 of 2024:

- Have counsel review the **platform privacy notice** (site footer, *Privacy*), the **terms**, and
  the employer privacy notice template (each employer can edit theirs in *Settings → Organisation
  policy*).
- Confirm MudhoTech's **registration/licensing with POTRAZ** as a data controller/processor, as
  counsel advises.
- Review the data protection impact assessment in `docs/dpia/` and the AI model card in
  `docs/ai-governance/`, and record approval.
- Confirm the breach-notification contacts and timelines in `docs/runbooks/incident-data-leak.md`.

Tell me the outcome; I update decision D-08 and the documents.

### 8. Set up the first real employer

1. A real employer creates its organisation (*For employers → Create organisation*), or you create
   one for them.
2. As platform admin, open **Admin → Organisations** and **verify** it (it cannot publish until
   verified).
3. The employer's admin invites their HR team (*Settings → Team*); each privileged user sets up
   two-factor authentication.
4. HR creates, approves and publishes a vacancy; it appears on the job board.
5. Do one real test yourself: register as a candidate with a second email address, apply with a
   sample CV, and confirm the confirmation emails arrive and the application is screened.

### 9. A business mailbox for system email (recommended)

Today's sender is the Gmail account mudhotechsolutions@gmail.com, limited to about **500 emails a
day** and more likely to land in spam at volume. Before many candidates apply:

1. Create a mailbox on your own domain, e.g. `no-reply@mudhotech.co.zw` (Google Workspace, Zoho,
   or your host's mail), with SMTP access (an app password if it uses two-step sign-in).
2. Ask whoever manages the domain's DNS to add the mail provider's **SPF**, **DKIM** and **DMARC**
   records.
3. Run `ssh -t agribizframework "bash /srv/mhrs/infrastructure/vps/configure-email.sh"` with the new
   mailbox. It sends a test email at the end.

---

## Priority 3 — to switch features from test mode to live

These all work today in **test mode** (nothing is sent to the real provider). Each goes live when
its account exists. Values go into `/srv/mhrs/backend/.env` on the server; to edit it:

```bash
ssh -t agribizframework "nano /srv/mhrs/backend/.env"
```

then restart with `ssh agribizframework "systemctl restart mhrs-backend mhrs-worker mhrs-beat"`.
When the provider accounts are in, tell me and I set `INTEGRATIONS_SANDBOX=false` and test each one.

### 10. Payments and billing (Paynow)

- **From Paynow:** a merchant account with an integration for **USD** and one for **ZWG**
  (integration ID and integration key for each).
- **Put on the server:** `PAYNOW_USD_INTEGRATION_ID`, `PAYNOW_USD_INTEGRATION_KEY`,
  `PAYNOW_ZWG_INTEGRATION_ID`, `PAYNOW_ZWG_INTEGRATION_KEY`. (`PAYNOW_RESULT_URL_BASE` is already
  set to `https://hr.agribizframework.com`.)
- **Invoice details:** `BILLING_SELLER_NAME`, `BILLING_SELLER_ADDRESS`, `BILLING_SELLER_EMAIL`,
  `BILLING_SELLER_TAX_NUMBER` (BP/VAT number), `BILLING_TAX_RATE` (e.g. `15.5`), `BILLING_TAX_LABEL`
  (e.g. `VAT`).
- **Decide:** the plan prices and limits (*Admin → Plans & pricing*), and when to start charging.
  Billing is **not enforced** now (`BILLING_ENFORCE=false`); tell me the date and I switch it on.
  Existing pilot organisations need a plan assigned first, or their 30-day trial starts.

### 11. Calendars and staff sign-in (Google and Microsoft)

- **Google:** in Google Cloud Console create an OAuth client (web application) with redirect URI
  `https://hr.agribizframework.com/api/v1/auth/browser/v1/auth/provider/callback/google` and the
  Calendar API enabled. Put `GOOGLE_OAUTH_CLIENT_ID` and `GOOGLE_OAUTH_CLIENT_SECRET` on the server.
- **Microsoft:** in Microsoft Entra (Azure) register an app with redirect URI
  `https://hr.agribizframework.com/api/v1/auth/browser/v1/auth/provider/callback/microsoft` and
  Calendars.ReadWrite permission. Put `MICROSOFT_OAUTH_CLIENT_ID`, `MICROSOFT_OAUTH_CLIENT_SECRET`
  and `MICROSOFT_OAUTH_TENANT` (`common` for any organisation) on the server.
- Tell me when done: the sign-in buttons need a frontend rebuild with SSO switched on.
- Details: `docs/integrations/calendar.md`, `docs/integrations/sso.md`.

### 12. SMS and WhatsApp updates for candidates (decision D-14)

- **SMS:** choose a Zimbabwean SMS aggregator (decision D-14) that offers an HTTP API, delivery
  receipts and inbound STOP replies. Each employer then enters the API key and sender ID in
  *Settings → Integrations*. Platform values: `SMS_AGGREGATOR_BASE_URL`, `SMS_WEBHOOK_SECRET`.
- **WhatsApp:** a Meta Business account with the WhatsApp Cloud API, a phone number, and approved
  message templates (the wording is in `docs/integrations/sms-whatsapp.md`). Employers enter the
  access token and phone number ID in *Settings → Integrations*. Platform values:
  `WHATSAPP_APP_SECRET`, `WHATSAPP_VERIFY_TOKEN`.

### 13. Faster server with full AI matching (hosting provider)

The server's virtual processor does not offer **AVX2** instructions, so meaning-based skill matching
is switched off (matching uses the skills list and aliases; unmatched skills go to a person).
**Ask the hosting provider** to enable *CPU host-passthrough* (or move the VPS to a plan whose CPU
exposes AVX2). After that, tell me and I switch semantic matching back on and compute the skill
vectors.

### 14. Error tracking (optional)

Create a free **Sentry** project and put its DSN in `SENTRY_DSN` on the server. Errors then arrive
with the release that caused them.

### 15. Translations

Have a human translator review the chiShona and isiNdebele texts (`frontend/messages/sn.json`,
`nd.json` and the email templates). Until then they are labelled as drafts.

---

## Priority 4 — closing the project

- **Phase 16 sign-off:** after the next fully green nightly test run (I check it), tell me
  **"Phase 16 signed"** to close the project (milestones M2 and M5).
- **External penetration test (yearly):** brief a tester with `docs/security/PENTEST_READINESS.md`.
  Test against production only with the tester's agreement and a fresh backup, or ask me to set up a
  test copy first.
- **Yearly reviews:** data protection impact assessment, AI model card, and access review of who has
  platform admin rights and server keys.

---

## Already done — no action needed

| Item | Status |
|---|---|
| Live site, HTTPS certificate (auto-renew), DNS | Done |
| Separation from the four other sites on the server | Done, verified |
| Secrets generated on the server, nothing default | Done |
| Platform admin account | Done |
| Outgoing email (Gmail) | Done, tested |
| Nightly backups and a passed restore drill | Done |
| Monitoring with email alerts (tested) | Done |
| Releases through GitHub with your approval; restricted deploy key | Done, v1.2.0 released |
| Security review of the code and the live site (ZAP passive scan) | Done |
| Full test suite (3,067 backend, 196 frontend, browser journeys) | Done |
| Documentation: system guide, user guides, runbooks, handover | Done |

## Who to tell what

| When you have done | Tell me |
|---|---|
| Items 1 to 4 | "priority 1 done" (I verify the backups, updates, disk and sites) |
| The go-live checklist | "go-live signed" plus any exceptions |
| Legal review | the outcome for D-08 |
| Provider accounts in place | which ones, so I switch them live and test them |
| Hosting CPU change | "AVX2 enabled", so I switch on semantic matching |
