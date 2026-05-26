"""Retry just the failed teams from fetch_wiki_logos.py with rate-limit delay."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor import PredictorBundle
from scripts.fetch_wiki_logos import WIKI_API, HEADERS, WIKI_TITLES, fetch_wiki_badge

OUT = ROOT / "data" / "processed" / "club_logos.json"


def main() -> None:
    existing = json.loads(OUT.read_text(encoding="utf-8"))
    bundle = PredictorBundle.load("leagues")
    teams = sorted(set(bundle.teams))

    pending = [t for t in teams if t not in existing and t in WIKI_TITLES]
    print(f"Retrying {len(pending)} teams with 1.5s delay between requests...\n")

    added = 0
    failed: list[str] = []
    for t in pending:
        title = WIKI_TITLES[t]
        badge = fetch_wiki_badge(title)
        if badge:
            existing[t] = badge
            added += 1
            print(f"  + {t}: {badge[:80]}")
        else:
            failed.append(t)
            print(f"  - {t}: still no badge")
        time.sleep(1.5)

    OUT.write_text(json.dumps(existing, indent=2, sort_keys=True), encoding="utf-8")
    print(f"\nAdded {added}. Still failing: {len(failed)} -> {failed}")
    print(f"Final coverage: {len(existing)} / {len(teams)} "
          f"({100*len(existing)/len(teams):.0f}%)")


if __name__ == "__main__":
    main()
