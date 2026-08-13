# Provenance

Source: public Kaggle kernel `aristophanivan/multiply-agent-best-940-lb` ("Algorithm: 03
MultiPly Beam Search Agent"), pulled to
`notebooks/kaggle-research/pulled/aristophanivan__multiply-agent-best-940-lb/multiply-agent-best-940-lb.ipynb`.

Cleared under the 2026-08-13 third-party code decision: agents derived from public Kaggle
kernels may be submitted.

Notebook cell 2 is a `%%writefile main.py` cell (24,246 chars raw / 24,226 after stripping
the magic line); this directory's `main.py` is that cell's body extracted verbatim, no other
transformation. `deck.csv` is the 60-card `DECK` list from cell 1, written one ID per line.

Discrepancy worth flagging: the notebook's own markdown (cell 0) describes this as "a
strictly heuristic agent," but `main.py` imports `search_begin`/`search_step` from `cg.api` —
the same real forward-search primitives `archaludon_search`'s PIMC layer uses. This makes it
architecturally a search agent, not a pure heuristic, contrary to its own description. A
third architecturally-distinct candidate in the roster (alongside `archaludon_search`'s PIMC
and `jazivxt_alakazam`'s 2-ply minimax).

Claimed by kernel title: "940 LB". Never forked or measured locally before this extraction.
Never uploaded to the real ladder under this repo.
