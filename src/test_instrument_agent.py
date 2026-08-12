"""Tests for `src/instrument_agent.py`.

Run: python3 src/test_instrument_agent.py

Follows `test_trueskill_lite.py`'s convention: a plain script, no pytest, each numeric claim
checked against something derived independently of the implementation under test.

The important test is `test_counts_swallowed_exception`. The whole point of this module is to
measure failures the agent hides from us — an exception that escapes is trivially observable, an
exception the agent catches and turns into a degraded-but-legal move is not, and it is the second
kind that cost this project real ladder points twice.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from instrument_agent import Counters, legal_fallback, wrap_agent  # noqa: E402

FAILURES = []


def check(name: str, condition: bool, detail: str = ""):
    status = "ok" if condition else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))
    if not condition:
        FAILURES.append(name)


def _obs(n_options=3, min_count=1, max_count=1):
    return {"select": {"option": list(range(n_options)), "minCount": min_count, "maxCount": max_count}}


def test_legal_fallback():
    print("legal_fallback returns a selection the engine would accept")
    check("deck phase returns None marker", legal_fallback({"select": None}) is None)
    check("picks minCount options", legal_fallback(_obs(5, 2, 3)) == [0, 1])
    check("clips to n options", legal_fallback(_obs(1, 2, 3)) == [0])
    check("empty when maxCount is 0", legal_fallback(_obs(3, 0, 0)) == [])


def test_counts_escaping_exception():
    print("an exception that escapes the agent is counted and does not crash the battle")
    counters = Counters()

    def always_raises(obs_dict):
        raise RuntimeError("boom")

    wrapped = wrap_agent(always_raises, counters)
    out = wrapped(_obs())
    check("returned a legal selection", out == [0], f"got {out!r}")
    check("escaping exception counted", counters.escaped == 1, f"got {counters.escaped}")
    check("decision counted", counters.decisions == 1, f"got {counters.decisions}")


def test_counts_swallowed_exception():
    print("an exception the agent catches internally is still counted")
    counters = Counters()

    def swallows(obs_dict):
        try:
            raise ValueError("scoring blew up")
        except ValueError:
            pass
        return [0]

    wrapped = wrap_agent(swallows, counters)
    out = wrapped(_obs())
    check("returned the agent's own answer", out == [0], f"got {out!r}")
    check("nothing escaped", counters.escaped == 0, f"got {counters.escaped}")
    check("swallowed exception counted", counters.swallowed == 1, f"got {counters.swallowed}")
    sites = list(counters.raise_sites)
    check("raise site recorded", len(sites) == 1, f"got {sites}")
    check(
        "raise site points at this test file",
        sites and sites[0][0].endswith("test_instrument_agent.py"),
        f"got {sites}",
    )


def test_clean_agent_reports_zero():
    print("an agent that never raises reports no failures")
    counters = Counters()
    wrapped = wrap_agent(lambda obs_dict: [0], counters)
    for _ in range(50):
        wrapped(_obs())
    check("50 decisions counted", counters.decisions == 50, f"got {counters.decisions}")
    check("no escapes", counters.escaped == 0, f"got {counters.escaped}")
    check("no swallowed exceptions", counters.swallowed == 0, f"got {counters.swallowed}")
    check("latencies recorded", len(counters.latencies_ms) == 50, f"got {len(counters.latencies_ms)}")


def test_generator_exhaustion_is_not_a_failure():
    """Regression: the first version of this module counted StopIteration.

    Every `any(...)`/`sum(...)` over a generator raises StopIteration to signal exhaustion, so an
    agent built out of generator expressions — which our Archaludon agent is — reported a 39%
    "swallowed exception" rate whose top three sites were ordinary comprehensions. Anything that
    flags a clean agent as broken 39% of the time is worse than no measurement at all.
    """
    print("ordinary generator exhaustion is not counted as a failure")
    counters = Counters()

    def genexp_heavy(obs_dict):
        options = obs_dict["select"]["option"]
        if any(o > 100 for o in options) or sum(1 for o in options if o < 0):
            return [0]
        return [0]

    wrapped = wrap_agent(genexp_heavy, counters)
    for _ in range(20):
        wrapped(_obs())
    check("20 decisions counted", counters.decisions == 20, f"got {counters.decisions}")
    check("no swallowed exceptions", counters.swallowed == 0, f"got {counters.swallowed}")
    check("no raise sites", not counters.raise_sites, f"got {counters.raise_sites}")


def test_raise_site_is_the_raising_line_not_the_function():
    """The site must name the line that raised, not the enclosing `def`.

    A 1,100-line agent has few functions and dozens of raise sites; reporting `co_firstlineno`
    collapses them all onto a handful of useless lines.
    """
    print("raise site resolves to the raising line")
    counters = Counters()

    def raises_deep_inside(obs_dict):          # noqa: ANN001
        filler = 1                              # noqa: F841
        try:
            raise KeyError("missing")           # <- this line
        except KeyError:
            pass
        return [0]

    expected_line = raises_deep_inside.__code__.co_firstlineno + 3
    wrapped = wrap_agent(raises_deep_inside, counters)
    wrapped(_obs())
    sites = list(counters.raise_sites)
    check("one site", len(sites) == 1, f"got {sites}")
    check(
        "line is the raise, not the def",
        sites and sites[0][1] == expected_line,
        f"got {sites[0][1] if sites else None}, expected {expected_line}",
    )


def test_counters_merge():
    print("per-process counters sum without losing raise sites")
    a, b = Counters(), Counters()
    a.decisions, a.escaped, a.swallowed = 10, 1, 2
    a.raise_sites[("f.py", 3)] = 2
    a.latencies_ms.append(1.0)
    b.decisions, b.escaped, b.swallowed = 5, 0, 3
    b.raise_sites[("f.py", 3)] = 1
    b.raise_sites[("g.py", 9)] = 3
    b.latencies_ms.append(2.0)
    a.merge(b)
    check("decisions summed", a.decisions == 15, f"got {a.decisions}")
    check("escaped summed", a.escaped == 1, f"got {a.escaped}")
    check("swallowed summed", a.swallowed == 5, f"got {a.swallowed}")
    check("shared site summed", a.raise_sites[("f.py", 3)] == 3, f"got {a.raise_sites}")
    check("new site carried over", a.raise_sites[("g.py", 9)] == 3, f"got {a.raise_sites}")
    check("latencies concatenated", a.latencies_ms == [1.0, 2.0], f"got {a.latencies_ms}")


def test_percentile_matches_manual_sort():
    print("percentile is derived independently, not memorised")
    from instrument_agent import percentile

    values = [5.0, 1.0, 3.0, 2.0, 4.0]
    ordered = sorted(values)
    check("p0 is the minimum", percentile(values, 0) == ordered[0])
    check("p100 is the maximum", percentile(values, 100) == ordered[-1])
    check("p50 of 5 values is the middle one", percentile(values, 50) == ordered[2])
    check("empty input is 0.0", percentile([], 50) == 0.0)


if __name__ == "__main__":
    for fn in (
        test_legal_fallback,
        test_counts_escaping_exception,
        test_counts_swallowed_exception,
        test_clean_agent_reports_zero,
        test_generator_exhaustion_is_not_a_failure,
        test_raise_site_is_the_raising_line_not_the_function,
        test_counters_merge,
        test_percentile_matches_manual_sort,
    ):
        fn()
        print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURES: {FAILURES}")
        sys.exit(1)
    print("all tests passed")
