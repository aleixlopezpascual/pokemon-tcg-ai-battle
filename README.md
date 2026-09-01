# Pokémon TCG AI Battle — Top 14% Solution 🏆

Welcome to the development repository for the Kaggle [PTCG AI Battle Challenge Simulation](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle) competition (featured simulation contest, running from August 6 to August 16, 2026).

This repository contains our complete development history, local simulation harness, and the codebase for **`grimmsnarl_v1`**, our final submission that achieved **824.7 μ on the settled leaderboard**, landing at **Rank 931 out of 6,807 teams (Top 13.67%)**.

---

## 🚀 Executive Summary & Results

Our journey through the competition spanned multiple paradigms—from rule-based heuristics and Monte Carlo Search to offline Imitation Learning—culminating in a highly successful last-minute archetype pivot:

*   **Final Standing:** Rank 931 of 6,807 (Top 13.67%)
*   **Final Score:** 824.7 μ (TrueSkill rating scale)
*   **Peak Score:** 942.9 μ (interim reading over 58 games)
*   **The Winning Agent:** `grimmsnarl_v1` (Marnie Grimmsnarl ex damage-transfer control)

---

## 🛠️ Key Technical Implementations

### 1. The Marnie Grimmsnarl Archetype Pivot (Our Silver-Tier Breakthrough)
Early in the competition, we worked heavily on the dominant **Archaludon ex** archetype, hardening it against common blunders (boundary crashes, supporter paralysis, empty benched ex vulnerabilities). While our hardened Archaludon (`lucifer19_lossfix_merge`) achieved a robust ~775 μ, data-mining the leaderboard score-bands revealed a structural ceiling:
*   Archaludon held a mere **1.4% share** of the 800–899 bronze score band and was practically absent above it.
*   In contrast, **Marnie Grimmsnarl ex** held a massive **52.4% share** in the same band, indicating a vastly higher skill ceiling in the simulator.

With 24 hours to the deadline, we executed a complete archetype pivot to `grimmsnarl_v1` (a fork of `tetsutani`'s Grimmsnarl ex damage-transfer control with custom decision-tree scoring and rule guards), which rapidly climbed the ladder to peak at **942.9 μ** before settling at **824.7 μ**.

### 2. Sandbox-Compliant Imitation Learning (IL) Pipeline
We built a highly scalable imitation-learning pipeline to train models on professional game logs:
*   **Data Scraper & Pipeline:** Extracted and parsed over **760,000 game states** from public leaderboard matches, weighting training samples based on the players' settled TrueSkill scores.
*   **JSON-Tree Compiler (`pure_predictor.py`):** The Kaggle simulation sandbox operates in a minimal environment devoid of standard data-science dependencies (`numpy`, `pandas`, `scikit-learn`). To deploy our trained `HistGradientBoostingClassifier`, we wrote a custom compiler that exported sklearn's decision tree structure into plain JSON, and re-implemented a zero-dependency bit-for-bit identical inference engine in standard library Python.

### 3. Playable-Information Monte Carlo (PIMC) Forward Search
We developed a Monte Carlo forward-planning layer (`src/pimc.py`) utilizing the game engine's state-transition and prediction APIs. The search layer simulated prospective lines of play to evaluate optimal moves. This track ultimately served as a "blunder oracle," helping us identify and fix critical edge-case bugs in our main rule-based agents.

### 4. Robust Simulation Evaluation & Order-Invariant Estimation
Early-reading TrueSkill values on the Kaggle ladder suffer from extreme noise (drift of ±50–65 μ). To validate our code changes locally without wasting daily submission quotas:
*   We created `src/ladder_eval.py`, featuring a **batch Maximum Likelihood Estimator (MLE)** to solve candidate TrueSkill scores.
*   The estimator fits the full local tournament result set at once, providing **provably order-invariant rating calculations** that resolved local-to-ladder calibration mismatches.

---

## 📁 Repository Structure

```tree
/
├── .claude/                   # Claude helper settings, rules, and local pre-push safety scan hooks
├── docs/                      # Technical specifications and step-by-step implementation plans
├── notebooks/kaggle-research/ # In-depth research logs, discussion audits, and iteration metrics
│   ├── 10-day-plan.md         # Master day-by-day roadmap and submission logs
│   ├── grimmsnarl-iteration-log.md # Detailed metrics for Grimmsnarl v1 to v5
│   └── evaluation-methodology.md # Local evaluation and TrueSkill MLE design
├── src/                       # Reusable Python scripts and modules
│   ├── ladder_eval.py         # Tourney rating MLE estimator
│   ├── trueskill_lite.py      # Standard library TrueSkill solver
│   ├── pure_predictor.py      # Dependency-free JSON model predictor
│   └── feature_engineering.py # State feature extraction for ML models
├── submissions/               # Snapshot directories of candidate agents
│   ├── grimmsnarl_v1/         # Final Top 14% agent (main.py + deck.csv)
│   ├── archaludon_hardening_v1/ # Our best hardened Archaludon candidate
│   └── alakazam_v2/           # Secondary Alakazam archetype pivot candidate
├── requirements.txt           # Project dependencies (local research environment)
└── deck.csv                   # Current active card-list configuration
```

---

## ⚙️ Getting Started & Installation

### 1. Prerequisites
Ensure you have Python 3.11+ installed. We recommend using `uv` for fast virtual environment management.

### 2. Setup Environment
```bash
# Create a virtual environment
uv venv --python 3.11
source .venv/bin/activate

# Install dependencies
uv pip install -r requirements.txt
```

### 3. Run a Local Battle
You can simulate a battle between two agents locally using our pre-built script:
```bash
python3 .claude/skills/run-battle/scripts/run_battle.py --player1 submissions/grimmsnarl_v1/ --player2 submissions/archaludon_hardening_v1/
```

### 4. Run the Tournament Evaluation
To calculate MLE-fitted TrueSkill ratings across a panel of local agents:
```bash
python3 src/ladder_eval.py rate --candidate submissions/grimmsnarl_v1/
```

---

## 🔒 Safety and Security Scans

This repository includes custom pre-push hooks to prevent accidental leakage of raw competition datasets or Kaggle credentials:
*   Run the safety scanner before pushing any changes to your public fork:
    ```bash
    bash .claude/skills/secrets-and-data-guard/scripts/scan.sh
    ```

---

## 💭 Key Engineering Takeaways

*   **Meta Beats Micro-Optimization:** Technical hardening on a capped archetype is a losing battle. Swapping archetypes to match the high-tier meta (Marnie Grimmsnarl) resulted in an immediate **+150 μ** jump that no amount of code refinement could have matched.
*   **Be Sandbox-Agnostic:** Assume simulation platforms are extremely minimal. Designing a custom zero-dependency JSON tree parser allowed us to deploy powerful ensemble models without relying on third-party binary wheels.
*   **Validate Order-Invariance:** When evaluating sequential game histories, sequential rating estimation introduces order-bias. Upgrading to batch maximum-likelihood estimation (MLE) was vital to making our local tests representative of the public leaderboard.

---

*Developed by Aleix López (Rank 931, PTCG AI Battle Kaggle Simulation Challenge).*
