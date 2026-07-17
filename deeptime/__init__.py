"""Deep-Time Civilizational Evolution model.

A hybrid stochastic dynamical network implementing the specification in
``docs/deep_time_complete_mathematical_model.md``.

Typical use::

    from deeptime import Params, Simulation, run_ensemble

    sim = Simulation(params=Params())
    sim.run()

    ens = run_ensemble(Params(), n_runs=100)
    print(ens.probabilities)
"""

from .config import Params, PARAM_META, TAG_MEANING
from .model import Simulation, EventRecord
from .montecarlo import run_ensemble, EnsembleResult, QUESTIONS, summarize_run
from .serialize import graph_snapshot, run_snapshot
from . import state

__version__ = "1.0.0"

__all__ = [
    "Params",
    "PARAM_META",
    "TAG_MEANING",
    "Simulation",
    "EventRecord",
    "run_ensemble",
    "EnsembleResult",
    "QUESTIONS",
    "summarize_run",
    "graph_snapshot",
    "run_snapshot",
    "state",
    "__version__",
]
