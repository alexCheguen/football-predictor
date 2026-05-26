"""FastAPI service for the football predictor.

Run locally:
    uvicorn api.main:app --reload --port 8000

Interactive docs:
    http://127.0.0.1:8000/docs
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from . import predictor_service, sources
from .schemas import (
    Fixture,
    MatchLineup,
    Prediction,
    PredictionRequest,
    Result,
    Standing,
)

app = FastAPI(
    title="Football Predictor API",
    description=(
        "Free football data + model predictions. Sources: FBref via soccerdata "
        "for fixtures/results/standings/lineups; locally trained ensemble for predictions."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root() -> dict:
    return {
        "name": "Football Predictor API",
        "docs": "/docs",
        "endpoints": [
            "/leagues",
            "/fixtures?league=EPL&days=14",
            "/results?league=EPL&limit=20",
            "/standings?league=EPL",
            "/lineups?game_id=...&league=EPL",
            "/league/teams?league=EPL",
            "/team/form?team=Arsenal&league=EPL&n=10",
            "/team/lineups?team=Arsenal&league=EPL&n=5",
            "/team/predicted-xi?team=Arsenal&league=EPL&lookback=5",
            "/teams?scope=leagues",
            "POST /predict",
        ],
    }


@app.get("/leagues")
def leagues() -> dict:
    return {"leagues": sources.list_leagues()}


@app.get("/fixtures", response_model=list[Fixture])
def get_fixtures(
    league: str = Query(..., description="EPL | LaLiga | Bundesliga | SerieA | Ligue1"),
    days: int = Query(14, ge=1, le=60, description="Look-ahead window in days"),
    season: str | None = Query(None, description="Season code e.g. '2526' (defaults to current)"),
):
    try:
        return sources.fixtures(league, days=days, season=season)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"FBref fetch failed: {e}")


@app.get("/results", response_model=list[Result])
def get_results(
    league: str = Query(..., description="EPL | LaLiga | Bundesliga | SerieA | Ligue1"),
    limit: int = Query(20, ge=1, le=100),
    season: str | None = Query(None),
):
    try:
        return sources.results(league, limit=limit, season=season)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"FBref fetch failed: {e}")


@app.get("/standings", response_model=list[Standing])
def get_standings(
    league: str = Query(..., description="EPL | LaLiga | Bundesliga | SerieA | Ligue1"),
    season: str | None = Query(None),
):
    try:
        return sources.standings(league, season=season)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"FBref fetch failed: {e}")


@app.get("/lineups", response_model=MatchLineup)
def get_lineups(
    game_id: str = Query(..., description="FBref game_id from /fixtures or /results"),
    league: str = Query(..., description="League the match belongs to"),
    season: str | None = Query(None),
):
    try:
        data = sources.lineup(game_id, league_name=league, season=season)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"FBref fetch failed: {e}")
    if not data.get("home") or not data.get("away"):
        raise HTTPException(
            status_code=404,
            detail="Lineups not available (match not yet played or FBref has no lineup data).",
        )
    return {"game_id": game_id, "home": data["home"], "away": data["away"]}


@app.get("/teams")
def get_teams(scope: str = Query("leagues", description="'leagues' or 'internationals'")):
    try:
        return {"scope": scope, "teams": predictor_service.teams(scope)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/league/teams")
def get_league_teams(
    league: str = Query(..., description="EPL | LaLiga | Bundesliga | SerieA | Ligue1"),
    season: str | None = Query(None),
):
    """List team names appearing in this season's schedule (FBref naming).
    Use these names for the /team/* endpoints below."""
    try:
        return {"league": league, "teams": sources.teams_in_league(league, season=season)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"FBref fetch failed: {e}")


@app.get("/team/form")
def get_team_form(
    team: str = Query(..., description="Team name as it appears in FBref (see /league/teams)"),
    league: str = Query(..., description="EPL | LaLiga | Bundesliga | SerieA | Ligue1"),
    n: int = Query(10, ge=1, le=38, description="Number of recent completed matches"),
    season: str | None = Query(None),
):
    try:
        return sources.team_form(team, league, n=n, season=season)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"FBref fetch failed: {e}")


@app.get("/team/lineups")
def get_team_lineups(
    team: str = Query(..., description="Team name as it appears in FBref (see /league/teams)"),
    league: str = Query(..., description="EPL | LaLiga | Bundesliga | SerieA | Ligue1"),
    n: int = Query(5, ge=1, le=10, description="Number of recent lineups (each is an extra FBref call)"),
    season: str | None = Query(None),
):
    """Last N starting XIs for this team. Slow on first call (N FBref requests);
    cached for 1 hour."""
    try:
        return sources.team_last_lineups(team, league, n=n, season=season)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"FBref fetch failed: {e}")


@app.get("/team/predicted-xi")
def get_predicted_xi(
    team: str = Query(..., description="Team name as it appears in FBref (see /league/teams)"),
    league: str = Query(..., description="EPL | LaLiga | Bundesliga | SerieA | Ligue1"),
    lookback: int = Query(5, ge=2, le=10, description="Matches to base the prediction on"),
    season: str | None = Query(None),
):
    """Most-likely starting XI based on the team's recent rotation pattern.
    Does NOT factor in injuries, suspensions, or opponent-specific tactical changes -
    surface that to your users."""
    try:
        return sources.predicted_xi(team, league, lookback=lookback, season=season)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"FBref fetch failed: {e}")


@app.post("/predict", response_model=Prediction)
def post_predict(req: PredictionRequest):
    try:
        return predictor_service.predict(
            home=req.home, away=req.away, scope=req.scope, neutral=req.neutral
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prediction failed: {e}")
