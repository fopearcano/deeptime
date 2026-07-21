"""JSON-friendly snapshots of a running simulation for the web interface."""

from __future__ import annotations

from typing import Dict, List

import numpy as np

from . import state as S
from .model import Simulation


def _project_2d(positions: np.ndarray) -> np.ndarray:
    """Project 3D node positions to 2D via the first two principal axes."""
    if positions.shape[0] < 2:
        return positions[:, :2]
    centered = positions - positions.mean(axis=0, keepdims=True)
    try:
        _, _, vt = np.linalg.svd(centered, full_matrices=False)
        coords = centered @ vt[:2].T
    except np.linalg.LinAlgError:
        coords = centered[:, :2]
    return coords


def graph_snapshot(sim: Simulation, max_edges: int = 400) -> Dict:
    """Node/edge snapshot of the current Field graph coloured by occupant."""
    p = sim.params
    coords = _project_2d(sim.graph.positions)
    # scale to a friendly range
    span = np.max(np.abs(coords)) + 1e-9
    coords = coords / span

    # occupant civ per node (-1 if empty), pick the civ with most population
    occupant = np.full(p.n_nodes, -1, dtype=int)
    for i in range(p.n_nodes):
        holders = np.where(sim.occ[:, i] > 0)[0]
        if len(holders):
            pops = sim.x[holders, i, S.P]
            occupant[i] = int(holders[int(np.argmax(pops))])

    nodes: List[Dict] = []
    for i in range(p.n_nodes):
        a = occupant[i]
        nodes.append({
            "id": i,
            "x": float(coords[i, 0]),
            "y": float(coords[i, 1]),
            "civ": int(a),
            "psi": float(sim.psi[i]),
            "phi": float(sim.x[a, i, S.PHI]) if a >= 0 else 0.0,
            "pop": float(sim.x[a, i, S.P]) if a >= 0 else 0.0,
            "capital": bool(a >= 0 and sim.capital[a] == i),
        })

    w = sim.graph.field_weights(sim.psi, p)
    edges: List[Dict] = []
    iu, ju = np.triu_indices(p.n_nodes, k=1)
    wv = w[iu, ju]
    order = np.argsort(-wv)
    wmax = float(np.max(wv)) + 1e-9
    for k in order:
        if wv[k] <= 0:
            continue
        if len(edges) >= max_edges:
            break
        edges.append({
            "s": int(iu[k]),
            "t": int(ju[k]),
            "w": float(wv[k] / wmax),
        })

    return {
        "nodes": nodes,
        "edges": edges,
        "n_civ": int(np.sum(sim.alive)),
        "t": float(sim.t),
    }


def run_snapshot(sim: Simulation) -> Dict:
    """Everything the frontend needs to render one finished run."""
    from .montecarlo import summarize_run
    summary = summarize_run(sim)
    summary["graph"] = graph_snapshot(sim)
    # final per-civ state table
    civ_table = []
    for a in sim.alive_indices():
        nodes = np.where(sim.occ[a] > 0)[0]
        if len(nodes) == 0:
            continue
        Etot = float(np.sum(sim.x[a, nodes, S.E]))
        K = (np.log10(max(Etot, 1e-9)) - sim.params.kardashev_k0) / sim.params.kardashev_dk
        phi = float(np.max(sim.x[a, nodes, S.PHI]))
        level, era_en, era_it = S.civ_era(K, phi)
        oct_level, vclass, vname = S.oct_reach(phi)
        civ_table.append({
            "civ": int(a),
            "nodes": int(len(nodes)),
            "P": float(np.sum(sim.x[a, nodes, S.P])),
            "K": float(K),
            "Phi": phi,
            "tier": S.field_tier(phi),
            "era_level": level,
            "era": era_en,
            "era_it": era_it,
            "oct": oct_level,
            "vessel": vclass,
            "vessel_name": vname,
            "A": float(np.mean(sim.x[a, nodes, S.A])),
            "G": float(np.mean(sim.x[a, nodes, S.G])),
            "I": float(np.mean(sim.x[a, nodes, S.I])),
            "aeon": int(sim.aeon_count[a]),
        })
    summary["civ_table"] = civ_table
    summary["params"] = sim.params.to_dict()

    # Deep-time ladder trajectory (Image 1): civilizational level vs cosmic year.
    # We plot, at each record, the (cosmic_year, max_era) reached by the leading
    # civilization -- the frontier of the civilizational ecosystem.
    ladder = [[rec.get("cosmic_year", 0.0), rec.get("max_era", 0)] for rec in sim.records]
    # per-civ frontier lines keyed by civ id (era over cosmic time)
    per_civ = {}
    for rec in sim.records:
        cy = rec.get("cosmic_year", 0.0)
        for cid, c in rec.get("civ", {}).items():
            per_civ.setdefault(int(cid), []).append([cy, c.get("era_level", 1)])
    summary["ladder"] = {
        "frontier": ladder,
        "per_civ": per_civ,
        "narrative_year": float(sim.params.narrative_year),
        "year0": float(sim.params.cosmic_year0),
        "year_end": float(sim.params.cosmic_year_end),
    }
    final = sim.records[-1] if sim.records else {}
    summary["cosmos"] = {
        "cosmic_year": final.get("cosmic_year", 0.0),
        "cosmo_era": final.get("cosmo_era", ""),
        "cosmo_era_key": final.get("cosmo_era_key", ""),
        "max_aeon": int(max((sim.aeon_count[a] for a in sim.alive_indices()), default=0)),
        "fate": sim.cosmic_fate,
        "fate_name": sim.cosmic_fate_name,
    }
    return summary
