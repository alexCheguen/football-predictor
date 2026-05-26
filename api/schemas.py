from __future__ import annotations

from pydantic import BaseModel, Field


class Fixture(BaseModel):
    date: str
    time: str | None = None
    home: str
    away: str
    league: str
    season: str
    venue: str | None = None
    week: str | None = None
    game_id: str | None = None


class Result(BaseModel):
    date: str
    home: str
    away: str
    home_goals: int
    away_goals: int
    league: str
    season: str
    game_id: str | None = None


class Standing(BaseModel):
    rank: int
    team: str
    played: int
    wins: int
    draws: int
    losses: int
    goals_for: int
    goals_against: int
    goal_diff: int
    points: int


class PlayerEntry(BaseModel):
    number: str | None = None
    name: str
    position: str | None = None
    minutes: int | None = None


class TeamLineup(BaseModel):
    team: str
    formation: str | None = None
    starting: list[PlayerEntry]
    bench: list[PlayerEntry]


class MatchLineup(BaseModel):
    game_id: str
    note: str = Field(
        default="FBref publishes lineups post-match. Pre-match starting XIs are not available from this source.",
    )
    home: TeamLineup
    away: TeamLineup


class PredictionRequest(BaseModel):
    home: str
    away: str
    scope: str = Field(default="leagues", description="'leagues' or 'internationals'")
    neutral: bool = False


class Prediction(BaseModel):
    home: str
    away: str
    scope: str
    neutral: bool
    probabilities: dict[str, float]
    expected_goals: dict[str, float]
    top_scores: list[dict]
    most_likely: dict
    score_matrix: list[list[float]] | None = None
    model_breakdown: dict[str, dict[str, float] | None] | None = None
