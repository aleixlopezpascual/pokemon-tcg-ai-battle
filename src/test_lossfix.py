"""Tests pinning submissions/archaludon_lossfix/main.py's base-heuristic fixes.

Run: python3 src/test_lossfix.py

Each fix gets a captured-obs fixture (a single MAIN-decision obs_dict, saved as JSON under
data/processed/instrumentation/lossfix_fixtures/<name>.json) and a before/after assertion on
score_option's or a named sub-scorer's return value. Skips cleanly when the candidate or a
fixture is absent (both are gitignored)."""

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FAILURES = []
SKIPPED = []


def check(name, condition, detail=""):
    if condition:
        print(f"  ok    {name}")
    else:
        print(f"  FAIL  {name}   {detail}")
        FAILURES.append(name)


def skip(name, why):
    print(f"  skip  {name}   ({why})")
    SKIPPED.append(name)


def _load_candidate(dirname="archaludon_lossfix"):
    agent_dir = REPO_ROOT / "submissions" / dirname
    main_py = agent_dir / "main.py"
    if not main_py.exists():
        return None
    engine_dir = REPO_ROOT / "data" / "raw" / "sample_submission" / "sample_submission"
    if not (engine_dir / "cg").is_dir():
        return None
    for p in (str(engine_dir), str(agent_dir)):
        if p not in sys.path:
            sys.path.insert(0, p)
    spec = importlib.util.spec_from_file_location("lossfix_under_test", main_py)
    module = importlib.util.module_from_spec(spec)
    sys.modules["lossfix_under_test"] = module
    spec.loader.exec_module(module)
    return module


def load_fixture(name):
    path = REPO_ROOT / "data" / "processed" / "instrumentation" / "lossfix_fixtures" / name
    if not path.exists():
        return None
    return json.loads(path.read_text())


def main():
    m = _load_candidate()
    if m is None:
        skip("all lossfix tests", "submissions/archaludon_lossfix not present locally")
    else:
        run_all_tests(m)
    print(f"\n{len(FAILURES)} failed, {len(SKIPPED)} skipped")
    if FAILURES:
        sys.exit(1)


def test_lillie_shuffle_energy(m):
    """Worklist #1 (crustle, turn 4, gap 2.0): chosen_option=3 (PLAY Lillie's Determination)
    outranked best_alt_option=2 (ATTACH Metal Energy to a bench Pokemon).

    Lillie's Determination shuffles the whole hand into the deck (see the pre-existing,
    Crustle-only, and itself-buggy "Crustle: Lillie OK (no energy in hand)" guard in
    apply_overrides — its has_metal=True branch falls through with no override at all). That
    hazard -- losing an unattached Metal Energy card sitting in hand -- is not Crustle-specific;
    it applies against every opponent, since attaching first costs nothing (Lillie can still be
    played immediately afterward in the same turn once the energy is out of hand). score_play's
    generic LILLIE branch never checked for this, so playing Lillie scored 5000 unconditionally
    while attaching the loose Metal Energy scored only 2200 -- a real, generalizable heuristic
    bug, not oracle noise (detect_matchup even returns "generic" at this turn, so the existing
    Crustle-only guard was never reachable here in the first place)."""
    fixture = load_fixture("crustle_turn4.json")
    if fixture is None:
        skip("lillie_shuffle_energy", "fixture not captured")
        return
    obs = m.to_observation_class(fixture)
    chosen_opt = obs.select.option[3]
    alt_opt = obs.select.option[2]
    score, reason = m.score_option(obs, chosen_opt)
    alt_score, _ = m.score_option(obs, alt_opt)
    check("lillie_shuffle_energy no longer over-scores the blunder option",
          score < alt_score, f"got score={score} reason={reason!r} alt_score={alt_score}")


def test_hero_cape_bench_duraludon(m):
    """Worklist #2 (crustle, turn 6, gap 2.0): chosen_option=5 (ATTACH Hero's Cape to a
    fully-energized BENCH Duraludon) outranked best_alt_option=6 (END turn).

    Two compounding bugs, both real and both generalizable past this one archetype:

    1. `score_attach`'s HERO_CAPE branch grants its +8000 "Hero's Cape on Duraludon" bonus for
       any Duraludon target with >=1 energy, without checking whether the target is the ACTIVE
       Pokemon (the one actually taking damage / attacking) or a benched one that isn't exposed
       yet -- a missing case, not archetype-specific.
    2. `apply_overrides`'s Crustle-only "Crustle: bench Duraludon energy priority" ATTACH bonus
       (+10000) fires for *any* card attached to a bench Duraludon, even though its own reason
       string says "energy priority" -- it never checks `cid == METAL_ENERGY`, so it also boosts
       an unrelated Tool card (Hero's Cape) by the same +10000, compounding bug 1.

    Together these turned a should-be-saved Hero's Cape (better held for when a Pokemon is
    actually active/exposed) into an 18000-scoring "priority" play, beating END turn (0)."""
    fixture = load_fixture("crustle_turn6.json")
    if fixture is None:
        skip("hero_cape_bench_duraludon", "fixture not captured")
        return
    obs = m.to_observation_class(fixture)
    chosen_opt = obs.select.option[5]
    alt_opt = obs.select.option[6]
    score, reason = m.score_option(obs, chosen_opt)
    alt_score, _ = m.score_option(obs, alt_opt)
    check("hero_cape_bench_duraludon no longer over-scores the blunder option",
          score < alt_score, f"got score={score} reason={reason!r} alt_score={alt_score}")


def test_lillie_boss_paralysis(m):
    """Worklist #4 (crustle, turn 10, gap 2.0): chosen_option=5 (ATTACK now, score 220)
    outranked best_alt_option=1 (PLAY Lillie's Determination, score -500).

    score_play's LILLIE branch deferred to Boss's Orders on the bare combination of "Boss is in
    hand" and "an attacker is ready" (`BOSS in ids and planned_archaludon_attacks(obs)`), without
    checking whether Boss would actually do anything this turn. In this fixture Boss's own branch
    independently scores itself -500 ("save Boss: can KO Active" -- no lethal target this turn),
    yet Lillie's guard fired anyway on the same board state, so *neither* supporter got played:
    a "supporter paralysis" missing-case bug, not archetype-specific. Gated the guard on
    `_boss_has_lethal(obs)` -- the same lethal-only conditions Boss's own scorer uses to return
    20000/"LETHAL Boss" -- so Lillie is only held back when Boss would genuinely be worth playing
    instead."""
    fixture = load_fixture("crustle_turn10.json")
    if fixture is None:
        skip("lillie_boss_paralysis", "fixture not captured")
        return
    obs = m.to_observation_class(fixture)
    chosen_opt = obs.select.option[5]
    alt_opt = obs.select.option[1]
    score, reason = m.score_option(obs, chosen_opt)
    alt_score, _ = m.score_option(obs, alt_opt)
    check("lillie_boss_paralysis no longer over-scores the blunder option",
          score < alt_score, f"got score={score} reason={reason!r} alt_score={alt_score}")


def run_all_tests(m):
    test_lillie_shuffle_energy(m)
    test_hero_cape_bench_duraludon(m)
    test_lillie_boss_paralysis(m)


if __name__ == "__main__":
    main()
