# Calendar sync – Google Calendar and Microsoft 365 (P15-T02)

Each staff member can connect **their own** calendar in **Settings → Integrations**. MHRS then:

- creates an event in each connected panelist's calendar when an interview gets a time (scheduled
  directly or booked by the candidate), updates it when it is rescheduled and deletes it when it is
  cancelled;
- reads free/busy for the panel when an interview is scheduled and adds any clash to the conflict
  warning (a warning only – it never blocks scheduling, EC-INT-01).

Events contain the vacancy, stage, time, mode/location, the application reference and a link to the
interview page – no candidate contact details. A calendar that fails (expired token, provider outage)
is marked **Failing** on the integrations page; the interview itself is never affected.

## Owner setup (production)

1. **Google**: Google Cloud console → APIs & Services → enable *Google Calendar API* → OAuth consent
   screen (internal or external) → Credentials → *OAuth client ID* (web application). Authorised
   redirect URI: `https://<host>/api/v1/auth/browser/v1/auth/provider/callback/google` (shared with
   SSO). Scopes: `openid email profile https://www.googleapis.com/auth/calendar.events
   https://www.googleapis.com/auth/calendar.freebusy`.
2. **Microsoft**: Entra ID → App registrations → new registration → redirect URI
   `https://<host>/api/v1/auth/browser/v1/auth/provider/callback/microsoft` → API permissions
   (delegated): `Calendars.ReadWrite`, `offline_access`, `openid`, `email`, `profile`.
3. Set `GOOGLE_OAUTH_CLIENT_ID/SECRET` and `MICROSOFT_OAUTH_CLIENT_ID/SECRET/TENANT` in the
   environment and `INTEGRATIONS_SANDBOX=false`.

Until then (and always in development and tests) integrations run in **sandbox mode**: nothing leaves
the server and replies are simulated, so the whole flow can be tried safely.

> Follow-up: the in-app "Connect with Google/Microsoft" OAuth consent screen (storing the refresh
> token automatically) needs the OAuth apps above; until they exist, a refresh token can be pasted in
> sandbox mode for testing.
