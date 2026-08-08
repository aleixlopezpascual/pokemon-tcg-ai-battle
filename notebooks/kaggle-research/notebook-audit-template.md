# Notebook audit template

Copy the block below once per audited kernel. Keep filled entries in this same file, newest
first, so `10-day-plan.md` Day-2 synthesis can scan them in one pass.

```markdown
### <ref> — <title>

- **Author / votes / last run**: <author>, <totalVotes>, <lastRunTime>
- **Approach type**: rule-based | RL/MCTS | meta-analysis | anti-meta/matchup | tooling
- **Deck archetype targeted**: <e.g. Mega Lucario ex, Crustle, Dragapult ex, Alakazam>
- **Win-rate / LB claim**: <what the author claims, and against what opponent — a claim
  against a named bot (e.g. "beats the Day-1 Crustle bot") is more useful than a vague
  aggregate number>
- **Verified locally?**: not yet | yes via run-battle (<result>) | no — couldn't reproduce
- **Local-sim-vs-ladder red flag**: <does this kernel's approach look like it could be
  overfit to the local simulator's opponent pool rather than the real hidden ladder? e.g.
  hardcoded counters to one specific bot, no matchup diversity in its own testing>
- **Reusable idea for this repo**: <the one thing worth carrying into src/ or submissions/ —
  a heuristic, a deck list, a data structure, an insight about the meta. Be specific about
  *where* it would slot in.>
- **Skip reason (if not fully audited)**: <e.g. "tooling only, no strategy content" — per
  prioritization-matrix.md's dedup rule, so it's clear this was a deliberate choice>
```

## Filled entries

### masamikobayashi/a-sample-archaludon-75-wr-vs-my-1300-starmie — A Sample Archaludon: 75% WR vs my 1300+ Starmie

