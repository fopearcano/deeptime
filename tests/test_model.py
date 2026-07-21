"""Tests for the Deep-Time model.

Runnable either with pytest (``pytest tests``) or directly
(``python tests/test_model.py``) so no test framework is required.
"""

import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deeptime import Params, Simulation, run_ensemble, run_snapshot, state as S
from deeptime.graph import build_space_graph


# --- parameters ------------------------------------------------------------
def test_params_roundtrip_and_unknown_keys():
    p = Params()
    d = p.to_dict()
    assert "pop_r" in d and "n_nodes" in d
    p2 = Params.from_dict({**d, "not_a_real_key": 123, "pop_r": 0.9})
    assert p2.pop_r == 0.9
    assert not hasattr(p2, "not_a_real_key")


# --- graph -----------------------------------------------------------------
def test_field_distance_matches_reference():
    """Floyd-Warshall distance on a tiny known graph."""
    rng = np.random.default_rng(0)
    g = build_space_graph(5, rng)
    # craft a simple path graph 0-1-2-3-4 with unit weights
    n = 5
    w = np.zeros((n, n))
    for i in range(n - 1):
        w[i, i + 1] = w[i + 1, i] = 1.0
    d = g.field_distance(w, eps=1e-9)
    # cost per unit-weight edge is 1/(1+eps) ~ 1
    edge = 1.0 / (1.0 + 1e-9)
    assert math.isclose(d[0, 4], 4 * edge, rel_tol=1e-6)
    assert math.isclose(d[1, 3], 2 * edge, rel_tol=1e-6)
    assert np.allclose(d, d.T)                      # symmetric
    assert np.all(np.diagonal(d) == 0)


def test_field_distance_disconnected_is_inf():
    rng = np.random.default_rng(1)
    g = build_space_graph(4, rng)
    w = np.zeros((4, 4))
    w[0, 1] = w[1, 0] = 1.0                          # {0,1} isolated from {2,3}
    w[2, 3] = w[3, 2] = 1.0
    d = g.field_distance(w, eps=1e-9)
    assert not np.isfinite(d[0, 2])


# --- simulation invariants -------------------------------------------------
def test_constraints_hold_and_finite():
    p = Params(n_nodes=16, n_civ=3, t_max=20, seed=3)
    sim = Simulation(params=p)
    sim.run(record_every=4)
    occ = sim.occ.astype(bool)
    assert np.all(np.isfinite(sim.x))
    # non-negativity (section 39)
    for idx in S.NONNEGATIVE_VARS:
        assert np.all(sim.x[..., idx] >= -1e-9)
    # unit-interval variables
    for idx in S.UNIT_INTERVAL_VARS:
        vals = sim.x[..., idx][occ]
        assert np.all(vals >= -1e-9) and np.all(vals <= 1 + 1e-9)
    # Field mastery within its ceiling
    assert np.all(sim.x[..., S.PHI] <= p.Phi_max + 1e-6)
    # coherence and chronal tech bounded
    assert np.all((sim.Omega >= -1e-9) & (sim.Omega <= 1 + 1e-9))
    assert np.all(sim.Gamma <= p.Gamma_max + 1e-6)


def test_reproducible_with_seed():
    p = Params(n_nodes=14, n_civ=2, t_max=15, seed=42)
    a = Simulation(params=p); a.run(record_every=5)
    b = Simulation(params=Params.from_dict(p.to_dict())); b.run(record_every=5)
    assert a.step_count == b.step_count
    assert len(a.events) == len(b.events)
    assert np.allclose(a.x, b.x)
    # different seed -> different history
    c = Simulation(params=Params(n_nodes=14, n_civ=2, t_max=15, seed=43)); c.run(record_every=5)
    assert not np.allclose(a.x, c.x)


def test_population_nonnegative_and_records_grow():
    p = Params(n_nodes=12, n_civ=2, t_max=20, seed=7)
    sim = Simulation(params=p); sim.run(record_every=4)
    assert np.all(sim.x[..., S.P] >= 0)
    assert len(sim.records) > 2
    assert sim.records[-1]["t"] <= p.t_max + p.dt_max


# --- civilizational & cosmological framework (Image 1, 4-5) ----------------
def test_civ_era_ladder_monotonic():
    # planetary at the bottom, chronal at the top
    assert S.civ_era(0.7, 0.0)[0] == 1
    assert S.civ_era(1.2, 1.0)[1] == "Solar"
    assert S.civ_era(2.2, 2.0)[1] == "Interstellar"
    assert S.civ_era(3.1, 3.1)[1] == "Galactic"    # Galactic needs K>=3 and Phi>=3
    assert S.civ_era(3.1, 4.1)[1] == "Oceanic"     # Oceanic needs K>=3 and Phi>=4
    assert S.civ_era(4.6, 6.5)[0] == 7             # Chronal needs K>=4.5 and Phi>=6
    # both thresholds required: high Phi but low K cannot be top era (K-Phi coupling)
    assert S.civ_era(0.5, 6.5)[0] < 7
    assert S.civ_era(6.0, 3.0)[0] < 5              # high K but shallow Field stalls below Oceanic
    # non-decreasing in both arguments
    prev = 0
    for K, Phi in [(0.5, 0.2), (1.1, 1.1), (2.1, 2.1), (3.1, 3.1), (3.1, 4.1), (4.1, 5.1), (4.6, 6.1)]:
        lvl = S.civ_era(K, Phi)[0]
        assert lvl >= prev
        prev = lvl


