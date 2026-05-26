"""Lazy-loaded predictor service.

Loads PredictorBundle joblib files once on first request and caches them in
memory. Joblib loading is slow (tens of MB of trained models), so we never
re-load inside a request.
"""
from __future__ import annotations

import threading
from pathlib import Path

import numpy as np
import pandas as pd

from src.predictor import PredictorBundle


_BUNDLES: dict[str, PredictorBundle] = {}
_LOCK = threading.Lock()


def get_bundle(scope: str) -> PredictorBundle:
    if scope not in {"leagues", "internationals"}:
        raise ValueError(f"Unknown scope '{scope}'. Must be 'leagues' or 'internationals'.")
    if scope in _BUNDLES:
        return _BUNDLES[scope]
    with _LOCK:
        if scope not in _BUNDLES:
            _BUNDLES[scope] = PredictorBundle.load(scope)
    return _BUNDLES[scope]


def teams(scope: str) -> list[str]:
    return list(get_bundle(scope).teams)


def predict(home: str, away: str, scope: str = "leagues", neutral: bool = False) -> dict:
    bundle = get_bundle(scope)
    known = set(bundle.teams)
    missing = [t for t in (home, away) if t not in known]
    if missing:
        raise ValueError(
            f"Unknown team(s) for scope '{scope}': {missing}. "
            f"Call GET /teams?scope={scope} to list available teams."
        )

    raw = bundle.predict(home, away, neutral=neutral)
    top = [
        {"home_goals": int(hg), "away_goals": int(ag), "prob": float(p)}
        for (hg, ag, p) in raw["top_scores"]
    ]
    ml_hg, ml_ag = raw["most_likely"]

    def _round_dict(d):
        if d is None:
            return None
        return {k: round(float(v), 4) for k, v in d.items()}

    sm = raw.get("score_matrix")
    sm_list = sm.tolist() if sm is not None else None

    return {
        "home": home,
        "away": away,
        "scope": scope,
        "neutral": neutral,
        "probabilities": _round_dict(raw["outcome"]),
        "expected_goals": {
            "home": round(float(raw["lambda_home"]), 3),
            "away": round(float(raw["lambda_away"]), 3),
        },
        "top_scores": top,
        "most_likely": {"home_goals": int(ml_hg), "away_goals": int(ml_ag)},
        "score_matrix": sm_list,
        "model_breakdown": {
            "dc": _round_dict(raw.get("dc_outcome")),
            "xgb": _round_dict(raw.get("xgb_outcome")),
            "lgb": _round_dict(raw.get("lgb_outcome")),
            "cat": _round_dict(raw.get("cat_outcome")),
            "stacked": _round_dict(raw.get("stacked_outcome")),
        },
    }
