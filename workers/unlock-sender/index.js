/**
 * Cloudflare Worker — Stripe webhook handler that emails an unlock token.
 *
 * Privacy-minimal: the unlock token contains only the Stripe session id +
 * expiry — no customer email is ever embedded in the token URL. We hold no
 * persistent storage; the customer's email passes through memory only
 * long enough to make a single Resend API call, then is forgotten.
 *
 * Required env vars (set via `wrangler secret put` or the dashboard):
 *   STRIPE_WEBHOOK_SECRET   — from Stripe Dashboard → Webhooks → your endpoint
 *   STRIPE_UNLOCK_SECRET    — must match src/unlock.py on the Streamlit side
 *   RESEND_API_KEY          — from resend.com → API keys
 *   UNLOCK_BASE_URL         — e.g. "https://wcpicks26.app"
 *   FROM_ADDRESS            — e.g. "WC26 Picks <unlock@wcpicks26.app>"
 *   TTL_DAYS                — optional, defaults to 90
 */

const enc = new TextEncoder();
const dec = new TextDecoder();

function b64url(bytes) {
  let s = btoa(String.fromCharCode(...new Uint8Array(bytes)));
  return s.replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
}

async function hmacSha256(secret, message) {
  const key = await crypto.subtle.importKey(
    "raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]
  );
  return new Uint8Array(await crypto.subtle.sign("HMAC", key, enc.encode(message)));
}

async function signUnlockToken(sessionId, ttlDays, secret, tier = "wc26-full") {
  const payload = JSON.stringify(
    { exp: Math.floor(Date.now() / 1000) + ttlDays * 86400, sid: sessionId, tier },
  );
  // Match Python: keys sorted, no whitespace. JS JSON.stringify isn't sorted
  // by default, so do it explicitly:
  const sorted = { exp: undefined, sid: undefined, tier: undefined };
  const parsed = JSON.parse(payload);
  sorted.exp = parsed.exp; sorted.sid = parsed.sid; sorted.tier = parsed.tier;
  const canonical = JSON.stringify(sorted);
  const payloadBytes = enc.encode(canonical);
  const sigBytes = await hmacSha256(secret, canonical);
  return `${b64url(payloadBytes)}.${b64url(sigBytes)}`;
}

/**
 * Verify Stripe webhook signature.
 * Stripe-Signature header format: `t=<timestamp>,v1=<sig>,v1=<sig>,...`
 * Signed payload is `<timestamp>.<rawBody>`.
 */
async function verifyStripeSignature(rawBody, sigHeader, secret) {
  if (!sigHeader) return false;
  const parts = Object.fromEntries(
    sigHeader.split(",").map(p => {
      const i = p.indexOf("=");
      return [p.slice(0, i), p.slice(i + 1)];
    })
  );
  const ts = parts["t"];
  // Multiple v1 entries possible — split header again to collect them all
  const v1s = sigHeader.split(",")
    .filter(p => p.startsWith("v1="))
    .map(p => p.slice(3));
  if (!ts || v1s.length === 0) return false;
  // Reject very stale events (>5 min) to prevent replay
  const ageSec = Math.floor(Date.now() / 1000) - parseInt(ts, 10);
  if (ageSec > 300 || ageSec < -60) return false;
  const signedPayload = `${ts}.${rawBody}`;
  const expectedSig = await hmacSha256(secret, signedPayload);
  const expectedHex = Array.from(expectedSig)
    .map(b => b.toString(16).padStart(2, "0")).join("");
  // Constant-time compare against each v1 signature
  return v1s.some(v => safeEq(v, expectedHex));
}

function safeEq(a, b) {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

function htmlEmail(unlockUrl) {
  return `<!doctype html>
<html><body style="font-family: system-ui, -apple-system, sans-serif; background:#11151c; color:#f1f5f9; padding:32px;">
  <div style="max-width:560px; margin:0 auto; background:#1a2030; border-radius:16px; padding:32px; border:1px solid rgba(37,99,235,0.25);">
    <h1 style="margin:0 0 16px; font-size:26px; color:#3b82f6;">Your WC26 Picks unlock</h1>
    <p style="font-size:16px; line-height:1.6;">
      Thanks for buying. The button below opens the full tournament: every fixture
      with its predicted score, the knockout bracket through to the Final, and the
      simulator that gives each team's chances of winning the cup.
    </p>
    <p style="margin:32px 0;">
      <a href="${unlockUrl}" style="display:inline-block; background:linear-gradient(135deg,#2563eb,#1d4ed8); color:#fff; text-decoration:none; padding:14px 28px; border-radius:10px; font-weight:700;">
        Open WC26 Picks
      </a>
    </p>
    <p style="font-size:13px; color:#94a3b8; line-height:1.6;">
      Keep this email. The link is your access pass and works through the end of
      the tournament. If you lose it, email <a href="mailto:support@wcpicks26.app" style="color:#60a5fa;">support@wcpicks26.app</a> and we'll resend it.
    </p>
    <hr style="border:none; border-top:1px solid rgba(255,255,255,0.08); margin:24px 0;">
    <p style="font-size:12px; color:#64748b; line-height:1.5;">
      WC26 Picks is a statistical forecasting tool, not betting advice. For a
      refund before kickoff, email <a href="mailto:support@wcpicks26.app" style="color:#94a3b8;">support@wcpicks26.app</a>.
    </p>
  </div>
</body></html>`;
}

async function sendUnlockEmail(env, toEmail, unlockUrl) {
  const r = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${env.RESEND_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      from: env.FROM_ADDRESS,
      to: toEmail,
      subject: "Your WC26 Picks unlock is ready",
      html: htmlEmail(unlockUrl),
      reply_to: "support@wcpicks26.app",
    }),
  });
  if (!r.ok) {
    const errText = await r.text();
    // Log the *status* only — not the customer email
    console.error(`Resend ${r.status}: ${errText.slice(0, 200)}`);
    throw new Error(`Resend send failed: ${r.status}`);
  }
}

export default {
  async fetch(request, env) {
    if (request.method === "GET") {
      return new Response("WC26 Picks webhook OK", { status: 200 });
    }
    if (request.method !== "POST") {
      return new Response("Method not allowed", { status: 405 });
    }

    const rawBody = await request.text();
    const sigHeader = request.headers.get("stripe-signature") || "";

    const valid = await verifyStripeSignature(rawBody, sigHeader, env.STRIPE_WEBHOOK_SECRET);
    if (!valid) {
      return new Response("Bad signature", { status: 400 });
    }

    let event;
    try { event = JSON.parse(rawBody); } catch { return new Response("Bad JSON", { status: 400 }); }
    if (event.type !== "checkout.session.completed") {
      // Acknowledge other event types so Stripe doesn't retry
      return new Response("Ignored", { status: 200 });
    }

    const session = event.data?.object;
    const sessionId = session?.id;
    const customerEmail = session?.customer_details?.email || session?.customer_email;
    if (!sessionId || !customerEmail) {
      return new Response("Missing session id or customer email", { status: 400 });
    }

    const ttlDays = parseInt(env.TTL_DAYS || "90", 10);
    const token = await signUnlockToken(sessionId, ttlDays, env.STRIPE_UNLOCK_SECRET);
    const unlockUrl = `${env.UNLOCK_BASE_URL}/?token=${token}`;

    try {
      await sendUnlockEmail(env, customerEmail, unlockUrl);
    } catch (e) {
      // 500 makes Stripe retry; if Resend is down we want the retry
      return new Response("Send failed", { status: 500 });
    }

    return new Response("OK", { status: 200 });
  },
};