- **Author / votes / last run**: masamikobayashi, 96 votes, 2026-08-06
- **Approach type**: rule-based, matchup-tuned (Crustle, Alakazam, Hop, Lucario-specific logic; v2/v5/v6 changelog shows real iteration — grid-searched HP thresholds, prize-race-aware heal lines)
- **Deck archetype targeted**: Archaludon ex / Cinderace / Duraludon / Relicanth — inspired by a real tournament 2nd-place decklist (City League 2026 Season 4, linked in the notebook)
- **Win-rate / LB claim**: 74.4% WR over 1000 games — but explicitly **against the author's own Starmie/Froslass agent only**, not the ladder or a diverse field. Author states this may not generalize to other Starmie builds (Cinderace-based, Dusknoir Bomb). **No ladder μ of its own** — the author deliberately never submitted this agent (didn't want to burn a Final slot; their real "1300+" is a *different*, unshared Starmie/Froslass build).
- **Verified locally?**: yes via run-battle — 70% WR over 20 games vs our own submitted Lucario baseline (real ladder-scored at 439.9-450.9 μ), and 10/10 vs the bundled random baseline.
- **Local-sim-vs-ladder red flag**: the 74.4% claim is a single fixed matchup (vs one opponent's Starmie), not a diverse field — treat as "plausible signal," not a ladder guarantee. Our own local test used a different opponent (Lucario) and got a different but still-positive number (70%), which is at least *some* cross-opponent evidence.
- **Reusable idea for this repo**: **this became our working baseline** (`submissions/masamikobayashi_archaludon_cinderace/`) — fully self-contained main.py + deck.csv (no external dataset dependency, unlike the Kiyota Lucario sample), already handles the `exec()`-without-`__file__` Kaggle sandbox quirk correctly (`try: ROOT = __file__ / except NameError: ROOT = None`) — exactly the bug class that broke our first submission.
- **Cross-validation**: Archaludon ex + Cinderace independently identified as the strongest known archetype by `pulled/TomBombadyl__kaggle_pokemon/` (their real ladder testing: 1196.1-1224.2 μ, at/above the live leaderboard top at the time). Two independent sources, same archetype conclusion.

### masamikobayashi/prize-card-tracking-1300-starmie — Gold Medal Starmie: Prize Card Tracking

- **Author / votes / last run**: masamikobayashi, 51 votes, 2026-08-06
- **Approach type**: write-up + one reusable component (`PrizeTracker` class), not a full agent
- **Deck archetype targeted**: Starmie / Froslass (based on ashleysandlin's Limitless tournament list — same real-world decklist TomBombadyl's repo also references, which scored only 277.5 μ in *their* implementation — strong evidence that **pilot/agent quality dominates deck choice**, not just deck choice alone)
- **Win-rate / LB claim**: "Gold Medal range" — no full main.py shared, so unverifiable directly, but the architecture write-up (generic mode + matchup-specific modes + a Forward-Search "Finish mode" that verifies lethal lines) reads as substantially more sophisticated than the Archaludon sample.
- **Verified locally?**: not possible — full agent code not shared, only the `PrizeTracker` helper class.
- **Local-sim-vs-ladder red flag**: n/a — no local testing possible without the full agent.
- **Reusable idea for this repo**: the shared `PrizeTracker` class (imperfect-information deck-inference: subtracts every visible card from the known decklist, treats the remainder as prized only when the count exactly matches `len(player.prize)`, explicitly handles the "in-flight effect card" edge case via `obs.select.effect`). Directly reusable once we build search-based logic — freely shared by the author ("I hope it helps others... if you know a better implementation, please share it").
- **Skip reason (if not fully audited)**: no full agent to audit — write-up + one component only.

### aristophanivan/probablity-v2 (sibling: multiply-agent-best-940-lb) — Algorithm: 03 MultiPly Beam Search Agent

- **Author / votes / last run**: aristophanivan, 70-87 votes across the two sibling notebooks, last run 2026-06-24 (~6 weeks stale as of 2026-08-08).
- **Approach type**: rule-based scorer (`AdvancedPolicy`, Mega Lucario ex / Mega Abomasnow ex / Hariyama hybrid deck) **plus a real determinized search layer** — calls `cg.api.search_begin/search_step/search_end/search_release` directly. Confirmed these are genuine, officially-documented engine functions (checked against the real `cg/api.py`, not guessed): you supply your own *guess* at the opponent's hidden hand/deck/prizes/active (via `get_search_kwargs`'s random sampling), and the engine simulates forward from that determinized world. This is architecturally different from anything else in this repo (pure heuristics or supervised IL) and from the "naive MCTS" that `discussion-intel-report.md`'s #717697 finding says was abandoned here — that finding was likely about ignoring the imperfect-information problem, not about using the engine's own determinization-based search primitive.
- **Win-rate / LB claim**: `probablity-v2`'s Code-tab score badge shows **933.8**; the sibling `multiply-agent-best-940-lb` self-reports "Best: 940 LB" in its title. Same caveat as every other Code-tab badge logged here — likely the author's current overall account score, not proof this exact code produces it — but the two independent numbers (badge + title) are at least mutually consistent, and both are real above anything we've achieved (best real score to date: Archaludon 811.4 peak, ~750-775 settled).
- **Verified locally?**: **yes.** Built `submissions/aristophanivan_probablity_v2/` (extracted from the notebook's `%%writefile main.py` cell, standard `cg/` engine copied in, no path guards needed beyond what was already present). Runs clean, reasonable speed (`SEARCH_TIME_BUDGET = 2.6` s/decision, well inside the 600s/game budget). `local_eval.py --battles 20 --repeats 3` (360 games total, all matchups Wilson-CI-stable): pooled **59.7% [54.6, 64.7]**. Per-matchup: crushes weak/generic opponents (100% vs random, 93.3% vs our frozen IL agent, 68.3% vs Lucario) but **loses to every one of our strongest local candidates** — 28.3% vs hardened Archaludon, 36.7% vs the Crustle mill deck, 31.7% vs the newly-added Alakazam/Dunsparce complement.
- **Local-sim-vs-ladder red flag**: real one, and it cuts both ways here. It doesn't currently beat what we already have locally, but this project has independently and repeatedly found local win rate unreliable for ranking comparable-strength candidates (`baseline-comparison.md`'s calibration table) — so "loses locally to Archaludon" doesn't rule out a good real score, it just means the local evidence alone doesn't justify a submission yet.
- **Reusable idea for this repo**: added to `local_eval.py`'s default opponent roster permanently (`submissions/aristophanivan_probablity_v2/`). The determinized-search technique itself (`search_begin`/`search_step`) is a genuinely unexplored axis worth a deeper look if rule-based tuning plateaus — not pursued further this session beyond building/testing the existing code as-is.

### Byte-identical duplicate found: a locally-downloaded "meta-snapshot-06-29.ipynb" == biohack44/pok-mon-tcg-ai-battle-meta-snapshot-07-july

