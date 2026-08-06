# Pokemon TCG AI Battle

Working repo for the Kaggle competition: [PTCG AI Battle Challenge Simulation](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle) (Featured, Knowledge reward, deadline **2026-08-16**).

## Structure

- `data/raw/` — original competition data (not tracked)
- `data/processed/` — feature/derived data caches (not tracked)
- `notebooks/` — findings and research docs
- `src/` — reusable modules
- `kernels/` — Kaggle notebook templates for submission
- `models/`, `submissions/` — artifacts (not tracked)

## Setup

```bash
uv venv --python 3.11
uv pip install --python ./.venv/bin/python -r requirements.txt
```
