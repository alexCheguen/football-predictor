"""HMAC-signed unlock tokens for the paid-tier paywall.

Privacy-minimal design: tokens contain only `sid` (Stripe session id),
`exp` (Unix expiry timestamp), and `tier` ("wc26-full"). No email or
other PII is ever encoded into the token, so the URL itself reveals
nothing about the buyer.

The same `STRIPE_UNLOCK_SECRET` env var is used by both this module
(Streamlit-side verify) and the Cloudflare Worker (issue side). They
sign independently and stateless-ly — no shared database.

Token format: `<base64url(payload_json)>.<base64url(hmac_sha256)>`
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

_ALG = hashlib.sha256


def _secret() -> bytes:
    val = os.environ.get("STRIPE_UNLOCK_SECRET")
    if not val:
        try:
            import streamlit as st
            val = st.secrets.get("STRIPE_UNLOCK_SECRET")
        except Exception:
            val = None
    if not val:
        raise RuntimeError(
            "STRIPE_UNLOCK_SECRET is not configured. Set it in env or Streamlit secrets."
        )
    return val.encode("utf-8")


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def sign_token(session_id: str, ttl_days: int = 90, tier: str = "wc26-full") -> str:
    """Sign an unlock token for a Stripe checkout session.

    Args:
        session_id: Stripe Checkout session id (e.g. "cs_test_..."). Opaque to us.
        ttl_days:   How long the token is valid for. Default 90 days covers
                    the entire WC2026 window with a buffer.
        tier:       Which paid tier this unlocks. Reserved for future tiers.
    """
    payload = {"sid": session_id, "exp": int(time.time()) + ttl_days * 86400, "tier": tier}
    payload_b = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    sig = hmac.new(_secret(), payload_b, _ALG).digest()
    return f"{_b64url(payload_b)}.{_b64url(sig)}"


def verify_token(token: str) -> dict | None:
    """Verify a token. Returns the decoded payload, or None if invalid/expired."""
    if not token or token.count(".") != 1:
        return None
    payload_part, sig_part = token.split(".", 1)
    try:
        payload_b = _b64url_decode(payload_part)
        sig = _b64url_decode(sig_part)
    except Exception:
        return None
    expected = hmac.new(_secret(), payload_b, _ALG).digest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        payload = json.loads(payload_b.decode("utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict) or "exp" not in payload:
        return None
    if int(payload["exp"]) < int(time.time()):
        return None
    return payload


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "sign":
        sid = sys.argv[2] if len(sys.argv) > 2 else "cs_local_test"
        print(sign_token(sid))
    elif len(sys.argv) > 1 and sys.argv[1] == "verify":
        print(verify_token(sys.argv[2]))
    else:
        t = sign_token("cs_local_test")
        print("Generated token:", t)
        print("Verified payload:", verify_token(t))