- User supplied a raw `.ipynb` file downloaded from Kaggle (no kernel/author metadata attached), citing a claimed "1054.1 public score, ~1 month old." Before building anything, statically parsed the embedded `AGENT_PAYLOADS` JSON blob via Python's `ast` module (no code execution — same caution as the discarded `tetsutani` notebook) and SHA256-compared both profiles' `main_py`/`deck_csv` against the already-pulled `biohack44__pok-mon-tcg-ai-battle-meta-snapshot-07-july` notebook: **100% byte-identical**, both Profile A (`flex_archaludon_0018_minus1182_plus1213`) and Profile B (`flex_alakazam_dunsparce_0000_seed`).
- Profile A was already real-submitted by us (ref `55309000`) at **682.0/694.4** — below current hardened Archaludon (711-811). No value in re-adding it.
- Profile B (Alakazam/Dunsparce complement) had never been built/tested before. Built `submissions/biohack44_alakazam_dunsparce/`, runs clean, added to `local_eval.py`'s roster. Weak early signal (25% in a 4-battle smoke test; 31.7% in the bigger 60-game run above, as the opponent for the `probablity-v2` evaluation) — consistent with this same notebook's own embedded field data ranking `alakazam_dunsparce` below `archaludon` (51.3% vs 62.2% score rate over real large samples).
- **Cross-reference worth keeping in mind**: `lucifer19/battlecore-compact-agent` (also ships an Archaludon-metal-tempo / Alakazam-Dunsparce A/B pair) independently cites a **"600→1054 μ range for the same submission"** when discussing score volatility — the "1054" the user saw for this build is plausibly a real, if unstable, early reading for this same underlying `flex_archaludon_0018_minus1182_plus1213` code, consistent with this project's own documented finding that same-agent resubmissions can land 300+ points apart. It does not change the recommendation (our own real, settled reading for this exact build is 682-694, and we already have a better-performing hardened variant).
- **Lesson reinforced**: static-AST-extraction-and-hash-compare is now a proven, safe, cheap way to de-duplicate "new" notebook submissions against everything already pulled, before spending any build/test effort on them.

### makthanithin/pokemon-tcg-ai-battle-1084-5-baseline — Simple Baseline + Matchup Tests

- **Author / votes / last run**: makthanithin (kernel slug), 26 votes
- **Approach type**: rule-based, Mega Lucario ex, with a small Crustle-specific guard
- **Win-rate / LB claim**: "1084.5 Baseline" (title); includes real local matchup-test data (e.g. a Crustle confirmation run: 47/100 win rate vs a named opponent `harukiharada_crustle`)
- **Verified locally?**: not yet — pulled, not yet built/tested
- **Reusable idea for this repo**: **adopted its packaging-validation pattern** — after building `submission.tar.gz`, assert `{"main.py", "deck.csv", "cg/api.py", "cg/libcg.so"}` are all present before considering it submit-ready. Cheap check, catches a broken package before it burns a daily submission slot. Now used for our own packaging step.

### myso1987/ptcg-ai-battle-leaderboard-deck-meta-by-score-band — Leaderboard Deck Meta by Score Band

