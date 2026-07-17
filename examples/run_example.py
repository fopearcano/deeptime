"""Minimal command-line example for the Deep-Time model.

Runs a single history, prints a compact chronicle of its deep-time arc, then
runs a small Monte-Carlo ensemble and prints the probability questions of
section 42.

Usage::

    python examples/run_example.py            # defaults
    python examples/run_example.py --runs 60  # bigger ensemble
"""

import argparse
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deeptime import Params, Simulation, run_ensemble, state as S


def chronicle(sim: Simulation) -> None:
    print("\n=== Single history ===")
    print(f"integrated to t = {sim.t:.1f} in {sim.step_count} adaptive steps")
    kinds = Counter(e.kind for e in sim.events)
    print("events:", dict(kinds))

    last = sim.records[-1]
    print(f"\nfinal state: {last['n_civ']} civilization(s), "
          f"{last['n_colonized']} colonized sites")
    for a, c in sorted(last["civ"].items()):
        print(f"  civ {a}: K={c['K']:.2f}  Phi={c['Phi']:.2f} "
              f"({S.field_tier(c['Phi'])})  pop={c['P']:.1f}  "
              f"sites={c['nodes']}  universe U{c['universe']}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Deep-Time model example")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--nodes", type=int, default=24)
    ap.add_argument("--civ", type=int, default=3)
    ap.add_argument("--tmax", type=float, default=50.0)
    ap.add_argument("--runs", type=int, default=40)
    args = ap.parse_args()

    params = Params(n_nodes=args.nodes, n_civ=args.civ, t_max=args.tmax, seed=args.seed)

    sim = Simulation(params=params)
    sim.run()
    chronicle(sim)

    print(f"\n=== Monte-Carlo ensemble ({args.runs} runs) ===")

    def prog(done, total):
        bar = int(30 * done / total)
        print(f"\r  [{'#' * bar}{'.' * (30 - bar)}] {done}/{total}", end="", flush=True)

    ens = run_ensemble(params, n_runs=args.runs, progress=prog)
    print("\n")
    for q, p in ens.probabilities.items():
        print(f"  {q:<30} {p:5.2f}  +/- {ens.stderr[q]:.2f}")


if __name__ == "__main__":
    main()
