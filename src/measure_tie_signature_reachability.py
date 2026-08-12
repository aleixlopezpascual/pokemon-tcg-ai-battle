"""Lever L5, Step 0 — measure genuine tie reachability BEFORE writing any dataset builder or
training pipeline.

Context: L0 (class-score edit, Task 5) and L0b (deterministic within-class tiebreak, Task 6)
both FAILED the reachability gate. Task 6's root-cause found that `audit_main_decisions.py`'s
`tie_report` counts ties by option *type* only, so its raw within-class tie counts (ATTACH 4248,
PLAY 4149 of 79,041 MAIN decisions; 206/5000 and 182/5000 on the plain 5,000-state sample this
script also uses) overstate how many ties are actually resolvable -- most are duplicate options
that are indifferent *by construction* (same card, same target). Once deduped by real identity
(`features._option_signature`), only 78/206 ATTACH ties and 28/182 PLAY ties were genuinely
distinct.

L5's plan-table pitch is to drop the class prior and train an option-level tiebreaker on tied
sets, deduped by `_option_signature` so indifferent-by-construction ties are never counted as
reachable. This script measures -- across ALL option classes, not just the already-thin
ATTACH/PLAY pair -- whether that deduped tie pool is even large enough (>=5% of examined states,
the same floor L0/L0b were held to) to be worth building a model for. Pure measurement: no
dataset builder, no model, reuses `audit_main_decisions.score_probe`/`_load_module` and
`features.option_features`/`_option_signature` rather than reimplementing any of it.
"""
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_main_decisions as audit  # noqa: E402
import features as feat  # noqa: E402

STATES_GLOB = "data/processed/selfplay_crustle/shard_*.jsonl"
BASE_AGENT_DIR = Path("submissions/soutasakurai_libraryout_crustle")
OUT_JSON = Path("data/processed/instrumentation/tie_signature_reachability.json")
LIMIT = 5000

# Same OPT_* constants features.py itself uses (copied from cg/api.py's own enum).
OPT_NAMES = {
    feat.OPT_NUMBER: "NUMBER",
    feat.OPT_CARD: "CARD",
    feat.OPT_TOOL_CARD: "TOOL_CARD",
    feat.OPT_ENERGY_CARD: "ENERGY_CARD",
    feat.OPT_ENERGY: "ENERGY",
    feat.OPT_PLAY: "PLAY",
    feat.OPT_ATTACH: "ATTACH",
    feat.OPT_EVOLVE: "EVOLVE",
    feat.OPT_ABILITY: "ABILITY",
    feat.OPT_DISCARD: "DISCARD",
    feat.OPT_RETREAT: "RETREAT",
    feat.OPT_ATTACK: "ATTACK",
    feat.OPT_END: "END",
}


def _type_name(t):
    return OPT_NAMES.get(t, str(t))


def load_states(limit):
    """Same pattern as test_prior_identity.py's load_states: rebuild the minimal obs dict from
    the dumped shards, skip null-select records, cap at `limit`."""
    out = []
    for shard in sorted(Path(".").glob(STATES_GLOB)):
        with shard.open() as f:
            for line in f:
                rec = json.loads(line)
                if rec.get("select") is None:
                    continue
                out.append({"select": rec["select"], "current": rec["current"], "logs": []})
                if len(out) >= limit:
                    return out
    return out


