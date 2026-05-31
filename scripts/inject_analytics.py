"""Patch Streamlit's index.html at build time.

Streamlit gives no supported way to add tags to the page <head>, so we patch
the installed package's index.html during the deploy build. Run it AFTER
`pip install` in the build command:

    pip install -r requirements.txt && python scripts/inject_analytics.py

It does two things:
  1. Open Graph + Twitter Card meta, so links to the site unfurl with a proper
     title, description and preview image (instead of Streamlit's default
     "enable JavaScript" message). Always injected.
  2. The Plausible analytics snippet, if PLAUSIBLE_DOMAIN is set.

Everything is overridable by env vars but ships with working defaults, so a
plain `python scripts/inject_analytics.py` already does the right thing.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


OG_DEFAULTS = {
    "OG_TITLE": "WC26 Picks",
    "OG_DESCRIPTION": ("Score predictions for all 104 World Cup 2026 matches, "
                       "tuned to your office pool's scoring. Free preview, "
                       "£7 to unlock the full tournament."),
    "OG_URL": "https://wcpicks26.app",
    "OG_IMAGE": ("https://raw.githubusercontent.com/jdgoated1/"
                 "football-predictor/main/assets/og-image.png"),
}


def _esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace('"', "&quot;")
             .replace("<", "&lt;").replace(">", "&gt;"))


def _og_block() -> str:
    v = {k: os.environ.get(k, d) for k, d in OG_DEFAULTS.items()}
    t, desc, url, img = (_esc(v["OG_TITLE"]), _esc(v["OG_DESCRIPTION"]),
                         _esc(v["OG_URL"]), _esc(v["OG_IMAGE"]))
    return (
        f'<meta property="og:type" content="website">'
        f'<meta property="og:site_name" content="WC26 Picks">'
        f'<meta property="og:title" content="{t}">'
        f'<meta property="og:description" content="{desc}">'
        f'<meta property="og:url" content="{url}">'
        f'<meta property="og:image" content="{img}">'
        f'<meta property="og:image:width" content="1200">'
        f'<meta property="og:image:height" content="630">'
        f'<meta name="twitter:card" content="summary_large_image">'
        f'<meta name="twitter:title" content="{t}">'
        f'<meta name="twitter:description" content="{desc}">'
        f'<meta name="twitter:image" content="{img}">'
        f'<meta name="description" content="{desc}">'
    )


def _plausible_block() -> str:
    domain = os.environ.get("PLAUSIBLE_DOMAIN", "").strip()
    if not domain:
        return ""
    src = os.environ.get("PLAUSIBLE_SRC", "https://plausible.io/js/script.js").strip()
    return f'<script defer data-domain="{_esc(domain)}" src="{_esc(src)}"></script>'


def main() -> int:
    try:
        import streamlit
    except ImportError:
        print("[inject] streamlit not importable, skipping.", file=sys.stderr)
        return 0

    index_path = Path(streamlit.__file__).parent / "static" / "index.html"
    if not index_path.exists():
        print(f"[inject] {index_path} not found, skipping.", file=sys.stderr)
        return 0

    html = index_path.read_text(encoding="utf-8")
    if "</head>" not in html:
        print("[inject] no </head>, skipping.", file=sys.stderr)
        return 0

    additions = ""
    if 'property="og:title"' not in html:
        additions += _og_block()
    else:
        print("[inject] OG tags already present.")
    plausible = _plausible_block()
    if plausible and "plausible.io" not in html:
        additions += plausible
    elif plausible:
        print("[inject] Plausible already present.")

    if not additions:
        print("[inject] nothing to add.")
        return 0

    html = html.replace("</head>", additions + "</head>", 1)
    index_path.write_text(html, encoding="utf-8")
    print("[inject] Injected OG/Twitter meta"
          + (" + Plausible" if plausible else "") + ".")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
