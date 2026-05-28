# Unlock-sender Worker

Receives Stripe `checkout.session.completed` webhooks, signs an HMAC unlock
token (no PII in the token), emails the unlock URL via Resend.

## Deploy via Cloudflare dashboard (no CLI needed)

1. Cloudflare → **Workers & Pages → Create application → Create Worker**
2. Name it `wc26-unlock-sender`
3. After the default "Hello World" deploys → **Edit code** → replace everything with the contents of `index.js`
4. **Save and deploy**

## Set environment variables

Worker → **Settings → Variables and Secrets → + Add variable**. All as
**Secret** type (encrypted), not plaintext:

| Name | Value |
|---|---|
| `STRIPE_WEBHOOK_SECRET` | From Stripe → Developers → Webhooks → your endpoint → "Signing secret" (`whsec_...`) |
| `STRIPE_UNLOCK_SECRET` | The 32-char string from your local `secrets.txt`. **MUST match** the value in Streamlit Cloud secrets |
| `RESEND_API_KEY` | From Resend → API Keys (`re_...`) |
| `UNLOCK_BASE_URL` | `https://wcpicks26.app` (no trailing slash) |
| `FROM_ADDRESS` | `WC26 Picks <unlock@wcpicks26.app>` |
| `TTL_DAYS` | `90` (optional — defaults to 90 if not set) |

## Set the custom domain

Worker → **Settings → Triggers → Custom Domains → + Add Custom Domain**
→ `webhook.wcpicks26.app` → save. Cloudflare auto-adds the DNS record.

## Connect to Stripe

In Stripe (Test mode first):

1. Developers → Webhooks → **+ Add endpoint**
2. Endpoint URL: `https://webhook.wcpicks26.app/`
3. Events: only `checkout.session.completed`
4. Save → copy the Signing secret → paste into the Worker's `STRIPE_WEBHOOK_SECRET` env var

## Test it

After deploy, hit `https://webhook.wcpicks26.app/` with a GET request
(your browser). You should see `WC26 Picks webhook OK`.

For an end-to-end test:
1. Stripe dashboard → Developers → Webhooks → your endpoint → **Send test webhook** → pick `checkout.session.completed`
2. Stripe sends a synthetic event; the Worker should return 200 OK
3. Note: synthetic events have a fake `customer_email` (e.g. `someone@example.com`) — Resend will accept the send but may bounce. The real test is doing a real purchase with test card `4242 4242 4242 4242` via your Payment Link.

## Privacy posture

- The unlock token payload is `{sid, exp, tier}` — no customer email.
- Customer email passes through worker memory only long enough to call Resend.
- No persistent storage. No DB. No logs of the email (only Resend status codes are logged).
- Replay protection: events older than 5 min are rejected.
