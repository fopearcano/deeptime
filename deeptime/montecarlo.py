"""Monte-Carlo ensembles and the probability questions of sections 42-45.

Each run draws its own random graph and stochastic history from a seeded RNG
(the ensemble seed offsets the per-run seed so runs are independent yet the
whole ensemble is reproducible).  We then estimate, by the empirical-frequency
estimator of section 45,

    P(A) = (1/N) * sum_r  1[ A holds in run r ],

for the technological / political / historical questions of section 42.

Runs are independent, so the ensemble is embarrassingly parallel; when more than
one worker is requested the histories are spread across processes.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Callable, Dict, List

import numpy as np

from .config import Params
from .model import Simulation


# --- section 42 predicates over a finished run -----------------------------
def _max_over_time(run: Simulation, key: str) -> float:
    best = -np.inf
    for rec in run.records:
        for c in rec["civ"].values():
            best = max(best, c.get(key, -np.inf))
    return best if np.isfinite(best) else 0.0


def _ever_stable_empire(run: Simulation, k_min: float = 3.0, g_min: float = 0.5,
                        node_min: int = 5) -> bool:
    for rec in run.records:
        for c in rec["civ"].values():
            if c["K"] >= k_min and c["G"] >= g_min and c["nodes"] >= node_min:
                return True
    return False


def _extinction(run: Simulation) -> bool:
    return any(e.kind == "extinction" for e in run.events)


def _aeonic(run: Simulation) -> bool:
    return any(e.kind == "aeonic_transition" for e in run.events)


def _chronal(run: Simulation) -> bool:
    return _max_over_time(run, "Phi") >= run.params.Phi_chronal


QUESTIONS: Dict[str, Callable[[Simulation], bool]] = {
    "P(K>=1)": lambda r: _max_over_time(r, "K") >= 1.0,
    "P(K>=2)": lambda r: _max_over_time(r, "K") >= 2.0,
    "P(K>=3)": lambda r: _max_over_time(r, "K") >= 3.0,
    "P(Phi>=3)": lambda r: _max_over_time(r, "Phi") >= 3.0,
    "P(stable galactic empire)": _ever_stable_empire,
    "P(extinction event)": _extinction,
    "P(aeonic transition)": _aeonic,
    "P(chronal breakthrough)": _chronal,
}

# metric label -> (per-civ key, reduction) ; None key means a global record field
METRICS: Dict[str, tuple] = {
    "K_max": ("K", "max"),
    "Phi_max": ("Phi", "max"),
    "P_total": ("P", "sum"),
    "A_mean": ("A", "mean"),
    "n_civ": (None, None),
    "n_colonized": (None, None),
}


def _civ_reduce(rec: dict, key: str, how: str = "max") -> float:
    vals = [c.get(key, 0.0) for c in rec["civ"].values()]
    if not vals:
        return 0.0
    if how == "max":
        return float(np.max(vals))
    if how == "sum":
        return float(np.sum(vals))
    return float(np.mean(vals))


@dataclass
class EnsembleResult:
    n_runs: int
    probabilities: Dict[str, float]
    stderr: Dict[str, float]
    time_grid: List[float]
    mean_series: Dict[str, List[float]]
    p10_series: Dict[str, List[float]]
    p90_series: Dict[str, List[float]]
    sample_runs: List[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "n_runs": self.n_runs,
            "probabilities": self.probabilities,
            "stderr": self.stderr,
            "time_grid": self.time_grid,
            "mean_series": self.mean_series,
            "p10_series": self.p10_series,
            "p90_series": self.p90_series,
            "sample_runs": self.sample_runs,
        }


def summarize_run(run: Simulation) -> dict:
    """Compact JSON-serialisable summary of a single run for the frontend."""
    series = {"t": [], "K_max": [], "Phi_max": [], "P_total": [], "A_mean": [],
              "n_civ": [], "n_colonized": [], "R_gal": [], "psi_mean": []}
    for rec in run.records:
        series["t"].append(rec["t"])
        series["K_max"].append(_civ_reduce(rec, "K", "max"))
        series["Phi_max"].append(_civ_reduce(rec, "Phi", "max"))
        series["P_total"].append(_civ_reduce(rec, "P", "sum"))
        series["A_mean"].append(_civ_reduce(rec, "A", "mean"))
        series["n_civ"].append(rec["n_civ"])
        series["n_colonized"].append(rec["n_colonized"])
        series["R_gal"].append(rec.get("R_gal", 0.0))
        series["psi_mean"].append(rec.get("psi_mean", 0.0))
    events = [
        {"t": e.t, "kind": e.kind, "civ": e.civ, "node": e.node, "detail": e.detail}
        for e in run.events
    ]
    return {"series": series, "events": events, "n_events": len(events)}


def _metric_series(run: Simulation, grid: np.ndarray) -> Dict[str, np.ndarray]:
    ts = np.array([rec["t"] for rec in run.records])
    out = {}
    for label, (key, how) in METRICS.items():
        if key is None:
            ys = np.array([rec[label] for rec in run.records], dtype=float)
        else:
            ys = np.array([_civ_reduce(rec, key, how) for rec in run.records])
        out[label] = np.interp(grid, ts, ys, left=ys[0], right=ys[-1])
    return out


def _run_one(payload: dict) -> dict:
    """Worker: run a single history and return only lightweight results."""
    params = Params.from_dict(payload["params"])
    params.seed = payload["seed"]
    grid = np.asarray(payload["grid"])
    sim = Simulation(params=params)
    sim.run(record_every=payload["record_every"])
    result = {
        "hits": {name: bool(pred(sim)) for name, pred in QUESTIONS.items()},
        "metrics": {k: v.tolist() for k, v in _metric_series(sim, grid).items()},
    }
    if payload["want_summary"]:
        result["summary"] = summarize_run(sim)
    return result


def run_ensemble(
    params: Params,
    n_runs: int = 40,
    record_every: int = 4,
    n_samples: int = 3,
    workers: int = 0,
    progress: Callable[[int, int], None] | None = None,
) -> EnsembleResult:
    """Run ``n_runs`` independent histories and aggregate them.

    ``workers`` <= 1 runs serially; ``workers`` == 0 auto-selects a small pool.
    """
    base_seed = params.seed
    grid = np.linspace(0, params.t_max, 60)
    payloads = [
        {
            "params": params.to_dict(),
            "seed": base_seed + 1009 * (r + 1),
            "record_every": record_every,
            "grid": grid.tolist(),
            "want_summary": r < n_samples,
        }
        for r in range(n_runs)
    ]

    if workers == 0:
        import os
        workers = min(4, max(1, (os.cpu_count() or 1)))

    results: List[dict] = [None] * n_runs
    done = 0
    if workers <= 1:
        for r, pl in enumerate(payloads):
            results[r] = _run_one(pl)
            done += 1
            if progress:
                progress(done, n_runs)
    else:
        try:
            with ProcessPoolExecutor(max_workers=workers) as ex:
                futures = {ex.submit(_run_one, pl): r for r, pl in enumerate(payloads)}
                for fut in as_completed(futures):
                    r = futures[fut]
                    results[r] = fut.result()
                    done += 1
                    if progress:
                        progress(done, n_runs)
        except Exception:
            # Fall back to serial if the process pool is unavailable.
            for r, pl in enumerate(payloads):
                if results[r] is None:
                    results[r] = _run_one(pl)
                    done += 1
                    if progress:
                        progress(done, n_runs)

    # probabilities (section 45)
    probs: Dict[str, float] = {}
    serr: Dict[str, float] = {}
    for name in QUESTIONS:
        hits = np.array([1.0 if res["hits"][name] else 0.0 for res in results])
        p_hat = float(np.mean(hits))
        probs[name] = p_hat
        serr[name] = float(np.sqrt(max(p_hat * (1 - p_hat), 0.0) / max(n_runs, 1)))

    # aggregate trajectories
    mean_series: Dict[str, List[float]] = {}
    p10: Dict[str, List[float]] = {}
    p90: Dict[str, List[float]] = {}
    for label in METRICS:
        arr = np.vstack([np.asarray(res["metrics"][label]) for res in results])
        mean_series[label] = [float(v) for v in np.mean(arr, axis=0)]
        p10[label] = [float(v) for v in np.percentile(arr, 10, axis=0)]
        p90[label] = [float(v) for v in np.percentile(arr, 90, axis=0)]

    samples = [res["summary"] for res in results if "summary" in res][:n_samples]

    return EnsembleResult(
        n_runs=n_runs,
        probabilities=probs,
        stderr=serr,
        time_grid=[float(v) for v in grid],
        mean_series=mean_series,
        p10_series=p10,
        p90_series=p90,
        sample_runs=samples,
    )
