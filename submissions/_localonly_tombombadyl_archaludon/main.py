"""Local-evaluation entry point for TomBombadyl's Archaludon ex / Cinderace agent.

LOCAL EVALUATION ONLY - see DO-NOT-SHIP.md. This shim exists so the agent loads under
src/ladder_eval.py and .claude/skills/run-battle, which import main.py by path from a
working directory that is not the candidate directory. Their own packager assumed
os.getcwd() was the bundle root (true on Kaggle, false here); nothing else is changed.
"""

import os
import sys

_here = "/kaggle_simulations/agent"
if not os.path.isdir(_here):
    try:
        _here = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        _here = os.getcwd()
if _here not in sys.path:
    sys.path.insert(0, _here)

from archaludon_agent import agent  # noqa: E402,F401
