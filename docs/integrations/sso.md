# Staff single sign-on – Google and Microsoft (P15-T03)

- An organisation admin enables SSO in **Settings → Policies → Single sign-on** and lists the
  organisation's email domains (e.g. `acme.co.zw`).
- A staff member who is an **active member** of that organisation and whose email (verified by Google
  or Microsoft) is on one of those domains can then use "Continue with Google/Microsoft" on the sign-in
  page.
- SSO never creates accounts: new staff still join by invitation (and can use SSO afterwards).
  Candidates sign in with email and password.
- MHRS's MFA policy still applies: privileged roles must also complete MHRS two-factor authentication.

## Owner setup

Uses the same OAuth apps as [calendar sync](calendar.md) (scopes `openid email profile`). Set
`GOOGLE_OAUTH_CLIENT_ID/SECRET`, `MICROSOFT_OAUTH_CLIENT_ID/SECRET` (and `MICROSOFT_OAUTH_TENANT`,
default `organizations`), and build the frontend with `NEXT_PUBLIC_SSO_ENABLED=true` so the sign-in
page shows the buttons. Providers without client ids are simply not offered.
