"""Spatial structure: the ordinary-space graph and the Field graph (section 4).

Two graphs share the same node set ``V``:

* ``G_S`` -- ordinary space.  Each node has a position ``r_i`` in R^3 and the
  ordinary distance is the Euclidean norm ``d^S_{ij} = ||r_i - r_j||``.
* ``G_Phi`` -- the Field graph.  A time-dependent weighted adjacency
  ``W^Phi_{ij} >= 0`` where a high weight means easy Field access.  The Field
  cost is ``c^Phi_{ij} = 1 / (W^Phi_{ij} + eps)`` and the Field distance is the
  shortest-path cost (section 4.2).

The Field graph need not respect ordinary proximity -- that non-locality is the
whole point of the "Field Ocean" (section 1).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np


@dataclass
class SpaceGraph:
    """Ordinary-space + Field graph over a shared node set."""

    positions: np.ndarray      # (n, 3) ordinary-space coordinates
    base_field_w: np.ndarray   # (n, n) baseline Field weights W^Phi_{ij,0}
    turbulence: np.ndarray     # (n, n) turbulence T_ij in [0, 1]
    barrier: np.ndarray        # (n, n) topological barrier strength B_ij

    @property
    def n(self) -> int:
        return self.positions.shape[0]

    # -- ordinary space ---------------------------------------------------
    def ordinary_distance(self) -> np.ndarray:
        """Euclidean distance matrix d^S_{ij}."""
        diff = self.positions[:, None, :] - self.positions[None, :, :]
        return np.sqrt(np.sum(diff * diff, axis=-1))

    # -- Field graph ------------------------------------------------------
    def field_weights(self, psi: np.ndarray, p) -> np.ndarray:
        """Route weights W^Phi_{ij}(t) from section 5.

        W_{ij} = W_{ij,0} * exp[ eta_psi (psi_i + psi_j)/2
                                 - eta_T T_{ij} - eta_B B_{ij} ]
        """
        psi_sum = 0.5 * (psi[:, None] + psi[None, :])
        w = self.base_field_w * np.exp(
            p.eta_psi * psi_sum - p.eta_T * self.turbulence - p.eta_B * self.barrier
        )
        # No self loops.
        np.fill_diagonal(w, 0.0)
        return w

    def field_laplacian(self, w: np.ndarray) -> np.ndarray:
        """Graph Laplacian L = D - W of the (symmetric) Field graph."""
        deg = np.sum(w, axis=1)
        return np.diag(deg) - w

    def field_cost(self, w: np.ndarray, eps: float) -> np.ndarray:
        """Edge cost c^Phi_{ij} = 1 / (W_{ij} + eps); inf where no edge."""
        cost = 1.0 / (w + eps)
        # Treat (near) zero-weight edges as absent.
        cost[w <= 0.0] = np.inf
        np.fill_diagonal(cost, 0.0)
        return cost

    def field_distance(self, w: np.ndarray, eps: float) -> np.ndarray:
        """All-pairs shortest Field distance d^Phi_{ij} (section 4.2).

        Vectorised Floyd-Warshall in the (min, +) semiring.  For the small node
        counts here (tens to low hundreds) this is far faster than a Python-level
        Dijkstra because every relaxation sweep is a single numpy broadcast.
        """
        dist = self.field_cost(w, eps).copy()
        n = self.n
        with np.errstate(invalid="ignore"):
            for k in range(n):
                # dist_ij = min(dist_ij, dist_ik + dist_kj)
                np.minimum(dist, dist[:, k][:, None] + dist[k, :][None, :], out=dist)
        return dist


def build_space_graph(
    n: int,
    rng: np.random.Generator,
    connectivity: float = 0.35,
    box: float = 100.0,
) -> SpaceGraph:
    """Generate a random inhabited-region graph.

    Nodes are placed uniformly in a cube.  Field edges are created with a
    probability that *decreases* with ordinary distance (nearby systems are more
    likely linked) but the weights themselves are randomised so the Field graph
    can still shortcut ordinary space -- some long edges are strong.
    """
    positions = rng.uniform(-box / 2, box / 2, size=(n, 3))
    diff = positions[:, None, :] - positions[None, :, :]
    dS = np.sqrt(np.sum(diff * diff, axis=-1))
    scale = np.median(dS[dS > 0]) if np.any(dS > 0) else 1.0

    # Edge presence: denser for near pairs, but a few long Field shortcuts.
    prob = connectivity * np.exp(-dS / scale)
    rand = rng.random((n, n))
    present = rand < prob
    present = present | present.T          # symmetric
    np.fill_diagonal(present, False)

    # A handful of long-range Field shortcuts, independent of ordinary distance.
    n_short = max(1, n // 6)
    for _ in range(n_short):
        i, j = rng.integers(0, n, size=2)
        if i != j:
            present[i, j] = present[j, i] = True

    # Weights: baseline 1, boosted for shortcuts, jittered.
    w = np.where(present, rng.uniform(0.5, 2.0, size=(n, n)), 0.0)
    w = 0.5 * (w + w.T)
    np.fill_diagonal(w, 0.0)

    # Ensure connectivity: link each isolated node to its nearest neighbour.
    for i in range(n):
        if not np.any(w[i] > 0):
            order = np.argsort(dS[i])
            for j in order:
                if j != i:
                    w[i, j] = w[j, i] = rng.uniform(0.5, 1.5)
                    break

    turbulence = np.clip(rng.uniform(0.0, 0.4, size=(n, n)), 0, 1)
    turbulence = 0.5 * (turbulence + turbulence.T)
    np.fill_diagonal(turbulence, 0.0)

    barrier = np.clip(rng.uniform(0.0, 0.3, size=(n, n)), 0, 1)
    barrier = 0.5 * (barrier + barrier.T)
    np.fill_diagonal(barrier, 0.0)

    return SpaceGraph(
        positions=positions,
        base_field_w=w,
        turbulence=turbulence,
        barrier=barrier,
    )


def connected_components(adj: np.ndarray) -> List[List[int]]:
    """Connected components of a boolean/weighted adjacency matrix."""
    n = adj.shape[0]
    seen = np.zeros(n, dtype=bool)
    comps: List[List[int]] = []
    for start in range(n):
        if seen[start]:
            continue
        stack = [start]
        seen[start] = True
        comp = []
        while stack:
            u = stack.pop()
            comp.append(u)
            for v in range(n):
                if not seen[v] and adj[u, v] > 0:
                    seen[v] = True
                    stack.append(v)
        comps.append(sorted(comp))
    return comps


def spectral_two_split(weight: np.ndarray, nodes: List[int]) -> Optional[List[List[int]]]:
    """Split a set of nodes into two clusters by the Fiedler vector.

    Used for fragmentation (section 31).  ``weight`` is the full affinity matrix
    ``W_{ij}`` (section 31); we restrict it to ``nodes`` and cut on the sign of
    the second-smallest eigenvector of the Laplacian.
    """
    if len(nodes) < 2:
        return None
    sub = weight[np.ix_(nodes, nodes)]
    deg = np.sum(sub, axis=1)
    lap = np.diag(deg) - sub
    try:
        vals, vecs = np.linalg.eigh(lap)
    except np.linalg.LinAlgError:
        return None
    if len(vals) < 2:
        return None
    fiedler = vecs[:, 1]
    left = [nodes[k] for k in range(len(nodes)) if fiedler[k] >= 0]
    right = [nodes[k] for k in range(len(nodes)) if fiedler[k] < 0]
    if not left or not right:
        return None
    return [left, right]
