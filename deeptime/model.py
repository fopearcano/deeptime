"""The hybrid stochastic dynamical model (sections 5-48 of the specification).

:class:`Simulation` holds the full ensemble state as a handful of numpy arrays
and advances it with an adaptive-timestep Euler / Euler-Maruyama scheme.  Each
step it:

1. rebuilds the Field graph weights and shortest-path distances (section 4);
2. resolves conflict damage for the step (section 28);
3. integrates every civilization's continuous local dynamics
   (sections 7-29) over the occupied nodes;
4. samples the discrete/stochastic events -- breakthroughs, colonization,
   conflict, collapse, fragmentation, merger and aeonic gates
   (sections 11, 20, 28, 30-34);
5. evolves the per-node Field state ``psi`` (section 5);
6. enforces the constraints of section 39 and records observables.

The *primary* tuning knobs live in :class:`~deeptime.config.Params`; a handful
of secondary shape-coefficients (communication / transport constants, unrest
weights, per-variable timestep scales) live as documented module constants.

Numerical notes
---------------
Military capacity and administrative complexity are given soft ceilings
(``M_max``, ``C_max``) purely as regularizers so the adaptive integrator is not
driven to its floor by their otherwise-unbounded growth.  The adaptive step is
chosen from *relative* change measured against a per-variable characteristic
scale (:data:`VAR_SCALE`) so that a fast but bounded variable does not dictate a
tiny global timestep.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from . import state as S
from .config import Params
from .graph import SpaceGraph, build_space_graph, spectral_two_split

# --- secondary shape coefficients (see module docstring) -------------------
TAU_COM0 = 1.0          # communication-time prefactor tau_0        (sec. 17)
GAMMA_PHI_COM = 0.7     # communication speed-up per Field mastery  (sec. 17)
V0_TRANSP = 0.4         # base vessel speed v_{q,0}                  (sec. 18)
NU_TRANSP = 0.8         # transport-speed exponent on Field mastery (sec. 18)
EPS_TRANSP = 0.25       # transport-speed exponent on energy        (sec. 18)
ZETA_TRANSP = 0.15      # transport-speed exponent on computation   (sec. 18)
U_FROM_I = 0.6          # unrest contribution from inequality       (sec. 26)
U_FROM_L = 0.6          # unrest contribution from illegitimacy     (sec. 26)
B_D_COLLAPSE = 0.4      # collapse-hazard weight on disruption D     (sec. 30)
MAX_CIV_SLOTS = 32      # hard cap on simultaneous civilizations
FIELD_REFRESH = 4       # steps between shortest-path Field-distance rebuilds
WAR_ONSET_RATE = 0.6    # max war-onset hazard (scaled by P_war)      (sec. 28)
WAR_PEACE_RATE = 0.5    # max peace hazard (scaled by 1 - P_war)      (sec. 28)
MERGE_RATE = 0.12       # merger hazard scale                         (sec. 32)
FRAG_COOLDOWN = 5.0     # min time before a civ can fragment again    (sec. 31)
COLLAPSE_COOLDOWN = 3.0 # min time before a node can collapse again   (sec. 30)
I_MAX = 8.0             # hard cap on inequality (numerical guard)    (sec. 39)
TINY = 1.0e-9

# Characteristic scale per state variable for the adaptive timestep.
VAR_SCALE = np.array([
    1.0,   # P
    1.0,   # H
    5.0,   # A
    50.0,  # E
    10.0,  # R
    30.0,  # Y
    30.0,  # Q
    5.0,   # L
    1.0,   # Phi
    1.0,   # G
    1.0,   # I
    20.0,  # M
    8.0,   # C
    1.0,   # Lambda
    1.0,   # Z
])


def _safe_pow(base, exp: float):
    """base**exp with a small positive floor to avoid 0**0 / negative issues."""
    return np.power(np.maximum(base, 0.0) + TINY, exp)


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -60, 60)))


@dataclass
class EventRecord:
    t: float
    kind: str
    civ: int
    node: int = -1
    detail: str = ""


@dataclass
class Simulation:
    """A single Monte-Carlo history of the deep-time model."""

    params: Params
    rng: np.random.Generator = field(init=False)
    graph: SpaceGraph = field(init=False)
    t: float = 0.0
    step_count: int = 0

    x: np.ndarray = field(init=False)          # (C, n, N_VARS)
    A_dom: np.ndarray = field(init=False)      # (C, n, N_DOMAINS)
    A_max_dom: np.ndarray = field(init=False)  # (C, n, N_DOMAINS) rising ceilings
    Gamma: np.ndarray = field(init=False)      # (C, n) chronal tech
    Omega: np.ndarray = field(init=False)      # (C, n) escape coherence
    ideas: np.ndarray = field(init=False)      # (C, n, n_ideas)
    psi: np.ndarray = field(init=False)        # (n,) Field state per node

    occ: np.ndarray = field(init=False)        # (C, n) occupancy in {0,1}
    alive: np.ndarray = field(init=False)      # (C,) civ alive flags
    capital: np.ndarray = field(init=False)    # (C,) capital node index
    war_state: np.ndarray = field(init=False)  # (C, C) at-war flags
    universe_idx: np.ndarray = field(init=False)  # (C,) aeonic position U_k
    last_aeon: np.ndarray = field(init=False)  # (C,) time of last transition

    events: List[EventRecord] = field(default_factory=list)
    records: List[dict] = field(default_factory=list)

    # -- construction -----------------------------------------------------
    def __post_init__(self) -> None:
        p = self.params
        self.rng = np.random.default_rng(p.seed)
        self.graph = build_space_graph(p.n_nodes, self.rng)
        n = p.n_nodes
        C = MAX_CIV_SLOTS

        self.x = np.zeros((C, n, S.N_VARS))
        self.A_dom = np.zeros((C, n, S.N_DOMAINS))
        self.A_max_dom = np.full((C, n, S.N_DOMAINS), p.A_max)
        self.Gamma = np.zeros((C, n))
        self.Omega = np.zeros((C, n))
        self.ideas = np.zeros((C, n, p.n_ideas))
        self.psi = self.rng.normal(0.0, 0.1, size=n)

        self.occ = np.zeros((C, n), dtype=np.int8)
        self.alive = np.zeros(C, dtype=bool)
        self.capital = np.full(C, -1, dtype=int)
        self.war_state = np.zeros((C, C), dtype=bool)
        self.universe_idx = np.zeros(C, dtype=int)
        self.aeon_count = np.zeros(C, dtype=int)     # CCC crossovers (Image 2)
        self.last_aeon = np.full(C, -1.0e9)
        self.last_frag = np.full(C, -1.0e9)
        self.last_collapse = np.full((C, n), -1.0e9)
        self._contact_info: Dict = {}

        # per-step caches
        self._w = np.zeros((n, n))
        self._dfield = np.full((n, n), np.inf)
        self._war_damage_cache = np.zeros((C, n))
        self._cosmo_efactor = 1.0

        self._seed_civilizations()
        self.record()

    def _seed_civilizations(self) -> None:
        p = self.params
        n = p.n_nodes
        n_civ = min(p.n_civ, MAX_CIV_SLOTS)
        home = self.rng.choice(n, size=n_civ, replace=False)
        for a in range(n_civ):
            i = int(home[a])
            self.alive[a] = True
            self.capital[a] = i
            self.occ[a, i] = 1
            self.x[a, i, S.P] = self.rng.uniform(0.8, 1.2)
            self.x[a, i, S.A] = self.rng.uniform(0.3, 0.6)
            self.x[a, i, S.E] = self.rng.uniform(0.8, 1.5)
            self.x[a, i, S.R] = self.rng.uniform(8.0, 15.0)
            self.x[a, i, S.Y] = self.rng.uniform(0.5, 1.0)
            self.x[a, i, S.Q] = self.rng.uniform(0.2, 0.5)
            self.x[a, i, S.L] = self.rng.uniform(1.0, 1.5)
            self.x[a, i, S.PHI] = self.rng.uniform(0.0, 0.2)
            self.x[a, i, S.G] = self.rng.uniform(0.55, 0.75)
            self.x[a, i, S.I] = self.rng.uniform(0.1, 0.3)
            self.x[a, i, S.M] = self.rng.uniform(0.2, 0.4)
            self.x[a, i, S.C] = self.rng.uniform(0.5, 1.0)
            self.x[a, i, S.LAM] = self.rng.uniform(0.5, 0.7)
            self.x[a, i, S.Z] = self.rng.uniform(0.4, 0.6)
            # Seed every domain at the aggregate value so that the reconstructed
            # aggregate A = sum_m omega_m A^m (weights sum to 1) equals the seed.
            self.A_dom[a, i, :] = self.x[a, i, S.A]
            self.ideas[a, i, :] = self.rng.uniform(0.1, 0.9, size=p.n_ideas)

    # -- helpers ----------------------------------------------------------
    def alive_indices(self) -> List[int]:
        return [a for a in range(MAX_CIV_SLOTS) if self.alive[a]]

    def _free_slot(self) -> Optional[int]:
        for a in range(MAX_CIV_SLOTS):
            if not self.alive[a]:
                return a
        return None

    def effective_cognition(self) -> np.ndarray:
        p = self.params
        H = p.h_bio * self.x[..., S.P]
        self.x[..., S.H] = H
        Dcult = self._node_cultural_spread()
        pen = np.exp(-p.chi_I * self._inorm() - p.chi_C * self.x[..., S.C] - p.chi_D * Dcult)
        return H * pen

    def _inorm(self) -> np.ndarray:
        I = self.x[..., S.I]
        return I / (1.0 + I)

    def _node_cultural_spread(self) -> np.ndarray:
        p = self.params
        spread = np.zeros((MAX_CIV_SLOTS, p.n_nodes))
        w = np.ones(p.n_ideas)
        for a in self.alive_indices():
            k = self.capital[a]
            if k < 0:
                continue
            diff = self.ideas[a, :, :] - self.ideas[a, k, :][None, :]
            spread[a] = np.sqrt(np.sum(w[None, :] * diff * diff, axis=1))
        return spread

    def unrest(self) -> np.ndarray:
        return np.clip(U_FROM_I * self._inorm() + U_FROM_L * (1.0 - self.x[..., S.LAM]), 0, 3)

    def _civ_totals(self) -> Dict[str, np.ndarray]:
        return {
            "P": np.sum(self.x[..., S.P] * self.occ, axis=1),
            "E": np.sum(self.x[..., S.E] * self.occ, axis=1),
            "M": np.sum(self.x[..., S.M] * self.occ, axis=1),
            "Y": np.sum(self.x[..., S.Y] * self.occ, axis=1),
            "R": np.sum(self.x[..., S.R] * self.occ, axis=1),
            "nodes": np.sum(self.occ, axis=1),
        }

    # -- cosmic time (Images 1, 4-5) -------------------------------------
    def cosmic_years(self, t: float) -> float:
        """Map integration time t to 'years in Earth's future' (log-uniform)."""
        p = self.params
        frac = min(max(t / max(p.t_max, TINY), 0.0), 1.0)
        return float(p.cosmic_year0 * (p.cosmic_year_end / p.cosmic_year0) ** frac)

    def cosmic_age(self, t: float) -> float:
        """Total cosmic age (years after the Big Bang) at integration time t."""
        return S.UNIVERSE_AGE_NOW + self.cosmic_years(t)

    # -- Field graph ------------------------------------------------------
    def _refresh_field(self) -> None:
        """Recompute Field weights every step (cheap) but the shortest-path
        distances only every ``FIELD_REFRESH`` steps -- ``psi`` diffuses slowly
        so the distances are effectively piecewise-constant over a few steps."""
        self._w = self.graph.field_weights(self.psi, self.params)
        if self.step_count % FIELD_REFRESH == 0 or not np.isfinite(self._dfield).any():
            self._dfield = self.graph.field_distance(self._w, self.params.field_eps)

    def step_field(self, dt: float) -> None:
        p = self.params
        lap = self.graph.field_laplacian(self._w)
        forcing = 0.02 * np.max(self.x[..., S.PHI] * self.occ, axis=0)
        drift = (
            -p.D_Phi * (lap @ self.psi)
            - p.alpha_Phi_damp * self.psi
            - p.beta_Phi_sat * self.psi ** 3
            + forcing
        )
        noise = p.sigma_Phi_field * self.rng.normal(0.0, np.sqrt(dt), size=p.n_nodes)
        self.psi = np.clip(self.psi + drift * dt + noise, -10, 10)

    # -- continuous drift (sections 7-29) --------------------------------
    def continuous_drift(self, Heff: np.ndarray) -> np.ndarray:
        p = self.params
        x = self.x
        occ = self.occ.astype(float)
        dfield = self._dfield
        dx = np.zeros_like(x)

        P = x[..., S.P]; A = x[..., S.A]; E = x[..., S.E]; R = x[..., S.R]
        Y = x[..., S.Y]; Q = x[..., S.Q]; L = x[..., S.L]; Phi = x[..., S.PHI]
        G = x[..., S.G]; I = x[..., S.I]; M = x[..., S.M]; C = x[..., S.C]
        Lam = x[..., S.LAM]; Zz = x[..., S.Z]
        Inorm = self._inorm()
        U = self.unrest()
        Dcult = self._node_cultural_spread()
        wd = self._war_damage_cache
        disruption = np.clip(U + wd, 0, 5)

        # population (section 7)
        Kpop = (p.K0 * _safe_pow(R, p.rho_R) * _safe_pow(E, p.rho_E)
                * _safe_pow(Y, p.rho_Y) * _safe_pow(L, p.rho_L))
        dx[..., S.P] = p.pop_r * P * (1.0 - P / np.maximum(Kpop, TINY)) - p.pop_mu * P

        # longevity (section 8)
        dx[..., S.L] = (p.g_L * _safe_pow(A, p.ell_A) * _safe_pow(Q, p.ell_Q)
                        * _safe_pow(Y, p.ell_Y) * (1.0 - L / p.L_max) - p.delta_L * L)

        # energy (section 13) -- stellar & galactic tiers fade with cosmic era
        # (Image 3: energy access declines toward the Degenerate Era), while the
        # Field-tapped tier persists: in this universe the Field is the constant.
        sf = self._cosmo_efactor
        Emax = (p.E_planet + (p.E_stellar + p.E_galactic) * sf
                + p.E_field * np.clip(Phi / p.Phi_max, 0, 1))
        dx[..., S.E] = (p.g_E * _safe_pow(A, p.e_A) * _safe_pow(Y, p.e_Y) * E
                        * (1.0 - E / np.maximum(Emax, TINY)) - p.delta_E * E)

        # resources (section 14)
        used_frac = np.clip(1.0 - R / p.R_total_node, 0, 1)
        extraction = p.x0_extract * _safe_pow(Y, p.x_Y) * _safe_pow(A, p.x_A) * (1.0 - used_frac)
        recycle = p.recycle * (p.c_P * P + p.c_Y * Y)
        dx[..., S.R] = extraction - p.c_P * P - p.c_Y * Y - p.c_E * E - p.c_M * M + recycle

        # industry (section 15)
        dx[..., S.Y] = (p.g_Y * _safe_pow(E, p.y_E) * _safe_pow(R, p.y_R) * _safe_pow(Q, p.y_Q)
                        * _safe_pow(A, p.y_A) * (1.0 - Y / p.Y_max) - p.delta_Y * Y)

        # computation (section 12)
        Qmax = p.q0 * _safe_pow(E, p.xi_E) * _safe_pow(R, p.xi_R) * _safe_pow(Phi, p.xi_Phi)
        dx[..., S.Q] = (p.g_Q * _safe_pow(A, p.q_A) * _safe_pow(E, p.q_E) * _safe_pow(Y, p.q_Y)
                        * (1.0 - Q / np.maximum(Qmax, TINY)) - p.delta_Q * Q)

        # knowledge domains (section 10)  -- growth/decay; transfer handled elsewhere
        grow = (p.eta_know * _safe_pow(Heff, p.alpha_know)[..., None] * _safe_pow(Q, p.beta_know)[..., None]
                * _safe_pow(self.A_dom, p.theta_know)
                * (1.0 - self.A_dom / np.maximum(self.A_max_dom, TINY)))
        decay = p.delta_A * disruption[..., None] * self.A_dom
        self._dA_dom = grow - decay

        # Field mastery (section 16)
        Afield = self.A_dom[..., S.DOM_FIELD]
        dx[..., S.PHI] = (p.g_Phi * _safe_pow(Afield, p.phi_A) * _safe_pow(Q, p.phi_Q)
                          * _safe_pow(E, p.phi_E) * (1.0 - Phi / p.Phi_max)
                          - p.delta_Phi * disruption * Phi)

        # chronal tech (section 19)
        Aaeon = self.A_dom[..., S.DOM_AEON]
        chronal_gate = (Phi >= p.Phi_chronal).astype(float)
        self._dGamma = (p.g_Gamma * Aaeon * Q * E * (1.0 - self.Gamma / p.Gamma_max) * chronal_gate
                        - p.delta_Gamma * self.Gamma)

        # escape coherence (section 37)
        self._dOmega = (p.g_Omega * Q * Phi * E * (1.0 - self.Omega)
                        - p.delta_Omega * (disruption + 1.0) * self.Omega)

        # inequality (section 22): generated by the cross-node coefficient of
        # variation of energy, longevity and computation within each civ, then
        # reduced by redistribution and relaxation.
        gen = np.zeros((MAX_CIV_SLOTS, p.n_nodes))
        for a in self.alive_indices():
            occ_nodes = np.where(self.occ[a] > 0)[0]
            if len(occ_nodes) == 0:
                continue
            def _cv(v):
                mu = v.mean()
                return float(v.var() / max(mu * mu, TINY))
            g = p.g_I * (p.omega_E * _cv(E[a, occ_nodes]) + p.omega_L * _cv(L[a, occ_nodes])
                         + p.omega_Q * _cv(Q[a, occ_nodes]))
            gen[a, occ_nodes] = g
        dx[..., S.I] = gen - p.r_I * p.redistribution - p.delta_I * I

        # legitimacy (section 23)
        wellbeing = np.clip(0.2 + 0.3 * np.tanh(R / np.maximum(P, TINY)) - 0.3 * Inorm, 0, 1)
        security = np.clip(1.0 - wd, 0, 1)
        dx[..., S.LAM] = (p.g_Lam * (p.w_wellbeing * wellbeing + p.w_security * security
                                     + p.w_continuity * Zz)
                          - p.d_Lam * (Inorm + U + (1.0 - G)))

        # administrative complexity (section 24) with soft ceiling
        mean_dfield = self._mean_internal_field_distance()
        dC_grow = p.g_C * (p.alpha_Pc * P + p.alpha_Vc * self.occ.sum(axis=1, keepdims=True)
                           + p.alpha_Dc * mean_dfield + p.alpha_Hc * self.x[..., S.H])
        dx[..., S.C] = dC_grow * (1.0 - C / p.C_max) - p.r_C * Q - p.delta_C * C

        # governability (section 25) & institutional stability (section 26).
        # R/(P+1) keeps the resource-slack term finite as population -> 0.
        Qgov = self._governability(Dcult)
        dx[..., S.G] = (p.a_Q * Qgov + p.a_R * R / (P + 1.0) + p.a_Lam * Lam + p.a_Z * Zz
                        - p.a_C * (C / p.gov_C0) - p.a_I * Inorm - p.a_U * U - p.a_W * wd)

        # military (section 27) with soft ceiling
        dx[..., S.M] = (p.g_M * _safe_pow(Y, p.m_Y) * _safe_pow(E, p.m_E) * _safe_pow(A, p.m_A)
                        * _safe_pow(Q, p.m_Q) * (1.0 - M / p.M_max) - p.delta_M * M)

        # archives (section 29).  Z is a [0,1] integrity index, so the build
        # term Q*Y is passed through a saturating response and driven toward the
        # (1-Z) headroom -- this keeps the drift bounded (Z is not an unbounded
        # stock) and avoids pinning the adaptive step to its floor.
        build = (Q * Y) / (1.0 + Q * Y)
        # War damage to Z (the -chi_W D^war term of section 29) is applied once,
        # in _apply_maintenance_and_war_losses, matching the E/Y/M/P war losses.
        dx[..., S.Z] = p.g_Z * build * (1.0 - Zz) - p.delta_Z * Zz

        dx *= occ[..., None]
        return dx

    def _governability(self, Dcult: np.ndarray) -> np.ndarray:
        p = self.params
        Qgov = np.zeros((MAX_CIV_SLOTS, p.n_nodes))
        Phi = self.x[..., S.PHI]
        dfield = self._dfield
        for a in self.alive_indices():
            k = self.capital[a]
            if k < 0:
                continue
            phi_pair = np.minimum(Phi[a], Phi[a, k])
            tau_com = TAU_COM0 * np.exp(-GAMMA_PHI_COM * phi_pair)
            v = (V0_TRANSP * _safe_pow(Phi[a, k], NU_TRANSP)
                 * _safe_pow(self.x[a, k, S.E], EPS_TRANSP)
                 * _safe_pow(self.x[a, k, S.Q], ZETA_TRANSP)) + TINY
            tau_transp = dfield[k] / v
            tau_transp = np.where(np.isfinite(tau_transp), tau_transp, 50.0)
            expo = -(tau_com / p.gov_TD + tau_transp / p.gov_TM
                     + Dcult[a] / p.gov_D0 + self.x[a, :, S.C] / p.gov_C0)
            Qgov[a] = np.exp(np.clip(expo, -60, 0))
        return Qgov

    def _mean_internal_field_distance(self) -> np.ndarray:
        out = np.zeros((MAX_CIV_SLOTS, 1))
        dfield = self._dfield
        for a in self.alive_indices():
            k = self.capital[a]
            occ_nodes = np.where(self.occ[a] > 0)[0]
            if k < 0 or len(occ_nodes) == 0:
                continue
            d = dfield[k, occ_nodes]
            d = d[np.isfinite(d)]
            out[a, 0] = float(np.mean(d)) if len(d) else 0.0
        return out

    # -- integration ------------------------------------------------------
    def _adaptive_dt(self, dx: np.ndarray) -> float:
        p = self.params
        occ = self.occ.astype(bool)
        if not np.any(occ):
            return p.dt_max
        scale = np.maximum(np.abs(self.x), VAR_SCALE[None, None, :])
        rel = np.abs(dx) / scale
        rel = rel * occ[..., None]
        m = float(np.max(rel)) if rel.size else 0.0
        if m <= TINY:
            return p.dt_max
        return float(np.clip(p.adapt_eps / m, p.dt_min, p.dt_max))

    def step(self) -> None:
        p = self.params
        self._war_damage_cache = np.zeros((MAX_CIV_SLOTS, p.n_nodes))

        self._cosmo_efactor = S.cosmo_energy_factor(self.cosmic_age(self.t))
        self._refresh_field()
        Heff = self.effective_cognition()
        self._Heff = Heff              # effective cognition, reused by events
        self._contact_info = self._contacts()
        self._compute_war_damage()

        dx = self.continuous_drift(Heff)
        dt = self._adaptive_dt(dx)

        occ = self.occ.astype(bool)
        self.x += dx * dt
        self.x[..., S.G] += p.sigma_G * self.rng.normal(0, np.sqrt(dt), size=self.x[..., S.G].shape) * occ
        self.x[..., S.PHI] += p.sigma_Phi_civ * self.rng.normal(0, np.sqrt(dt), size=self.x[..., S.PHI].shape) * occ

        self.A_dom += self._dA_dom * dt
        self.A_dom += p.sigma_A * self.rng.normal(0, np.sqrt(dt), size=self.A_dom.shape) * occ[..., None]
        self._diffuse_knowledge(dt)
        self.Gamma += self._dGamma * dt
        self.Omega += self._dOmega * dt
        self._evolve_ideas(dt)

        Aw = np.asarray(p.dom_weights)
        self.x[..., S.A] = np.sum(self.A_dom * Aw[None, None, :], axis=2)

        # discrete events
        self._apply_maintenance_and_war_losses(dt)
        self._sample_war_transitions(dt)
        self._sample_breakthroughs(dt)
        self._sample_field_breakthroughs(dt)
        self._migrate(dt)
        self._colonize(dt)
        self._sample_collapse(dt)
        self._sample_fragmentation(dt)
        self._sample_merger(dt)
        self._sample_aeonic(dt)

        self.step_field(dt)
        self.enforce_constraints()
        self._cull_dead_civs()

        self.t += dt
        self.step_count += 1

    # -- knowledge diffusion & culture -----------------------------------
    def _diffuse_knowledge(self, dt: float) -> None:
        p = self.params
        if p.kappa_transfer <= 0:
            return
        wn = self._w / (np.max(self._w) + TINY)
        for a in self.alive_indices():
            occ_nodes = np.where(self.occ[a] > 0)[0]
            if len(occ_nodes) < 2:
                continue
            sub = wn[np.ix_(occ_nodes, occ_nodes)]
            deg = sub.sum(axis=1)
            vals = self.A_dom[a, occ_nodes, :]                # (k, D)
            flux = p.kappa_transfer * (sub @ vals - vals * deg[:, None])
            self.A_dom[a, occ_nodes, :] += flux * dt

    def _evolve_ideas(self, dt: float) -> None:
        """Cultural idea dynamics p_aim with isolation-driven divergence (sec. 21).

        Exchange between Field-close nodes homogenises culture; the further a
        province sits (in Field distance) from its capital, the more it drifts,
        so far-flung empires diverge and can fragment."""
        p = self.params
        occ = self.occ.astype(bool)
        pmat = self.ideas
        drift = p.cult_beta * pmat * (1.0 - pmat) - p.cult_gamma * pmat
        wn = self._w / (np.max(self._w) + TINY)
        iso = np.zeros((MAX_CIV_SLOTS, p.n_nodes))
        for a in self.alive_indices():
            occ_nodes = np.where(self.occ[a] > 0)[0]
            k = self.capital[a]
            if len(occ_nodes) >= 2:
                sub = wn[np.ix_(occ_nodes, occ_nodes)]
                deg = sub.sum(axis=1)
                vals = pmat[a, occ_nodes, :]
                flux = p.cult_transfer * (sub @ vals - vals * deg[:, None])
                drift[a, occ_nodes, :] += flux
            if k >= 0:
                d = self._dfield[k, occ_nodes]
                iso[a, occ_nodes] = np.where(np.isfinite(d), np.clip(d / p.gov_D0, 0, 4), 4.0)
        noise_scale = 0.01 + p.cult_div0 * iso[..., None]
        noise = noise_scale * self.rng.normal(0, np.sqrt(dt), size=pmat.shape)
        self.ideas = np.clip(pmat + drift * dt * occ[..., None] + noise * occ[..., None], 0, 1)

    # -- breakthroughs (section 11) --------------------------------------
    def _sample_breakthroughs(self, dt: float) -> None:
        p = self.params
        occ = self.occ.astype(bool)
        Heff = self._Heff              # effective cognition (section 9), not raw H
        Q = self.x[..., S.Q]
        Inorm = self._inorm()
        G = self.x[..., S.G]
        # Saturating dependence on cognition, computation and knowledge keeps the
        # breakthrough hazard bounded: without this, mature Q ~ 1e2-1e3 would make
        # the hazard enormous and paradigm jumps would fire every step.
        base = (p.lam0_break * (1 + p.alpha_H * np.tanh(Heff / 5.0))
                * (1 + p.alpha_Q * np.tanh(Q / 50.0))
                * np.exp(-p.alpha_Ibr * Inorm - p.alpha_Gbr * (1 - G)))
        lam = base[..., None] * (1 + p.alpha_A * np.tanh(self.A_dom / 10.0))  # (C, n, D)
        prob = 1 - np.exp(-lam * dt)
        draws = self.rng.random(lam.shape)
        hit = (draws < prob) & occ[..., None]
        if np.any(hit):
            self.A_max_dom[hit] += p.dA_max
            self.A_dom[hit] += p.dA_jump
            for a, i, m in np.argwhere(hit):
                self.events.append(EventRecord(self.t, "breakthrough", int(a), int(i),
                                               S.DOMAIN_NAMES[m]))

    def _sample_field_breakthroughs(self, dt: float) -> None:
        p = self.params
        # Only nodes still below the Field-mastery ceiling can have a Field
        # paradigm jump; the knowledge dependence is bounded to avoid a storm of
        # events once field science is deep.
        headroom = self.x[..., S.PHI] < (p.Phi_max - 1.0e-3)
        occ = self.occ.astype(bool) & headroom
        lam = p.lam_Phi_jump * (1 + np.tanh(self.A_dom[..., S.DOM_FIELD] / 10.0))
        prob = 1 - np.exp(-lam * dt)
        hit = (self.rng.random(prob.shape) < prob) & occ
        if np.any(hit):
            self.x[..., S.PHI][hit] += p.dPhi_jump
            for a, i in np.argwhere(hit):
                tier = S.field_tier(self.x[int(a), int(i), S.PHI])
                self.events.append(EventRecord(self.t, "field_breakthrough", int(a), int(i), tier))

    # -- conflict (section 28) -------------------------------------------
    def _contacts(self):
        alive = self.alive_indices()
        adj = self._w > 0
        info = {}
        for idx, a in enumerate(alive):
            nodes_a = np.where(self.occ[a] > 0)[0]
            if len(nodes_a) == 0:
                continue
            for b in alive[idx + 1:]:
                nodes_b = np.where(self.occ[b] > 0)[0]
                if len(nodes_b) == 0:
                    continue
                border = adj[np.ix_(nodes_a, nodes_b)]
                n_border = int(np.sum(border))
                if n_border == 0:
                    continue
                pa = self.ideas[a, nodes_a].mean(axis=0)
                pb = self.ideas[b, nodes_b].mean(axis=0)
                dcult = float(np.sqrt(np.sum((pa - pb) ** 2)))
                info[(a, b)] = {"border": n_border, "dcult": dcult,
                                "nodes_a": nodes_a, "nodes_b": nodes_b}
        return info

    def _war_logit(self, a: int, b: int, c: dict, totals, inorm_civ) -> float:
        """Conflict logit for the pair (a, b) (section 28)."""
        p = self.params
        Ma, Mb = totals["M"][a], totals["M"][b]
        Ra, Rb = totals["R"][a], totals["R"][b]
        Pa, Pb = totals["P"][a], totals["P"][b]
        terr = c["border"] / (min(len(c["nodes_a"]), len(c["nodes_b"])) + TINY)
        res_scarcity = 1.0 / (1.0 + (Ra + Rb) / (Pa + Pb + TINY))
        ineq = float(inorm_civ[a].mean() + inorm_civ[b].mean())
        deterrence = min(Ma, Mb) / (abs(Ma - Mb) + 1.0)
        trade = np.exp(-c["dcult"]) * c["border"] * 0.1
        return (p.war_bias + p.war_alpha_R * res_scarcity + p.war_alpha_T * terr
                + p.war_alpha_I * ineq + p.war_alpha_C * c["dcult"]
                - p.war_alpha_D * deterrence - p.war_alpha_X * trade)

    def _compute_war_damage(self) -> None:
        """Damage rate D^war from currently-active wars (section 28)."""
        p = self.params
        totals = self._civ_totals()
        damage = np.zeros((MAX_CIV_SLOTS, p.n_nodes))
        for (a, b), c in self._contact_info.items():
            if not self.war_state[a, b]:
                continue
            Ma, Mb = totals["M"][a], totals["M"][b]
            da = p.war_damage * Mb / (1.0 + Ma) * 0.1
            db = p.war_damage * Ma / (1.0 + Mb) * 0.1
            damage[a, c["nodes_a"]] += da
            damage[b, c["nodes_b"]] += db
        self._war_damage_cache = np.clip(damage, 0, 5)

    def _sample_war_transitions(self, dt: float) -> None:
        """Sample war onset / peace as dt-scaled hazards (section 28)."""
        totals = self._civ_totals()
        inorm_civ = self._inorm()
        for (a, b), c in self._contact_info.items():
            if not (self.alive[a] and self.alive[b]):
                continue
            pwar = float(sigmoid(self._war_logit(a, b, c, totals, inorm_civ)))
            if not self.war_state[a, b]:
                rate = WAR_ONSET_RATE * pwar
                if self.rng.random() < 1 - np.exp(-rate * dt):
                    self.war_state[a, b] = self.war_state[b, a] = True
                    self.events.append(EventRecord(self.t, "war_start", a, -1, f"vs {b}"))
            else:
                rate = WAR_PEACE_RATE * (1 - pwar)
                if self.rng.random() < 1 - np.exp(-rate * dt):
                    self.war_state[a, b] = self.war_state[b, a] = False
                    self.events.append(EventRecord(self.t, "war_end", a, -1, f"vs {b}"))

    def _apply_maintenance_and_war_losses(self, dt: float) -> None:
        p = self.params
        wd = self._war_damage_cache
        self.x[..., S.E] -= (0.5 * wd + 0.01 * self.x[..., S.M]) * self.x[..., S.E] * dt
        self.x[..., S.Y] -= wd * self.x[..., S.Y] * dt
        self.x[..., S.M] -= wd * self.x[..., S.M] * dt
        self.x[..., S.P] -= 0.5 * wd * self.x[..., S.P] * dt
        self.x[..., S.Z] -= p.chi_W * wd * self.x[..., S.Z] * dt

    # -- migration & colonization (section 20) ---------------------------
    def _migrate(self, dt: float) -> None:
        p = self.params
        if p.migrate_m0 <= 0:
            return
        dfield = self._dfield
        for a in self.alive_indices():
            occ_nodes = np.where(self.occ[a] > 0)[0]
            k = len(occ_nodes)
            if k < 2:
                continue
            R = self.x[a, occ_nodes, S.R]; G = self.x[a, occ_nodes, S.G]
            L = self.x[a, occ_nodes, S.L]; P = self.x[a, occ_nodes, S.P]
            Inorm = self._inorm()[a, occ_nodes]; W = self._war_damage_cache[a, occ_nodes]
            attract = np.exp(np.clip(0.05 * R + 0.5 * G + 0.1 * L - 0.5 * W - 0.5 * Inorm, -30, 30))
            tau = dfield[np.ix_(occ_nodes, occ_nodes)]
            kernel = np.where(np.isfinite(tau), np.exp(-tau / p.migrate_tau), 0.0)
            np.fill_diagonal(kernel, 0.0)
            # Section 20: M_aij = m0 P_ai exp(-tau/tau_M) A_aij with destination-
            # only attractiveness A_aij (no reciprocal source term).
            flow = (p.migrate_m0 * P[:, None] * kernel * attract[None, :]) * dt
            outflow = flow.sum(axis=1)
            cap = 0.2 * P
            scale = np.where(outflow > cap, cap / (outflow + TINY), 1.0)
            flow *= scale[:, None]
            net = flow.sum(axis=0) - flow.sum(axis=1)
            self.x[a, occ_nodes, S.P] += net

    def _colonize(self, dt: float) -> None:
        p = self.params
        dfield = self._dfield
        occupied_any = np.any(self.occ > 0, axis=0)
        empty = np.where(~occupied_any)[0]
        if len(empty) == 0:
            return
        claims = {}  # node -> (civ, src, hazard)
        for a in self.alive_indices():
            occ_nodes = np.where((self.occ[a] > 0) & (self.x[a, :, S.P] >= 0.5))[0]
            if len(occ_nodes) == 0:
                continue
            Y = self.x[a, occ_nodes, S.Y]; E = self.x[a, occ_nodes, S.E]
            Phi = self.x[a, occ_nodes, S.PHI]
            strength = (p.col_lam0 * _safe_pow(Y, p.col_chi_Y) * _safe_pow(E, p.col_chi_E)
                        * _safe_pow(Phi, p.col_chi_Phi))                 # (k,)
            d = dfield[np.ix_(occ_nodes, empty)]                          # (k, m)
            lam = strength[:, None] * np.exp(-d / p.col_length)
            lam = np.where(np.isfinite(d), lam, 0.0)
            prob = 1 - np.exp(-lam * dt)
            draws = self.rng.random(prob.shape)
            hits = draws < prob
            for jj, j in enumerate(empty):
                col = np.where(hits[:, jj])[0]
                if len(col) == 0:
                    continue
                best = col[int(np.argmax(lam[col, jj]))]
                haz = lam[best, jj]
                if j not in claims or haz > claims[j][2]:
                    claims[j] = (a, int(occ_nodes[best]), float(haz))
        for j, (a, src, _) in claims.items():
            self._establish_colony(a, src, j)

    def _establish_colony(self, a: int, src: int, j: int) -> None:
        p = self.params
        seed_pop = 0.3 * self.x[a, src, S.P]
        self.x[a, src, S.P] -= seed_pop
        self.occ[a, j] = 1
        self.x[a, j, :] = 0.0
        self.x[a, j, S.P] = max(seed_pop, 0.2)
        for v in (S.A, S.E, S.Y, S.Q, S.L, S.PHI, S.M):
            self.x[a, j, v] = 0.5 * self.x[a, src, v]
        self.x[a, j, S.R] = p.R_total_node * 0.6
        self.x[a, j, S.G] = self.x[a, src, S.G]
        self.x[a, j, S.LAM] = self.x[a, src, S.LAM]
        self.x[a, j, S.Z] = self.x[a, src, S.Z]
        self.x[a, j, S.C] = 0.3 * self.x[a, src, S.C]
        self.A_dom[a, j, :] = 0.5 * self.A_dom[a, src, :]
        self.A_max_dom[a, j, :] = self.A_max_dom[a, src, :]
        # A founding colony carries its parent's culture but mutates it, so
        # distant provinces can drift apart and eventually fragment (section 21).
        self.ideas[a, j, :] = np.clip(
            self.ideas[a, src, :] + self.rng.normal(0.0, 0.15, size=p.n_ideas), 0, 1)
        self.events.append(EventRecord(self.t, "colonization", a, int(j), f"from {src}"))

    # -- collapse (section 30) -------------------------------------------
    def _sample_collapse(self, dt: float) -> None:
        p = self.params
        x = self.x
        occ = self.occ.astype(bool)
        Inorm = self._inorm()
        U = self.unrest()
        disruption = np.clip(U + self._war_damage_cache, 0, 5)
        CR = x[..., S.C] / (x[..., S.R] + p.field_eps)
        # Section 30 exponent: complexity/resource strain, inequality, unrest,
        # war and disruption raise the hazard; institutions (G), archives (Z) and
        # resilience (legitimacy Lambda, the model's R_ai shield) lower it.
        h = p.h0_collapse * np.exp(np.clip(
            p.b_CR * CR + p.b_I * Inorm + p.b_U * U + p.b_W * self._war_damage_cache
            + B_D_COLLAPSE * disruption
            - p.b_G * x[..., S.G] - p.b_Z * x[..., S.Z] - p.b_resil * x[..., S.LAM], -60, 60))
        prob = 1 - np.exp(-h * dt)
        ready = (self.t - self.last_collapse) >= COLLAPSE_COOLDOWN
        hit = (self.rng.random(prob.shape) < prob) & occ & ready
        for a, i in np.argwhere(hit):
            self.last_collapse[int(a), int(i)] = self.t
            self._apply_collapse(int(a), int(i))

    def _apply_collapse(self, a: int, i: int) -> None:
        p = self.params
        loss = p.collapse_loss
        chi_A = loss["A"] * float(np.exp(-p.rho_Z * self.x[a, i, S.Z]))
        for name, idx in zip(S.VAR_NAMES, range(S.N_VARS)):
            if name in ("I", "C"):
                self.x[a, i, idx] *= (1.0 + loss.get(name, 0.0))
            elif name == "A":
                self.x[a, i, idx] *= (1.0 - chi_A)
                self.A_dom[a, i, :] *= (1.0 - chi_A)
            else:
                self.x[a, i, idx] *= (1.0 - loss.get(name, 0.0))
        self.events.append(EventRecord(self.t, "collapse", a, i))

    # -- fragmentation & merger (sections 31-32) -------------------------
    def _sample_fragmentation(self, dt: float) -> None:
        p = self.params
        spread_all = self._node_cultural_spread()
        for a in self.alive_indices():
            if self.t - self.last_frag[a] < FRAG_COOLDOWN:
                continue
            occ_nodes = np.where(self.occ[a] > 0)[0]
            if len(occ_nodes) < 4:
                continue
            Gmean = float(np.mean(np.clip(self.x[a, occ_nodes, S.G], 0, 1)))
            if Gmean < p.G_crit and float(np.max(spread_all[a, occ_nodes])) > p.D_crit:
                self._fragment(a, occ_nodes)

    def _fragment(self, a: int, occ_nodes) -> None:
        split = spectral_two_split(self._w, list(occ_nodes))
        if split is None:
            return
        left, right = split
        if self.capital[a] in right:
            left, right = right, left
        b = self._free_slot()
        if b is None:
            return
        self.alive[b] = True
        self.universe_idx[b] = self.universe_idx[a]
        self.aeon_count[b] = self.aeon_count[a]
        self.last_aeon[b] = -1.0e9
        self.last_frag[a] = self.t
        self.last_frag[b] = self.t
        for j in right:
            self.occ[a, j] = 0
            self.occ[b, j] = 1
            self.x[b, j, :] = self.x[a, j, :]
            self.A_dom[b, j, :] = self.A_dom[a, j, :]
            self.A_max_dom[b, j, :] = self.A_max_dom[a, j, :]
            self.Gamma[b, j] = self.Gamma[a, j]
            self.Omega[b, j] = self.Omega[a, j]
            self.ideas[b, j, :] = self.ideas[a, j, :]
            self.x[a, j, :] = 0.0
        right = np.asarray(right)
        self.capital[b] = int(right[int(np.argmax(self.x[b, right, S.P]))])
        self.x[b, right, S.G] *= 0.7
        self.events.append(EventRecord(self.t, "fragmentation", a, -1, f"-> {b}"))

    def _sample_merger(self, dt: float) -> None:
        p = self.params
        totals = self._civ_totals()
        inorm_civ = self._inorm()
        dfield = self._dfield
        for (a, b), c in self._contact_info.items():
            if self.war_state[a, b] or not (self.alive[a] and self.alive[b]):
                continue
            # Benefit terms are bounded synergies in ~[0,1]: cultural affinity,
            # mutual security, and economic complementarity.  (Using absolute
            # industry here would make every contact merge instantly.)
            n_share = min(len(c["nodes_a"]), len(c["nodes_b"]))
            Ta = np.exp(-c["dcult"]) * min(1.0, c["border"] / (n_share + TINY))
            Sa = 1.0 / (1.0 + abs(totals["M"][a] - totals["M"][b]))
            Ka = float(np.tanh((totals["Y"][a] + totals["Y"][b]) / 100.0))
            benefit = p.merge_benefit_T * Ta + p.merge_benefit_S * Sa + p.merge_benefit_K * Ka
            nodes = np.concatenate([c["nodes_a"], c["nodes_b"]])
            dsub = dfield[np.ix_(nodes, nodes)]
            dsub = dsub[np.isfinite(dsub)]
            mean_d = float(np.mean(dsub)) if dsub.size else 5.0
            cost = (p.merge_cost_C * c["dcult"] + p.merge_cost_D * mean_d
                    + p.merge_cost_I * float(inorm_civ[a].mean() + inorm_civ[b].mean()))
            if benefit > cost:
                rate = MERGE_RATE * float(np.clip(benefit - cost, 0, 5))
                if self.rng.random() < 1 - np.exp(-rate * dt):
                    self._merge(a, b)

    def _merge(self, a: int, b: int) -> None:
        for j in np.where(self.occ[b] > 0)[0]:
            self.occ[a, j] = 1
            self.occ[b, j] = 0
            self.x[a, j, :] = self.x[b, j, :]
            self.A_dom[a, j, :] = self.A_dom[b, j, :]
            self.A_max_dom[a, j, :] = self.A_max_dom[b, j, :]
            self.Gamma[a, j] = self.Gamma[b, j]
            self.Omega[a, j] = self.Omega[b, j]
            self.ideas[a, j, :] = self.ideas[b, j, :]
        self.alive[b] = False
        self.capital[b] = -1
        self.war_state[b, :] = self.war_state[:, b] = False
        self.events.append(EventRecord(self.t, "merger", a, -1, f"absorbed {b}"))

    # -- aeonic (sections 33-34) -----------------------------------------
    def _sample_aeonic(self, dt: float) -> None:
        p = self.params
        for a in self.alive_indices():
            if self.t - self.last_aeon[a] < p.aeon_cooldown:
                continue
            occ_nodes = np.where(self.occ[a] > 0)[0]
            if len(occ_nodes) == 0:
                continue
            phis = self.x[a, occ_nodes, S.PHI]
            best = int(occ_nodes[int(np.argmax(phis))])
            Phi = self.x[a, best, S.PHI]
            if Phi < p.Phi_gate_min:
                continue
            Aaeon = self.A_dom[a, best, S.DOM_AEON]
            instab = abs(self.psi[best])                 # Field instability  (a5 term)
            # Singularity risk (a6 term of section 34): the tail risk of the
            # Field collapsing into a singularity, proxied by turbulent Field
            # state -- distinct from the linear instability penalty above.
            sing_risk = float(np.clip(self.psi[best] ** 2 / 9.0, 0, 1))
            logit = (p.gate_bias + p.gate_a1 * Phi + p.gate_a2 * Aaeon
                     + p.gate_a3 * self.x[a, best, S.E] + p.gate_a4 * self.x[a, best, S.Q]
                     - p.gate_a5 * instab - p.gate_a6 * sing_risk)
            pgate = float(sigmoid(logit))
            rate = p.aeon_rate * pgate
            if self.rng.random() < 1 - np.exp(-rate * dt):
                # Conformal crossover (Penrose CCC, Image 2): advance one step
                # along the linked aeon sequence; the accessible-universe index
                # cycles with period P (section 33).
                self.aeon_count[a] += 1
                self.universe_idx[a] = self.aeon_count[a] % p.aeon_prime
                self.last_aeon[a] = self.t
                self.events.append(EventRecord(self.t, "aeonic_transition", a, best,
                                               f"aeon {self.aeon_count[a]} (U{self.universe_idx[a]})"))

    # -- constraints (section 39) ----------------------------------------
    def enforce_constraints(self) -> None:
        for idx in S.NONNEGATIVE_VARS:
            np.maximum(self.x[..., idx], 0.0, out=self.x[..., idx])
        for idx in S.UNIT_INTERVAL_VARS:
            np.clip(self.x[..., idx], 0.0, 1.0, out=self.x[..., idx])
        np.clip(self.x[..., S.PHI], 0.0, self.params.Phi_max, out=self.x[..., S.PHI])
        np.clip(self.Gamma, 0.0, self.params.Gamma_max, out=self.Gamma)
        np.clip(self.Omega, 0.0, 1.0, out=self.Omega)
        np.maximum(self.A_dom, 0.0, out=self.A_dom)
        np.clip(self.x[..., S.R], 0.0, self.params.R_total_node, out=self.x[..., S.R])
        # Numerical guards: complexity and inequality can be bumped upward by a
        # collapse jump (section 30); keep them in a sane range so a run of
        # collapses on one node cannot overflow to +inf.
        np.clip(self.x[..., S.C], 0.0, self.params.C_max, out=self.x[..., S.C])
        np.clip(self.x[..., S.I], 0.0, I_MAX, out=self.x[..., S.I])
        self.x *= self.occ.astype(float)[..., None]

    def _cull_dead_civs(self) -> None:
        for a in self.alive_indices():
            occ_nodes = np.where(self.occ[a] > 0)[0]
            if len(occ_nodes) == 0 or np.sum(self.x[a, occ_nodes, S.P]) < 1e-3:
                if len(occ_nodes) > 0:
                    self.occ[a, :] = 0
                self.alive[a] = False
                self.capital[a] = -1
                self.war_state[a, :] = self.war_state[:, a] = False
                self.events.append(EventRecord(self.t, "extinction", a))

    # -- observables (section 41) ----------------------------------------
    def record(self) -> None:
        p = self.params
        rec = {"t": float(self.t), "civ": {}, "psi_mean": float(np.mean(self.psi))}
        cyear = self.cosmic_years(self.t)
        ckey, cname = S.cosmo_era(S.UNIVERSE_AGE_NOW + cyear)
        rec["cosmic_year"] = float(cyear)
        rec["cosmo_era"] = cname
        rec["cosmo_era_key"] = ckey
        occupied_any = np.any(self.occ > 0, axis=0)
        rec["n_colonized"] = int(np.sum(occupied_any))
        rec["n_civ"] = int(np.sum(self.alive))
        rec["max_era"] = 0
        occ_nodes = np.where(occupied_any)[0]
        if len(occ_nodes) >= 2:
            dS = self.graph.ordinary_distance()[np.ix_(occ_nodes, occ_nodes)]
            rec["R_gal"] = float(np.max(dS))
        else:
            rec["R_gal"] = 0.0
        for a in self.alive_indices():
            nodes = np.where(self.occ[a] > 0)[0]
            if len(nodes) == 0:
                continue
            Etot = float(np.sum(self.x[a, nodes, S.E]))
            K = (np.log10(max(Etot, TINY)) - p.kardashev_k0) / p.kardashev_dk
            phi = float(np.max(self.x[a, nodes, S.PHI]))
            level, era_en, era_it = S.civ_era(K, phi)
            rec["max_era"] = max(rec["max_era"], level)
            rec["civ"][int(a)] = {
                "P": float(np.sum(self.x[a, nodes, S.P])),
                "A": float(np.mean(self.x[a, nodes, S.A])),
                "E": Etot,
                "K": float(K),
                "Q": float(np.mean(self.x[a, nodes, S.Q])),
                "Phi": phi,
                "Phi_mean": float(np.mean(self.x[a, nodes, S.PHI])),
                "G": float(np.mean(self.x[a, nodes, S.G])),
                "I": float(np.mean(self.x[a, nodes, S.I])),
                "Lambda": float(np.mean(self.x[a, nodes, S.LAM])),
                "L": float(np.mean(self.x[a, nodes, S.L])),
                "nodes": int(len(nodes)),
                "era_level": level,
                "era": era_en,
                "era_it": era_it,
                "universe": int(self.universe_idx[a]),
                "aeon": int(self.aeon_count[a]),
            }
        self.records.append(rec)

    def run(self, record_every: int = 4, max_steps: int = 200000) -> None:
        while self.t < self.params.t_max and self.step_count < max_steps:
            self.step()
            if self.step_count % record_every == 0:
                self.record()
            if not np.any(self.alive):
                break
        self.record()