- **Author / votes**: myso1987, 68 votes
- **Approach type**: tooling — a live scraper (via the Kaggle API's `competition_team_submissions` + episode replay parsing) that classifies real leaderboard teams' decks into archetypes, stratified by score band, and charts archetype prevalence per band
- **Verified locally?**: not run — a multi-hour job (full-leaderboard mode) or a bounded stratified-sample mode (500 teams/band); requires internet + the competition's card-data CSV attached
- **Reusable idea for this repo**: this is the tool that would give a real, current "what's actually winning at the top score bands" answer, rather than inferring from a handful of self-reported kernel titles. Worth running once time allows (Day 8 late-meta check per `10-day-plan.md`) rather than day 1-2, since it's a heavier lift than the notebook audits.
- **Skip reason (if not fully audited)**: too expensive to run today given the more urgent submission-recovery work; noted for later.

### soutasakurai/max-elo-1208-libraryout-w-crustle-great-tusk — Max Elo: 1208, LibraryOut w/ Crustle & Great Tusk

- **Author / votes / last run**: soutasakurai, 10 votes, 2026-06-26
- **Approach type**: rule-based, but a totally different win condition — **library-out (deck-out/mill)** control via Great Tusk (primary "attacker" that doesn't really attack — mills instead), Dwebble/Crustle as a wall, Terrakion as backup
- **Win-rate / LB claim**: "Max Elo: 1208" in the title — **but the author explicitly discloses**: "The max Elo is scored by former submission. So the display on this page is different from the highest score... I developed this agent in consultation with ChatGPT, but it isn't fully functional yet." I.e. the 1208 is real but from a *different, earlier* submission — this exact shared code is not guaranteed to reproduce it, by the author's own admission.
- **Verified locally?**: **yes** — runs clean (no crash, despite the author's doubt), 10/10 vs random, **80% WR over 20 games vs our own submitted Archaludon baseline**, 95% vs the Lucario baseline. This is the strongest local result we've measured against a real (non-random) opponent, and notably against an opponent that's independently cross-validated as strong elsewhere.
- **Local-sim-vs-ladder red flag**: real one here — the deck's own stated weakness is "Lucario decks that have fully set up... prepared to counter Crustle," and self-decking risk from its own combo (Explorer's Guide accelerates the opponent's LO but also the agent's own). A narrow local test (vs our 2 other submissions only) can't surface this. Author's own uncertainty about functionality is a second-hand red flag worth taking seriously despite the good local numbers.
- **Reusable idea for this repo**: a genuinely different strategic axis (win-condition diversity, not just "which attacker deck") — worth testing as a real submission given the local result, but consciously as a higher-variance bet than Archaludon, not a safer one. Not yet submitted — pending a decision on spending one of the remaining daily slots on it (see `baseline-comparison.md`).

### llccqq624/ptcg-meta-a-stable-submit — PTCG Meta A Stable Submit

- **Author / votes**: llccqq624 (Jiachen Li), 31 votes
- **Approach type**: rule-based — **this is a byte-identical re-share of masamikobayashi's Archaludon ex/Cinderace `main.py`** (same 40947-char source), explicitly called out as "the stable `meta_a` Archaludon/Cinderace" pick by this author too.
- **Reusable idea for this repo**: not new code, but strong **independent confirmation** that Archaludon/Cinderace is the community-recognized stable top pick, not just one author's opinion. Also has a cleaner packaging cell (`py_compile.compile("main.py", doraise=True)` before packaging — a free syntax-error catch before wasting a submission — worth adopting).

### lucifer19/battlecore-compact-agent — PTCG AI Battle — Max-Efficiency Challenger Build (V4)

- **Author / votes**: lucifer19 (Krizsó Gergely), 27 votes
- **Approach type**: rule-based, ships **"Profile A — Archaludon Metal Tempo"** as primary (Profile B is an Alakazam/Dunsparce complement) — a 4th independent source landing on the same archetype.
- **Notable methodology** (unusually rigorous for a public kernel): ~20,000-game local arena with color-swapped pairs and Wilson 95% confidence intervals, a "sham-search placebo control" specifically built to detect *arena contamination* (i.e. checking whether their own local test harness was giving false positives), and an explicit leaderboard-volatility model asking "what field-relative strength rationalizes an observed 600→1054 μ range" for the same submission.
- **Reusable idea for this repo**: the placebo-control-for-arena-contamination idea is worth remembering if our own local `run-battle` results ever look too good to be true — it's a concrete way to sanity-check the test harness itself, not just the agent.
- **Skip reason (if not fully audited)**: payload is base64-encoded/compressed in the notebook ("byte-identical to benchmarked builds") — more effort to extract than value added, since it's another Archaludon variant and we already have a working one.

### nursrijan/pokemon-ai-battle-agent-mega-lucario, jazivxt/codex-sol-eclipse-alakazam

- Both rule-based, Lucario and Alakazam archetypes respectively, self-contained and packageable. Not yet built/tested locally — lower priority than Archaludon given the cross-validation evidence, kept as backup options if Archaludon's real ladder score disappoints.

### tetsutani/grimmsnarl-ex-damage-transfer-control — Adaptive Grimmsnarl ex Control

- **Author / votes**: tetsutani, 100 votes
- **Approach type**: multi-expert system — strategic policy + mirror/tempo experts routed via a matchup router, 5 guard layers, a custom hand-rolled decision-tree ensemble (`policy_ensemble.bin.gz`, home-grown "PTC2" binary format), cross-game opponent memory (`human_controller.py`/`human_memory.py`). Versioned publicly as v15, internal folders show iteration up to v32.
- **Win-rate / LB claim**: none disclosed — pure engineering share, no score in the title or README.
- **Verified locally?**: **discarded, not tested.** Payload is a base64+gzip-obfuscated single blob (unlike every other kernel audited, which ships plain readable `%%writefile` cells) — decoded and read-only inspected (SHA256 verified against the notebook's own declared hash, confirming no tampering vs. what's shipped), but the session's safety classifier correctly blocked local execution of the extracted code without an explicit user run-instruction. On review, decided the unusual obfuscation wasn't worth pursuing given 4+ other candidates with real disclosed provenance and cross-validation already in hand.
- **Skip reason**: discarded by user decision (2026-08-07) — "it looks weird" — after the execution block surfaced the obfuscation as a real difference from every other source audited, not just a technical hiccup.

## Why each field matters

- **Verified locally?** exists because a claimed win rate is only as good as its opponent —
  `run-battle` lets you check a claim cheaply before trusting it enough to build on.
- **Local-sim-vs-ladder red flag** exists because this competition's real scoring happens on a
  hidden ladder, not the local `cg` engine's fixed opponent pool — a kernel can look strong
  locally while being tuned to beat one specific bot rather than a diverse field. Multiple
  kernels in this competition (`dashimaki360/beating-the-day-1-1-crustle-bot`,
  `kokinnwakashuu/ptcg-lucario-public-lab-anti-crustle-log`) are explicitly framed as beating
  one named bot (Crustle) — useful to know about, but don't treat "beats Crustle" as "beats
  the ladder."
- **Reusable idea** is deliberately singular — force the audit to extract the one concrete,
  actionable takeaway rather than a vague summary, so Day-2 synthesis is scannable.
