"""Imitation-learning agent (v1) — scores each legal option with a trained model, picks the
highest. Deck: Archaludon ex/Cinderace (same as our current best rule-based submission) —
mining a better deck from the training data is future work, not done for this v1.

Kaggle runs this file via exec() with no __file__ in scope; every path lookup below guards for
that (see CLAUDE.md's "exec()-without-__file__ gotcha" section for why).
"""

import os
import warnings

warnings.filterwarnings("ignore")  # cosmetic sklearn "no feature names" warning — harmless,
# we pass columns in the exact order saved with the model.

try:
    _HERE = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _HERE = None

_CANDIDATE_DIRS = [d for d in [_HERE, "/kaggle_simulations/agent", os.getcwd()] if d]


def _find(filename):
    for d in _CANDIDATE_DIRS:
        path = os.path.join(d, filename)
        if os.path.exists(path):
            return path
    return filename  # last resort — relative to cwd


import sys  # noqa: E402

for _d in _CANDIDATE_DIRS:
    if _d not in sys.path:
        sys.path.insert(0, _d)

import il_features  # noqa: E402

import joblib  # noqa: E402
import numpy as np  # noqa: E402

# Safe: this pickle is our own model artifact, produced by src/train_il_model.py in this same
# repo/session from our own training data — not loading anything from an untrusted source.
_BUNDLE = joblib.load(_find(os.path.join("models", "il_scorer_v1.pkl")))
_MODEL = _BUNDLE["model"]
_FEATURE_COLUMNS = _BUNDLE["feature_columns"]
_CARD_DATA = il_features.load_card_data(_find("EN_Card_Data.csv"))
_ATTACK_DATA = il_features.load_attack_data(_find("EN_Attack_Data.csv"))


def _read_deck_csv():
    file_path = "deck.csv"
    if not os.path.exists(file_path):
        file_path = "/kaggle_simulations/agent/deck.csv"
    if not os.path.exists(file_path):
        file_path = _find("deck.csv")
    with open(file_path, "r") as f:
        lines = f.read().split("\n")
    return [int(lines[i]) for i in range(60)]


def _score_options(select, current):
    options = select.get("option") or []
    g = il_features.global_features(select, current)
    rows = []
    for option in options:
        o = il_features.option_features(option, current, _CARD_DATA, _ATTACK_DATA)
        row = {**g, **o}
        rows.append([row.get(col, -1) for col in _FEATURE_COLUMNS])
    X = np.array(rows, dtype=float)
    scores = _MODEL.predict_proba(X)[:, 1]
    return scores


def agent(obs_dict):
    if obs_dict.get("select") is None:
        return _read_deck_csv()

    select = obs_dict["select"]
    current = obs_dict["current"]
    options = select.get("option") or []
    if not options:
        return []

    try:
        scores = _score_options(select, current)
        max_count = select.get("maxCount", 1) or 1
        k = max(1, min(max_count, len(options)))
        ranked = sorted(range(len(options)), key=lambda i: scores[i], reverse=True)
        return ranked[:k]
    except Exception:
        # Never crash, never return the deck list mid-game (see CLAUDE.md #730707 lesson) —
        # fall back to the first minCount legal options.
        min_count = select.get("minCount", 1) or 1
        return list(range(min(min_count, len(options))))
