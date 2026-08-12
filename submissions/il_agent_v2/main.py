"""Imitation-learning agent (v2, pure-stdlib) — scores each legal option with a trained model,
picks options above a threshold (clipped to [minCount, maxCount]).

This version uses ZERO external packages (no numpy/pandas/scikit-learn/joblib) — the first
version of this agent ERRORed on the real Kaggle submission despite running perfectly locally
and on the extracted tar, which strongly suggests the competition's simulation sandbox doesn't
include the data-science stack an interactive Kaggle notebook has (every other submission here
only ever needed stdlib + the compiled cg engine; this was the first to pull in anything else).
`pure_predictor.py` re-implements the trained HistGradientBoostingClassifier's decision function
in plain Python (validated bit-for-bit identical to sklearn's own predict_proba before shipping)
so the model itself doesn't change, only how it's evaluated.

Deck: the real modal Grimmsnarl ex/Froslass decklist mined directly from the training replay
data (24% of real submissions in the sampled data) — the very first IL attempt shipped an
Archaludon deck that essentially never appeared in its own training data.

Kaggle runs this file via exec() with no __file__ in scope; every path lookup below guards for
that (see CLAUDE.md's "exec()-without-__file__ gotcha" section for why).
"""

import os

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
import pure_predictor  # noqa: E402

_BUNDLE = pure_predictor.load(_find(os.path.join("models", "il_scorer_v2_pure.json")))
_FEATURE_COLUMNS = _BUNDLE["feature_columns"]
_CARD_DATA = il_features.load_card_data(_find("EN_Card_Data.csv"))
_ATTACK_DATA = il_features.load_attack_data(_find("EN_Attack_Data.csv"))
_CARD_ATTRS = il_features.load_card_attrs(_find("EN_Card_Attrs.csv"))

# Selection threshold: probability above which an option is taken, before clipping to
# [minCount, maxCount]. Not calibrated against a held-out exact-set-match objective yet (that's
# a documented follow-up in the plan) — 0.5 is a reasonable pointwise-classifier default given
# class_weight="balanced" training.
_THRESHOLD = 0.5


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
    rows = [
        il_features.option_features(option, select, current, _CARD_DATA, _ATTACK_DATA, _CARD_ATTRS, g)
        for option in options
    ]
    il_features._add_listwise_features(rows)
    feature_rows = [[row.get(col, -1) for col in _FEATURE_COLUMNS] for row in rows]
    return pure_predictor.predict_proba_batch(_BUNDLE, feature_rows)


def agent(obs_dict):
    if obs_dict.get("select") is None:
        return _read_deck_csv()

    select = obs_dict["select"]
    current = obs_dict["current"]
    options = select.get("option") or []
    if not options:
        return []

    min_count = select.get("minCount", 1) or 1
    max_count = select.get("maxCount", 1) or 1

    try:
        scores = _score_options(select, current)
        ranked = sorted(range(len(options)), key=lambda i: scores[i], reverse=True)
        above_threshold = [i for i in ranked if scores[i] > _THRESHOLD]

        if len(above_threshold) < min_count:
            chosen = ranked[:min_count]
        elif len(above_threshold) > max_count:
            chosen = ranked[:max_count]
        else:
            chosen = above_threshold

        if min_count == 0 and not chosen:
            return []
        return chosen
    except Exception:
        # Never crash, never return the deck list mid-game (see CLAUDE.md #730707 lesson) —
        # fall back to the first minCount legal options (or [] when none are required).
        return list(range(min(min_count, len(options))))
