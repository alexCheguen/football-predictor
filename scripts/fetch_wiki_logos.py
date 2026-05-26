"""Fallback fetcher for clubs not covered by luukhopman/football-logos.

The luukhopman repo only carries current top-5 league teams. For historical
clubs (relegated sides still present in our bundle), we hit Wikipedia's REST
API to grab the club's main image. The mapping is then merged into the
existing club_logos.json.

Manual page-title hints are needed because there's no single naming convention.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor import PredictorBundle

OUT = ROOT / "data" / "processed" / "club_logos.json"
WIKI_API = "https://en.wikipedia.org/api/rest_v1/page/summary/"
HEADERS = {"User-Agent": "football-predictor-logos/1.0"}

# Bundle-name -> Wikipedia page title. Covers historical (relegated/lower-div)
# teams that the luukhopman repo lacks.
WIKI_TITLES = {
    # --- English (Championship / lower-division alumni) ---
    "Birmingham": "Birmingham City F.C.",
    "Blackburn": "Blackburn Rovers F.C.",
    "Blackpool": "Blackpool F.C.",
    "Bolton": "Bolton Wanderers F.C.",
    "Cardiff": "Cardiff City F.C.",
    "Huddersfield": "Huddersfield Town A.F.C.",
    "Hull": "Hull City A.F.C.",
    "Ipswich": "Ipswich Town F.C.",
    "Leicester": "Leicester City F.C.",
    "Luton": "Luton Town F.C.",
    "Middlesbrough": "Middlesbrough F.C.",
    "Norwich": "Norwich City F.C.",
    "QPR": "Queens Park Rangers F.C.",
    "Reading": "Reading F.C.",
    "Sheffield United": "Sheffield United F.C.",
    "Southampton": "Southampton F.C.",
    "Stoke": "Stoke City F.C.",
    "Swansea": "Swansea City A.F.C.",
    "Watford": "Watford F.C.",
    "West Brom": "West Bromwich Albion F.C.",
    "Wigan": "Wigan Athletic F.C.",
    # --- Spanish (Segunda alumni) ---
    "Almeria": "UD Almería",
    "Cadiz": "Cádiz CF",
    "Cordoba": "Córdoba CF",
    "Eibar": "SD Eibar",
    "Granada": "Granada CF",
    "Hercules": "Hercules CF",
    "Huesca": "SD Huesca",
    "Las Palmas": "UD Las Palmas",
    "Leganes": "CD Leganés",
    "Malaga": "Málaga CF",
    "Santander": "Racing de Santander",
    "Sp Gijon": "Sporting de Gijón",
    "La Coruna": "Deportivo de La Coruña",
    "Valladolid": "Real Valladolid CF",
    "Zaragoza": "Real Zaragoza",
    "Arles": "AC Arles",
    # --- German (2.Bundesliga alumni) ---
    "Bielefeld": "Arminia Bielefeld",
    "Bochum": "VfL Bochum",
    "Braunschweig": "Eintracht Braunschweig",
    "Darmstadt": "SV Darmstadt 98",
    "Fortuna Dusseldorf": "Fortuna Düsseldorf",
    "Greuther Furth": "SpVgg Greuther Fürth",
    "Hannover": "Hannover 96",
    "Hertha": "Hertha BSC",
    "Holstein Kiel": "Holstein Kiel",
    "Ingolstadt": "FC Ingolstadt 04",
    "Kaiserslautern": "1. FC Kaiserslautern",
    "Nurnberg": "1. FC Nürnberg",
    "Paderborn": "SC Paderborn 07",
    "Schalke 04": "FC Schalke 04",
    # --- Italian (Serie B alumni) ---
    "Bari": "S.S.C. Bari",
    "Benevento": "Benevento Calcio",
    "Brescia": "Brescia Calcio",
    "Carpi": "Carpi F.C. 1909",
    "Catania": "Catania F.C.",
    "Cesena": "Cesena F.C.",
    "Chievo": "A.C. ChievoVerona",
    "Crotone": "F.C. Crotone",
    "Empoli": "Empoli F.C.",
    "Frosinone": "Frosinone Calcio",
    "Livorno": "AS Livorno Calcio",
    "Monza": "A.C. Monza",
    "Novara": "Novara F.C.",
    "Palermo": "Palermo F.C.",
    "Pescara": "Delfino Pescara 1936",
    "Salernitana": "U.S. Salernitana 1919",
    "Sampdoria": "U.C. Sampdoria",
    "Siena": "A.C.N. Siena 1904",
    "Spal": "S.P.A.L. 2013",
    "Spezia": "Spezia Calcio",
    "Venezia": "Venezia FC",
    # --- French (Ligue 2 alumni) ---
    "Ajaccio": "AC Ajaccio",
    "Ajaccio GFCO": "Gazelec Ajaccio",
    "Amiens": "Amiens SC",
    "Arles": "AC Arles-Avignon",
    "Bastia": "SC Bastia",
    "Bordeaux": "FC Girondins de Bordeaux",
    "Caen": "Stade Malherbe Caen",
    "Clermont": "Clermont Foot",
    "Dijon": "Dijon FCO",
    "Evian Thonon Gaillard": "Thonon Evian F.C.",
    "Guingamp": "En Avant Guingamp",
    "Montpellier": "Montpellier HSC",
    "Nancy": "AS Nancy",
    "Nimes": "Nîmes Olympique",
    "Reims": "Stade de Reims",
    "Sochaux": "FC Sochaux-Montbéliard",
    "St Etienne": "AS Saint-Étienne",
    "Troyes": "ES Troyes AC",
    "Valenciennes": "Valenciennes FC",
}


def fetch_wiki_badge(title: str) -> str | None:
    """Hit Wikipedia REST summary, return originalimage source (badge URL)."""
    try:
        url = WIKI_API + title.replace(" ", "_")
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code != 200:
            return None
        j = r.json()
        img = (j.get("originalimage") or {}).get("source")
        if img:
            return img
        # fall back to thumbnail
        return (j.get("thumbnail") or {}).get("source")
    except requests.RequestException:
        return None


def main() -> None:
    existing = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    bundle = PredictorBundle.load("leagues")
    teams = sorted(set(bundle.teams))

    added: list[str] = []
    skipped_existing: list[str] = []
    no_hint: list[str] = []
    failed: list[str] = []

    for t in teams:
        if t in existing:
            skipped_existing.append(t)
            continue
        title = WIKI_TITLES.get(t)
        if not title:
            no_hint.append(t)
            continue
        badge = fetch_wiki_badge(title)
        if badge:
            existing[t] = badge
            added.append(t)
            print(f"  + {t}: {badge[:80]}...")
        else:
            failed.append(t)
            print(f"  - {t}: no badge from wiki page '{title}'")

    OUT.write_text(json.dumps(existing, indent=2, sort_keys=True), encoding="utf-8")
    print(f"\nAlready had: {len(skipped_existing)}")
    print(f"Newly added: {len(added)}")
    print(f"No wiki hint: {len(no_hint)} -> {no_hint}")
    print(f"Wiki lookup failed: {len(failed)} -> {failed}")
    print(f"Final coverage: {len(existing)} / {len(teams)} "
          f"({100*len(existing)/len(teams):.0f}%)")


if __name__ == "__main__":
    main()
