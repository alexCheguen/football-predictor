"""Refresh cached schedule + lineup data for the Live data tab.

Designed to run inside the daily GitHub Action (where Chrome is available).
The Streamlit Cloud deployment is read-only and cannot run Selenium itself,
so this script writes parquet files that the app reads at runtime.

Outputs:
    data/processed/live/schedules.parquet  - one row per match across all leagues
    data/processed/live/lineups.parquet    - one row per player per match

Both files are incremental: the script only fetches what isn't already cached.
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
LIVE_DIR = ROOT / "data" / "processed" / "live"
LIVE_DIR.mkdir(parents=True, exist_ok=True)
SCHEDULES_PATH = LIVE_DIR / "schedules.parquet"
LINEUPS_PATH = LIVE_DIR / "lineups.parquet"

LEAGUES: dict[str, str] = {
    "EPL": "ENG-Premier League",
    "LaLiga": "ESP-La Liga",
    "Bundesliga": "GER-Bundesliga",
    "SerieA": "ITA-Serie A",
    "Ligue1": "FRA-Ligue 1",
}


def current_season() -> str:
    today = datetime.today()
    start = today.year if today.month >= 8 else today.year - 1
    return f"{str(start)[-2:]}{str(start + 1)[-2:]}"


def refresh_schedules(season: str) -> pd.DataFrame:
    """Fetch the schedule for every league and return a flat DataFrame."""
    import soccerdata as sd
    frames = []
    for league_key, fb_code in LEAGUES.items():
        print(f"[schedule] {league_key} ({fb_code}) season {season}...", flush=True)
        try:
            fb = sd.FBref(leagues=fb_code, seasons=season, no_cache=False)
            df = fb.read_schedule().reset_index()
            df["league"] = league_key
            df["season"] = season
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
            frames.append(df)
            print(f"  -> {len(df)} matches", flush=True)
        except Exception as e:
            print(f"  ! schedule fetch failed for {league_key}: {e}", flush=True)
    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True)
    return combined


def _lineup_target_game_ids(schedule: pd.DataFrame, days_back: int = 21) -> pd.DataFrame:
    """Pick the recent completed matches that we want lineups for.

    We don't want to fetch lineups for every match all season - just enough
    to cover 'last 5 per team' lookups. Pulling everything completed in the
    last `days_back` days reliably covers that without unbounded work.
    """
    if schedule.empty:
        return schedule
    today = pd.Timestamp(datetime.today().date())
    cutoff = today - pd.Timedelta(days=days_back)
    mask = schedule["date"].notna() & (schedule["date"] >= cutoff) & (schedule["date"] <= today)
    recent = schedule[mask].copy()
    if "score" in recent.columns:
        recent = recent[recent["score"].astype(str).str.contains(r"\d", na=False)]
    return recent


def refresh_lineups(schedule: pd.DataFrame, season: str,
                   existing: pd.DataFrame | None = None) -> pd.DataFrame:
    """Fetch lineups for any recent completed matches that aren't already cached."""
    import soccerdata as sd

    if existing is None:
        existing = pd.DataFrame()
    cached_gids: set[str] = (
        set(existing["game_id"].astype(str).unique()) if not existing.empty else set()
    )

    targets = _lineup_target_game_ids(schedule)
    if targets.empty:
        print("[lineups] no recent completed matches to fetch", flush=True)
        return existing

    # Group by league so we can reuse the same FBref reader per league
    new_rows: list[pd.DataFrame] = []
    by_league = targets.groupby("league")
    for league_key, sub in by_league:
        fb_code = LEAGUES.get(league_key)
        if not fb_code:
            continue
        fb = sd.FBref(leagues=fb_code, seasons=season, no_cache=False)
        pending = [str(g) for g in sub["game_id"].dropna().unique() if str(g) and str(g) not in cached_gids]
        print(f"[lineups] {league_key}: {len(pending)} new game(s) to fetch", flush=True)
        for i, gid in enumerate(pending, 1):
            try:
                lp = fb.read_lineup(match_id=gid).reset_index()
                lp["game_id"] = gid
                lp["league"] = league_key
                lp["season"] = season
                # Carry the match date forward for easier filtering downstream
                row = sub[sub["game_id"] == gid].iloc[0]
                lp["date"] = row["date"]
                lp["home_team"] = row.get("home_team")
                lp["away_team"] = row.get("away_team")
                new_rows.append(lp)
                print(f"  [{i}/{len(pending)}] {gid} OK", flush=True)
            except Exception as e:
                print(f"  [{i}/{len(pending)}] {gid} FAIL: {e}", flush=True)
            time.sleep(0.5)  # be gentle with FBref

    if not new_rows:
        return existing
    new_df = pd.concat(new_rows, ignore_index=True)
    if existing.empty:
        return new_df
    # Drop any rows in existing that share a game_id with new_df, then concat
    keep = existing[~existing["game_id"].astype(str).isin(new_df["game_id"].astype(str))]
    return pd.concat([keep, new_df], ignore_index=True)


def prune_old_lineups(lineups: pd.DataFrame, keep_days: int = 90) -> pd.DataFrame:
    """Drop lineup rows for matches older than `keep_days` to bound file size."""
    if lineups.empty or "date" not in lineups.columns:
        return lineups
    cutoff = pd.Timestamp(datetime.today().date()) - pd.Timedelta(days=keep_days)
    return lineups[pd.to_datetime(lineups["date"], errors="coerce") >= cutoff].copy()


def main(only_league: str | None = None) -> None:
    season = current_season()
    print(f"=== refresh_live_data | season {season} ===", flush=True)

    schedules = refresh_schedules(season)
    if only_league:
        schedules = schedules[schedules["league"] == only_league].copy()
    if not schedules.empty:
        schedules.to_parquet(SCHEDULES_PATH, index=False)
        print(f"Wrote {len(schedules)} schedule rows -> {SCHEDULES_PATH}", flush=True)

    existing_lineups = pd.read_parquet(LINEUPS_PATH) if LINEUPS_PATH.exists() else None
    lineups = refresh_lineups(schedules, season, existing=existing_lineups)
    lineups = prune_old_lineups(lineups)
    if not lineups.empty:
        lineups.to_parquet(LINEUPS_PATH, index=False)
        print(f"Wrote {len(lineups)} lineup rows -> {LINEUPS_PATH}", flush=True)


if __name__ == "__main__":
    only = sys.argv[1] if len(sys.argv) > 1 else None
    main(only_league=only)
