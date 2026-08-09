"""Adversarial validation: is the data a model trains on the data it actually meets at inference?

The generic Kaggle version of this asks "can a classifier tell train rows from test rows?" and
treats AUC > 0.70 as evidence of distribution shift. This competition has no test set, so the
question is re-pointed at the place where a train/deploy mismatch genuinely exists.

**`--mode il` — the live question.** The imitation-learning agent trains on states from *logged
episodes*, i.e. trajectories other agents produced, but at inference it visits states from *its
own* trajectory. That is textbook imitation-learning covariate shift, and it is the strongest
untested explanation for why IL has underperformed rule-based agents twice here (v2 settled 538.7
against Archaludon's 711.4; v3 was worse still). Both post-mortems responded with more data and
more features in the same shape — neither tested whether the shape was the problem. This does.

  class 0 = feature rows from the training JSONL
  class 1 = feature rows harvested from the IL agent's own self-play, via
            `ladder_eval.py rate --candidate submissions/il_agent_v2b --dump-states <dir>`

  Grouping is `GroupKFold` on `episode_id`, matching `train_il_model.py:64` — without it, rows
  from one episode land on both sides of the fold and the AUC is inflated by memorisation rather
  than by real shift.

  A high AUC here does NOT by itself establish IL covariate shift, let alone explain the score
  gap. Harvested states differ from the corpus for three reasons at once: the agent's own
  trajectory (the hypothesis), the opponents (local panel vs real ladder field), and harvesting
  mechanics (the corpus logs both players, the dump logs one side). `--control <dir>` supplies a
  non-IL agent harvested against the identical panel so the last two cancel and the *difference*
  in AUC isolates the first. Run it; without it the headline number is uninterpretable.

  Measured 2026-08-09: IL 0.9786, control (Archaludon) 0.9978, label-shuffle 0.5006. The control
  is more separable than IL, so the hypothesis is unsupported — see `evaluation-methodology.md`.

**`--mode roster` — how unrepresentative is the local panel?** The 7-agent frozen panel is a
convenience sample; the real ladder is a much larger, differently-composed field. This compares
the panel's deck archetypes against the archetype mix in the real episode data and reports how
much of the real field the panel actually covers.

Usage:
    python3 src/adversarial_validation.py --mode il \
        --train data/processed/il_records.jsonl --selfplay data/processed/selfplay
    python3 src/adversarial_validation.py --mode il ... --shuffle-labels   # sanity check
    python3 src/adversarial_validation.py --mode roster
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from features import build_dataset  # noqa: E402

AUC_THRESHOLD = 0.70


# ---------------------------------------------------------------------------
# IL covariate shift
# ---------------------------------------------------------------------------


def _concat_shards(selfplay_dir: Path) -> Path:
    """`ladder_eval.py --dump-states` writes one shard per worker process; join them."""
    shards = sorted(selfplay_dir.glob("shard_*.jsonl"))
    if not shards:
        raise SystemExit(
            f"no shard_*.jsonl in {selfplay_dir}. Generate them with:\n"
            f"    python3 src/ladder_eval.py rate --candidate submissions/il_agent_v2b "
            f"--games 200 --dump-states {selfplay_dir}"
        )
    merged = selfplay_dir / "_merged.jsonl"
    with merged.open("w") as out:
        for s in shards:
            out.write(s.read_text())
    return merged


def _load_side(path: Path, tag: str, max_records: int):
    rows, _labels, _dec, _w, episode_ids = build_dataset(str(path), max_records=max_records)
    # Prefix so a self-play episode can never share a group id with a logged one.
    groups = [f"{tag}:{e}" for e in episode_ids]
    return rows, groups


# `features.global_features` derives these two from the leaderboard score of the player who
# produced the record. States harvested from local self-play have no leaderboard join at all, so
# both are the constant `_score_norm(None)`. In `il_records_v3_combined.jsonl` only 46,013 of
# 626,019 records are unjoined, so a classifier would reach near-perfect AUC by reading a single
# column — a fact about how the two files were *built*, not about the state distributions the
# question is asking about. Keeping them would inflate the headline AUC in exactly the direction
# that confirms the hypothesis.
PROVENANCE_COLUMNS = ["actor_score_norm", "opp_score_norm"]


def _auc_between(rows_a, groups_a, rows_b, groups_b, folds, shuffle_labels=False,
                 verbose=True, want_model=False):
    """Out-of-fold ROC-AUC for separating side A (class 0) from side B (class 1).

    Sides are balanced to equal row counts so the classifier cannot score off the class prior, and
    folds are grouped by episode so rows from one episode never straddle a fold.
    Returns (auc, X, y) — X/y are the balanced, provenance-stripped design matrix, so a caller
    that wants permutation importances can refit on it without rebuilding.
    """
    n = min(len(rows_a), len(rows_b))
    rows_a, groups_a = rows_a[:n], groups_a[:n]
    rows_b, groups_b = rows_b[:n], groups_b[:n]
    if verbose:
        print(f"balanced to {n} rows per class")

    X = pd.DataFrame(rows_a + rows_b)
    y = np.array([0] * len(rows_a) + [1] * len(rows_b))
    groups = np.array(groups_a + groups_b)

    dropped = [c for c in PROVENANCE_COLUMNS if c in X.columns]
    if dropped:
        X = X.drop(columns=dropped)
        if verbose:
            print(f"dropped provenance columns (constant in harvested states): {dropped}")

    if shuffle_labels:
        # Sanity check: permute the label so the only thing destroyed is the A-vs-B signal. AUC
        # must collapse to ~0.50; if it does not, the pipeline leaks and every result is worthless.
        y = np.random.default_rng(0).permutation(y)
        if verbose:
            print("!! labels shuffled — sanity check, expect AUC ~= 0.50")

    n_splits = min(folds, len(set(groups)))
    if n_splits < 2:
        raise SystemExit(f"need >=2 distinct episodes to cross-validate, got {len(set(groups))}")
    oof = np.zeros(len(y))
    for k, (tr, te) in enumerate(GroupKFold(n_splits=n_splits).split(X, y, groups)):
        model = HistGradientBoostingClassifier(max_iter=200, max_depth=6,
                                               learning_rate=0.08, random_state=0)
        model.fit(X.iloc[tr], y[tr])
        oof[te] = model.predict_proba(X.iloc[te])[:, 1]
        if verbose:
            print(f"  fold {k + 1}/{n_splits}  train {len(tr)}  test {len(te)}")

    auc = roc_auc_score(y, oof)
    if verbose:
        print(f"\nout-of-fold ROC-AUC: {auc:.4f}  (GroupKFold on episode_id, {n_splits} folds)")
    return auc, X, y


def _load_harvest(directory: str, tag: str, max_records: int):
    path = _concat_shards(Path(directory))
    print(f"loading harvested states from {path} ...")
    rows, groups = _load_side(path, tag, max_records)
    print(f"  {len(rows)} rows / {len(set(groups))} episodes")
    return rows, groups


def run_il(args):
    sp_rows, sp_groups = _load_harvest(args.selfplay, "self", args.max_records)

    print(f"loading training states from {args.train} ...")
    tr_rows, tr_groups = _load_side(Path(args.train), "train", args.max_records)
    print(f"  {len(tr_rows)} rows / {len(set(tr_groups))} episodes")

    auc, X, y = _auc_between(tr_rows, tr_groups, sp_rows, sp_groups, args.folds,
                             shuffle_labels=args.shuffle_labels)

    if args.shuffle_labels:
        verdict = "PASS" if abs(auc - 0.5) < 0.05 else "FAIL — pipeline leaks, real result is invalid"
        print(f"label-shuffle sanity check: {verdict}")
        return

    if auc <= AUC_THRESHOLD:
        print(f"AUC <= {AUC_THRESHOLD}: the states IL trains on and the states it reaches are not "
              f"cleanly separable. Covariate shift of this kind is NOT the explanation for the IL "
              f"score gap — look elsewhere before spending more on the IL track.")
        return

    print(f"AUC > {AUC_THRESHOLD}: the two distributions ARE separable.")

    # The raw AUC on its own does NOT isolate imitation-learning covariate shift, and reading it
    # that way is the mistake this control exists to prevent. Harvested states differ from the
    # training corpus for at least three reasons at once: (1) the agent's own trajectory, which is
    # the hypothesis; (2) the opponents — harvesting plays the 6-agent local panel, the corpus came
    # from the real ladder field; (3) harvesting mechanics — the corpus logs both players, the
    # dump logs only one side. Only (1) is about IL.
    #
    # The control separates them: harvest a NON-IL agent against the identical panel and measure
    # its AUC against the same corpus. Everything except (1) is shared, so the *difference* between
    # the two AUCs is the part attributable to the IL policy's own trajectory.
    #
    # Measured 2026-08-09: IL (`il_agent_v2b`) 0.9786, control (`masamikobayashi_archaludon_
    # cinderace`) 0.9978 — the control is *more* separable. So the separability is driven by (2)
    # and (3), and IL's own trajectory is if anything closer to its training data than a strong
    # rule-based agent's is. That is evidence against covariate shift as the explanation for the IL
    # score gap, not for it.
    if args.control:
        print(f"\n=== control: {args.control} vs the same training corpus ===")
        ctl_rows, ctl_groups = _load_harvest(args.control, "ctl", args.max_records)
        ctl_auc, _, _ = _auc_between(tr_rows, tr_groups, ctl_rows, ctl_groups, args.folds,
                                     verbose=False)
        print(f"control out-of-fold ROC-AUC: {ctl_auc:.4f}   (IL: {auc:.4f})")
        delta = auc - ctl_auc
        print(f"IL minus control: {delta:+.4f}")
        if delta <= 0.0:
            print(
                "\nThe control agent's states are AT LEAST as separable from the training corpus\n"
                "as the IL agent's are. The separation is therefore explained by the shared\n"
                "differences — local panel vs real ladder field, and one-sided vs two-sided\n"
                "harvesting — not by the IL policy's own trajectory. IL-specific covariate shift is\n"
                "NOT supported by this evidence, and DAgger does not follow from it. Do not restart\n"
                "the IL track on the strength of the raw AUC above.")
            return
        print(f"\nIL states are {delta:.4f} more separable than the control's. That residual is the\n"
              f"part plausibly attributable to the IL policy's own trajectory; the branches below\n"
              f"address it. Judge them against the residual, not against the raw AUC.")
    else:
        print(
            "\nNO CONTROL WAS RUN (--control). This AUC alone cannot distinguish IL covariate shift\n"
            "from the local panel simply differing from the real ladder field. Re-run with a non-IL\n"
            "agent's harvest as --control before acting on anything below.")

    print("\ncomputing permutation importances (which features drift) ...")
    model = HistGradientBoostingClassifier(max_iter=200, max_depth=6,
                                           learning_rate=0.08, random_state=0)
    model.fit(X, y)
    sample = min(args.importance_sample, len(X))
    idx = np.random.default_rng(0).choice(len(X), sample, replace=False)
    imp = permutation_importance(model, X.iloc[idx], y[idx], n_repeats=5,
                                 random_state=0, scoring="roc_auc")
    order = np.argsort(imp.importances_mean)[::-1][:15]
    print(f"\n{'feature':<40} {'drop in AUC':>12} {'std':>8}")
    for i in order:
        print(f"{X.columns[i]:<40} {imp.importances_mean[i]:>12.4f} {imp.importances_std[i]:>8.4f}")

    print("""
