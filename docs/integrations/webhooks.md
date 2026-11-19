# Outbound webhooks (P15-T05)

Organisation admins add HTTPS endpoints in **Settings → Integrations → Webhooks** and choose events:

| Event | When |
|---|---|
| `application.submitted` | A candidate submitted an application |
| `application.status_changed` | An application moved to another status |
| `shortlist.approved` | A shortlist was approved |
| `offer.accepted` | A candidate accepted an offer |
| `job.published` | A vacancy was published |

## Request

```
POST <your URL>
Content-Type: application/json
User-Agent: MHRS-Webhooks/1.0
X-MHRS-Event: application.status_changed
X-MHRS-Delivery: 6f1c…            (unique per delivery; use it to de-duplicate)
X-MHRS-Signature: t=1763578800,v1=5d41402abc4b2a76b9719d911017c592…

{"created_at":"2026-11-19T18:00:00+00:00","data":{"application_id":"…","from":"under_review","to":"shortlisted"},"id":"…","organisation_id":"…","type":"application.status_changed"}
```

Payloads carry **identifiers and statuses only** – never names, emails, phone numbers, documents or AI
output. Fetch details through the [public API](public-api.md) with your own key if you need them.

## Verify the signature

`v1` is the hex HMAC-SHA256 of `"<t>.<raw body>"` with your endpoint secret (`whsec_…`, shown once
when the endpoint is created; rotate it any time). Reject requests older than 5 minutes.

Python:

```python
import hashlib, hmac, time

def verify(secret: str, raw_body: bytes, header: str, tolerance: int = 300) -> bool:
    parts = dict(p.split("=", 1) for p in header.split(","))
    ts = int(parts["t"])
    if abs(time.time() - ts) > tolerance:
        return False
    expected = hmac.new(secret.encode(), f"{ts}.".encode() + raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, parts.get("v1", ""))
```

Node.js:

```js
const crypto = require("crypto");

function verify(secret, rawBody, header, tolerance = 300) {
  const parts = Object.fromEntries(header.split(",").map((p) => p.split("=")));
  const ts = Number(parts.t);
  if (Math.abs(Date.now() / 1000 - ts) > tolerance) return false;
  const expected = crypto.createHmac("sha256", secret).update(`${ts}.`).update(rawBody).digest("hex");
  return crypto.timingSafeEqual(Buffer.from(expected), Buffer.from(parts.v1 || ""));
}
```

Always verify against the **raw** request body (before JSON parsing).

## Delivery, retries and replay

- Answer with any 2xx within 10 seconds. Anything else is retried after 1 min, 5 min, 30 min, 2 h, 6 h
  and 12 h; after that the delivery is marked failed.
- The delivery log (last 50) shows status, attempts and the last error; **Replay** sends a delivery
  again.
- Each event is delivered once per endpoint; retries reuse the same `X-MHRS-Delivery` id.
- Only `https://` URLs on public addresses are accepted (private, loopback and link-local addresses are
  refused when the endpoint is added and again at send time).
- A failing receiver never affects MHRS records: deliveries run after the change is saved, on their
  own queue.