def main() -> int:
    states = load_states(LIMIT)
    print(f"loaded {len(states)} states from {STATES_GLOB}")
    if len(states) < 500:
        print(f"SKIP: only {len(states)} dumped states; run ladder_eval --dump-states first")
        return 1

    agent_fn, module = audit._load_module(BASE_AGENT_DIR)

    card_data = feat.load_card_data()
    attack_data = feat.load_attack_data()
    card_attrs = feat.load_card_attrs()

    examined = len(states)
    degraded = 0
    no_tie = 0
    tie_but_indistinct = 0
    tie_and_distinct = 0

    # tie_and_distinct broken down by which option type(s) are present in the *distinct* groups
    # (not just the raw tied_idx types) -- within_class keyed by the single OPT_* type, cross_class
    # keyed by a sorted tuple of the types involved.
    within_class_counts = Counter()
    cross_class_counts = Counter()
    cross_class_total = 0

    chosen_matches_lowest = 0
    chosen_checked = 0

    for state in states:
        select = state["select"]
        current = state["current"]
        options = select.get("option") or []

        with audit.score_probe(module) as captured:
            chosen = agent_fn(state)

        if not captured:
            degraded += 1
            continue

        scores = captured[-1]
        if not scores:
            no_tie += 1
            continue

        top = max(scores)
        tied_idx = [i for i, s in enumerate(scores) if s == top]

        if len(tied_idx) < 2:
            no_tie += 1
            continue

        g = feat.global_features(select, current)
        rows = {
            i: feat.option_features(options[i], select, current, card_data, attack_data, card_attrs, g)
            for i in tied_idx
        }

        sig_groups = {}
        for i in tied_idx:
            sig = feat._option_signature(rows[i], i)
            sig_groups.setdefault(sig, []).append(i)

        if len(sig_groups) < 2:
            tie_but_indistinct += 1
            continue

        tie_and_distinct += 1
        types_in_tie = sorted({options[i].get("type") for i in tied_idx})
        if len(types_in_tie) == 1:
            within_class_counts[types_in_tie[0]] += 1
        else:
            cross_class_total += 1
            cross_class_counts[tuple(types_in_tie)] += 1

        # Sanity check (Step 2.7): the base's stable sort should pick the lowest index among the
        # tied options -- confirm chosen[0] agrees, since that's the "reachable" baseline any
        # tiebreaker on this pool would have to beat.
        if chosen:
            chosen_checked += 1
            if chosen[0] == min(tied_idx):
                chosen_matches_lowest += 1

    reachability_pct = 100.0 * tie_and_distinct / examined if examined else 0.0
    floor_pct = 5.0
    verdict = "PASS" if reachability_pct >= floor_pct else "FAIL"

    within_class_named = {_type_name(t): c for t, c in sorted(within_class_counts.items())}
    cross_class_named = {
        "+".join(_type_name(t) for t in combo): c
        for combo, c in sorted(cross_class_counts.items(), key=lambda kv: -kv[1])
    }

    result = {
        "examined": examined,
        "degraded": degraded,
        "no_tie": no_tie,
        "tie_but_indistinct": tie_but_indistinct,
        "tie_and_distinct": tie_and_distinct,
        "tie_and_distinct_pct_of_examined": reachability_pct,
        "reachability_floor_pct": floor_pct,
        "verdict": verdict,
        "tie_and_distinct_within_class": within_class_named,
        "tie_and_distinct_cross_class": cross_class_named,
        "cross_class_total": cross_class_total,
        "chosen_matches_lowest_tied_index": {
            "checked": chosen_checked,
            "matches": chosen_matches_lowest,
        },
    }

    print(f"\nexamined:            {examined}")
    print(f"degraded:            {degraded}")
    print(f"no_tie:              {no_tie}")
    print(f"tie_but_indistinct:  {tie_but_indistinct}")
    print(f"tie_and_distinct:    {tie_and_distinct}")
    print(f"tie_and_distinct / examined: {reachability_pct:.2f}%  (floor: {floor_pct:.1f}%)")
    print(f"VERDICT: {verdict}")
    print("\ntie_and_distinct within-class breakdown:")
    for name, c in sorted(within_class_named.items(), key=lambda kv: -kv[1]):
        print(f"  {name}: {c}")
    print(f"\ntie_and_distinct cross-class total: {cross_class_total}")
    for name, c in cross_class_named.items():
        print(f"  {name}: {c}")
    print(f"\nchosen[0] matches lowest tied index: {chosen_matches_lowest}/{chosen_checked}")

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2))
    print(f"\nwrote {OUT_JSON}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