Two actionable branches, in order of expected value for shift of *this* origin:

(b) DAgger-style aggregation — the correct fix. Roll out the current IL agent, collect the states
    it actually visits, relabel those states with the expert policy (here: the strongest
    rule-based agent, not the logged human/agent trace), and retrain on training ∪ relabelled.
    Iterate. This attacks the cause: the training distribution does not cover the agent's own
    trajectory. Dropping features cannot fix that.

(a) Drop the top drifted features — a mitigation, not a fix. It makes the model blind to the
    axes along which its own trajectory differs, which removes the symptom and some signal with
    it. Worth doing only as a cheap A/B against (b).

Before either: this AUC says the distributions differ, not that the difference is what costs
score. The falsifiable version is (b) — if a single DAgger round does not move local mu, the
covariate-shift hypothesis is wrong too and the IL track should stay frozen.""")


# ---------------------------------------------------------------------------
# roster representativeness
# ---------------------------------------------------------------------------


def run_roster(args):
    import ladder_eval as le

    panel_decks = {}
    for p in le.DEFAULT_PANEL:
        deck_csv = Path(p) / "deck.csv"
        if not deck_csv.exists():
            print(f"  (no deck.csv for {Path(p).name}, skipped)")
            continue
        ids = [int(x) for x in deck_csv.read_text().replace("\n", ",").split(",") if x.strip()]
        panel_decks[Path(p).name] = Counter(ids)

    episodes_dir = REPO_ROOT / "data" / "raw" / "episodes"
    files = sorted(episodes_dir.rglob("*.json"))[:args.max_episodes]
    if not files:
        raise SystemExit(f"no episode JSON under {episodes_dir}")

    field_decks = []
    for f in files:
        try:
            ep = json.loads(f.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        field_decks.extend(set(d) for d in _iter_decks(ep))

    if not field_decks:
        raise SystemExit("found episodes but no decks inside them; check the episode schema")

    panel_sets = {n: set(d) for n, d in panel_decks.items()}
    print(f"real field: {len(field_decks)} decks over {len(files)} episodes\n")

    # Jaccard to the *nearest* panel deck, per real deck. Deliberately not "share of field cards
    # the panel contains" — that metric rewards holding common staples (every deck runs the same
    # trainers) and would call an unrepresentative panel well-covered. What matters is whether any
    # panel member resembles a given real deck as a whole.
    nearest = []
    for fd in field_decks:
        best_name, best = None, 0.0
        for name, ps in panel_sets.items():
            j = len(fd & ps) / len(fd | ps)
            if j > best:
                best, best_name = j, name
        nearest.append((best, best_name))

    sims = sorted(s for s, _ in nearest)
    def pct(q):
        return sims[min(len(sims) - 1, int(q * len(sims)))]
    print("Jaccard similarity of each real deck to its nearest panel deck")
    print(f"  median {pct(0.50):.3f}   p10 {pct(0.10):.3f}   p90 {pct(0.90):.3f}   "
          f"max {sims[-1]:.3f}")

    for thresh in (0.30, 0.50):
        share = sum(1 for s in sims if s < thresh) / len(sims)
        print(f"  {share * 100:5.1f}% of the real field is <{thresh:.2f} similar to ANY panel deck")

    print(f"\n{'nearest panel deck':<40} {'share of real field':>20}")
    counts = Counter(n for _, n in nearest if n)
    for name, c in counts.most_common():
        print(f"{name:<40} {c / len(nearest) * 100:>19.1f}%")
    unmatched = sum(1 for _, n in nearest if n is None)
    if unmatched:
        print(f"{'(no overlap at all)':<40} {unmatched / len(nearest) * 100:>19.1f}%")

    print("\nRead this as the ceiling on what local mu can tell you: the panel is a 7-deck sample "
          "of a much wider field, and every archetype it does not resemble is one that local "
          "evaluation never tests a candidate against.")


def _iter_decks(ep):
    """Both players' 60-card decks, from `steps[0][0].visualize[0].action` — verified against the
    real episode dumps in `data/raw/episodes`. Yields nothing rather than raising on an episode
    that doesn't match, since the dumps include some truncated/errored games."""
    try:
        decks = ep["steps"][0][0]["visualize"][0]["action"]
    except (KeyError, IndexError, TypeError):
        return
    if not isinstance(decks, list):
        return
    for deck in decks:
        if isinstance(deck, list) and len(deck) == 60 and all(isinstance(x, int) for x in deck):
            yield deck


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=["il", "roster"], required=True)
    ap.add_argument("--train", default="data/processed/il_records.jsonl")
    ap.add_argument("--selfplay", default="data/processed/selfplay")
    ap.add_argument("--control",
                    help="dump dir for a NON-IL agent harvested against the same panel. Without "
                         "it the headline AUC cannot be attributed to IL covariate shift at all.")
    ap.add_argument("--max-records", type=int, default=4000,
                    help="raw JSONL records per class (default 4000)")
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--shuffle-labels", action="store_true",
                    help="sanity check: AUC must collapse to ~0.50")
    ap.add_argument("--importance-sample", type=int, default=20000)
    ap.add_argument("--max-episodes", type=int, default=400)
    args = ap.parse_args()

    if args.mode == "il":
        run_il(args)
    else:
        run_roster(args)


if __name__ == "__main__":
    main()
