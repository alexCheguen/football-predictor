"""In-process data layer the Streamlit app uses.

Originally an HTTP client for the FastAPI service. Now calls `api.sources`
directly so the Streamlit Cloud deployment works with no external dependency.

The function names/signatures are kept identical to the old HTTP version
(including the unused `base` argument) so the rest of `app.py` didn't have
to change. The FastAPI service still exists at `api/main.py` and can be
deployed separately for external website consumers.
"""
from __future__ import annotations

import streamlit as st

from api import sources as _sources


# `base` is ignored - kept for signature compatibility with the old HTTP client.
def api_base() -> str:
    return "in-process"


@st.cache_data(ttl=60, show_spinner=False)
def health(base: str) -> dict | None:
    return {"name": "Football Predictor (in-process)", "mode": "direct"}


@st.cache_data(ttl=60, show_spinner=False)
def fetch_freshness(base: str) -> dict:
    return _sources.data_freshness()


@st.cache_data(ttl=600, show_spinner="Fetching fixtures...")
def fetch_fixtures(base: str, league: str, days: int = 14) -> list[dict]:
    return _sources.fixtures(league, days=days)


@st.cache_data(ttl=600, show_spinner="Fetching results...")
def fetch_results(base: str, league: str, limit: int = 20) -> list[dict]:
    return _sources.results(league, limit=limit)


@st.cache_data(ttl=600, show_spinner="Fetching standings...")
def fetch_standings(base: str, league: str) -> list[dict]:
    return _sources.standings(league)


@st.cache_data(ttl=3600, show_spinner="Fetching lineups...")
def fetch_lineup(base: str, game_id: str, league: str) -> dict:
    data = _sources.lineup(game_id, league_name=league)
    if not data.get("home") or not data.get("away"):
        raise RuntimeError(
            "Lineups not available (match not yet played or FBref has no lineup data).")
    return {
        "game_id": game_id,
        "home": data["home"],
        "away": data["away"],
        "note": "FBref publishes lineups post-match. Pre-match starting XIs are not available from this source.",
    }


@st.cache_data(ttl=60, show_spinner=False)
def fetch_leagues(base: str) -> list[str]:
    return _sources.list_leagues()


@st.cache_data(ttl=600, show_spinner="Fetching teams...")
def fetch_league_teams(base: str, league: str) -> list[str]:
    return _sources.teams_in_league(league)


@st.cache_data(ttl=600, show_spinner="Fetching team form...")
def fetch_team_form(base: str, team: str, league: str, n: int = 10) -> dict:
    return _sources.team_form(team, league, n=n)


@st.cache_data(ttl=3600, show_spinner="Fetching last lineups (FBref - slow first call)...")
def fetch_team_lineups(base: str, team: str, league: str, n: int = 5) -> dict:
    return _sources.team_last_lineups(team, league, n=n)


@st.cache_data(ttl=3600, show_spinner="Predicting starting XI (FBref - slow first call)...")
def fetch_predicted_xi(base: str, team: str, league: str, lookback: int = 5) -> dict:
    return _sources.predicted_xi(team, league, lookback=lookback)