def test_cosmo_era_and_energy_factor():
    assert S.cosmo_era(1.38e10 + 5e10)[0] == "stelliferous"
    assert S.cosmo_era(1e15)[0] == "degenerate"
    assert S.cosmo_era(1e101)[0] == "heat_death"
    # stellar energy availability declines with cosmic age, never rising
    ages = [1e10, 1e13, 1e15, 1e50, 1e101]
    factors = [S.cosmo_energy_factor(a) for a in ages]
    assert factors[0] == 1.0
    assert all(factors[i] >= factors[i + 1] for i in range(len(factors) - 1))


def test_cosmic_year_mapping_monotonic():
    p = Params(t_max=40, cosmic_year0=1e5, cosmic_year_end=5e11)
    sim = Simulation(params=p)
    assert abs(sim.cosmic_years(0) - 1e5) / 1e5 < 1e-6
    assert abs(sim.cosmic_years(40) - 5e11) / 5e11 < 1e-6
    ys = [sim.cosmic_years(t) for t in range(0, 41, 5)]
    assert all(ys[i] < ys[i + 1] for i in range(len(ys) - 1))


def test_oct_reach_and_vessel_classes():
    # OCT depth reach rises with Field mastery; the Formless is Chronal-only
    assert S.oct_reach(0.5)[1] == "Class 0"
    assert S.oct_reach(2.5)[1] == "Class I"
    assert S.oct_reach(3.5)[1] == "Class II"
    assert S.oct_reach(4.5)[1] == "Class III"
    assert S.oct_reach(6.2)[2] == "the Formless"
    assert S.oct_reach(5.9)[2] != "the Formless"      # Eonic is not yet Formless
    depths = [S.oct_depth_index(p) for p in [1, 2.5, 3.5, 4.5, 6.2]]
    assert all(depths[i] <= depths[i + 1] for i in range(len(depths) - 1))


def test_cosmic_fate_distribution_and_ccc_gating():
    from collections import Counter
    fates = Counter()
    for seed in range(200):
        fates[Simulation(params=Params(n_nodes=6, n_civ=1, t_max=1, seed=seed)).cosmic_fate] += 1
    # heat death is the modal fate (~45%); every fate key is valid
    assert fates["heat_death"] > fates["ccc"] > 0
    assert set(fates).issubset({f[0] for f in S.COSMIC_FATES})
    # conformal crossovers only ever happen in a CCC-fate universe
    for seed in range(12):
        sim = Simulation(params=Params(n_nodes=16, n_civ=3, t_max=40, seed=seed))
        sim.run(record_every=8)
        if any(e.kind == "aeonic_transition" for e in sim.events):
            assert sim.cosmic_fate == "ccc"


def test_snapshot_has_ladder_and_cosmos():
    p = Params(n_nodes=14, n_civ=2, t_max=20, seed=4)
    sim = Simulation(params=p); sim.run(record_every=6)
    snap = run_snapshot(sim)
    assert "ladder" in snap and "frontier" in snap["ladder"]
    assert all(1 <= pt[1] <= 7 for pt in snap["ladder"]["frontier"] if pt[1] > 0)
    assert "cosmos" in snap and "cosmo_era" in snap["cosmos"]
    for row in snap["civ_table"]:
        assert 1 <= row["era_level"] <= 7 and "era" in row


# --- serialization ---------------------------------------------------------
def test_snapshot_json_serializable():
    p = Params(n_nodes=14, n_civ=3, t_max=15, seed=5)
    sim = Simulation(params=p); sim.run(record_every=6)
    snap = run_snapshot(sim)
    for key in ("series", "events", "graph", "civ_table", "params"):
        assert key in snap
    assert len(snap["graph"]["nodes"]) == p.n_nodes
    # must be JSON serializable (the server sends it as JSON)
    text = json.dumps(snap)
    assert len(text) > 100


# --- ensemble --------------------------------------------------------------
def test_ensemble_probabilities_valid():
    p = Params(n_nodes=12, n_civ=2, t_max=18, seed=1)
    ens = run_ensemble(p, n_runs=6, record_every=8, workers=1)
    assert ens.n_runs == 6
    for name, val in ens.probabilities.items():
        assert 0.0 <= val <= 1.0
        assert ens.stderr[name] >= 0.0
    # aggregated series aligned to the grid
    assert len(ens.time_grid) == 60
    for key, series in ens.mean_series.items():
        assert len(series) == 60


def test_ensemble_reproducible():
    p = Params(n_nodes=12, n_civ=2, t_max=15, seed=11)
    e1 = run_ensemble(p, n_runs=5, record_every=8, workers=1)
    e2 = run_ensemble(Params.from_dict(p.to_dict()), n_runs=5, record_every=8, workers=1)
    assert e1.probabilities == e2.probabilities


# --- runner ----------------------------------------------------------------
def _run_all():
    fns = [g for name, g in sorted(globals().items())
           if name.startswith("test_") and callable(g)]
    passed = 0
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
        passed += 1
    print(f"\n{passed}/{len(fns)} tests passed.")


if __name__ == "__main__":
    _run_all()
