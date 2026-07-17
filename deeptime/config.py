"""Parameters and epistemic metadata for the Deep-Time model.

Every coefficient of the mathematical specification lives here as a field of
:class:`Params`.  Each parameter also carries an *epistemic tag* (section 2):

* ``E`` -- Empirical / calibratable from real data;
* ``X`` -- eXtrapolative but compatible with known physics;
* ``S`` -- Speculative axiom of the fictional universe.

The :data:`PARAM_META` registry drives the web interface: it groups the
parameters, gives each a human label, an epistemic tag, and a suggested slider
range.  Keeping the metadata beside the defaults means the UI and the maths can
never drift apart.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict, fields
from typing import Any, Dict, List


@dataclass
class Params:
    """Full parameter set for a single Monte-Carlo history.

    Defaults are chosen so that a small ensemble produces a recognisable
    deep-time arc (acceleration -> interstellar expansion -> fragmentation ->
    collapse and replacement -> Field maturity) rather than any single
    calibrated real-world trajectory.  They are deliberately *illustrative*.
    """

    # --- scenario scale ---------------------------------------------------
    n_nodes: int = 24            # inhabited astronomical sites
    n_civ: int = 3               # initial civilizations
    t_max: float = 50.0          # integration horizon (nondimensional time)
    dt_max: float = 0.1          # maximum adaptive step
    dt_min: float = 1.0e-3       # minimum adaptive step
    adapt_eps: float = 0.3       # target relative change per step (sec. 40)
    seed: int = 0                # base RNG seed

    # --- population (sections 7) -----------------------------------------
    pop_r: float = 0.55          # intrinsic growth rate            [E]
    pop_mu: float = 0.03         # baseline death/decay rate        [E]
    K0: float = 1.0              # carrying-capacity prefactor      [E]
    rho_R: float = 0.35          # K exponent on resources          [E]
    rho_E: float = 0.35          # K exponent on energy             [E]
    rho_Y: float = 0.20          # K exponent on industry           [E]
    rho_L: float = 0.15          # K exponent on longevity          [X]
    migrate_m0: float = 0.04     # migration prefactor              [E]
    migrate_tau: float = 6.0     # migration travel-time scale      [X]

    # --- longevity (section 8) -------------------------------------------
    g_L: float = 0.12            # longevity growth rate            [X]
    ell_A: float = 0.5           # longevity exponent on knowledge  [X]
    ell_Q: float = 0.3           # longevity exponent on computation[X]
    ell_Y: float = 0.2           # longevity exponent on industry   [X]
    L_max: float = 12.0          # longevity ceiling                [S]
    delta_L: float = 0.02        # longevity decay                  [X]

    # --- cognition (section 9) -------------------------------------------
    h_bio: float = 1.0           # weight, baseline biological mind [E]
    chi_I: float = 0.15          # cognition penalty, inequality    [X]
    chi_C: float = 0.05          # cognition penalty, admin complex.[X]
    chi_D: float = 0.20          # cognition penalty, cultural frag.[X]

    # --- knowledge (sections 10-11) --------------------------------------
    eta_know: float = 0.35       # knowledge growth prefactor       [E]
    alpha_know: float = 0.4      # exponent on effective cognition  [E]
    beta_know: float = 0.3       # exponent on computation          [X]
    theta_know: float = 0.2      # self-catalysis exponent          [X]
    A_max: float = 40.0          # knowledge ceiling (per epoch)    [X]
    delta_A: float = 0.01        # knowledge decay / forgetting     [E]
    kappa_transfer: float = 0.05 # inter-node knowledge diffusion   [E]
    sigma_A: float = 0.05        # knowledge noise amplitude        [X]
    dom_weights: List[float] = field(
        default_factory=lambda: [0.25, 0.15, 0.2, 0.1, 0.2, 0.1]
    )                             # omega_m over the six domains     [X]

    # breakthrough hazard (section 11)
    lam0_break: float = 0.03     # base breakthrough hazard         [S]
    alpha_H: float = 0.15        # hazard boost, cognition          [X]
    alpha_Q: float = 0.10        # hazard boost, computation        [X]
    alpha_A: float = 0.05        # hazard boost, existing knowledge [X]
    alpha_Ibr: float = 0.5       # hazard penalty, inequality       [X]
    alpha_Gbr: float = 0.5       # hazard penalty, weak institutions[X]
    dA_max: float = 6.0          # ceiling raise per breakthrough   [X]
    dA_jump: float = 1.2         # instantaneous knowledge jump     [X]

    # --- computation (section 12) ----------------------------------------
    g_Q: float = 0.45            # computation growth rate          [X]
    q_A: float = 0.4             # exponent on knowledge            [X]
    q_E: float = 0.5             # exponent on energy               [X]
    q_Y: float = 0.3             # exponent on industry             [X]
    delta_Q: float = 0.03        # computation decay                [X]
    q0: float = 1.0              # computation-ceiling prefactor    [X]
    xi_E: float = 0.6            # ceiling exponent on energy       [X]
    xi_R: float = 0.3            # ceiling exponent on resources    [X]
    xi_Phi: float = 0.4          # ceiling exponent on Field mastery[S]

    # --- energy (section 13) ---------------------------------------------
    g_E: float = 0.4             # energy growth rate               [X]
    e_A: float = 0.5             # exponent on knowledge            [X]
    e_Y: float = 0.4             # exponent on industry             [X]
    delta_E: float = 0.02        # energy decay                     [X]
    E_planet: float = 5.0        # planetary energy tier            [E]
    E_stellar: float = 60.0      # stellar (Dyson) tier             [X]
    E_galactic: float = 400.0    # galactic tier                    [X]
    E_field: float = 1500.0      # Field-tapped tier                [S]
    kardashev_k0: float = -0.3   # Kardashev index offset kappa_0   [E]
    kardashev_dk: float = 1.0    # Kardashev index scale            [E]

    # --- resources (section 14) ------------------------------------------
    x0_extract: float = 1.2      # extraction prefactor             [E]
    x_Y: float = 0.4             # extraction exponent on industry  [E]
    x_A: float = 0.3             # extraction exponent on knowledge [X]
    R_total_node: float = 50.0   # total resource stock per node    [E]
    c_P: float = 0.02            # resource cost per capita         [E]
    c_Y: float = 0.02            # resource cost per unit industry  [E]
    c_E: float = 5.0e-4          # resource cost per unit energy    [E]
    c_M: float = 0.01            # resource cost per unit military  [E]
    recycle: float = 0.5         # recycling efficiency             [X]

    # --- industry (section 15) -------------------------------------------
    g_Y: float = 0.4             # industry growth rate             [E]
    y_E: float = 0.4             # exponent on energy               [E]
    y_R: float = 0.3             # exponent on resources            [E]
    y_Q: float = 0.2             # exponent on computation          [X]
    y_A: float = 0.3             # exponent on knowledge            [E]
    Y_max: float = 120.0         # industry ceiling                 [X]
    delta_Y: float = 0.03        # industry decay                   [E]

    # --- Field mastery (section 16) --------------------------------------
    g_Phi: float = 0.06          # Field-mastery growth rate        [S]
    phi_A: float = 0.6           # exponent on field knowledge      [S]
    phi_Q: float = 0.3           # exponent on computation          [S]
    phi_E: float = 0.2           # exponent on energy               [S]
    Phi_max: float = 7.0         # Field-mastery ceiling            [S]
    delta_Phi: float = 0.02      # Field-mastery decay under stress [S]
    sigma_Phi_civ: float = 0.03  # Field-mastery noise              [S]
    lam_Phi_jump: float = 0.01   # Field breakthrough hazard        [S]
    dPhi_jump: float = 0.4       # Field breakthrough magnitude     [S]

    # --- Field state psi (section 5) -------------------------------------
    D_Phi: float = 0.15          # Field diffusivity                [S]
    alpha_Phi_damp: float = 0.1  # linear damping of psi            [S]
    beta_Phi_sat: float = 0.05   # cubic saturation of psi          [S]
    sigma_Phi_field: float = 0.08# Field turbulence noise           [S]
    eta_psi: float = 0.4         # route-weight sensitivity to psi  [S]
    eta_T: float = 0.3           # route-weight penalty, turbulence [S]
    eta_B: float = 0.3           # route-weight penalty, barriers   [S]
    field_eps: float = 1.0e-3    # cost regulariser epsilon         [S]

    # --- chronal (section 19) --------------------------------------------
    g_Gamma: float = 0.02        # chronal-tech growth rate         [S]
    Gamma_max: float = 5.0       # chronal-tech ceiling             [S]
    delta_Gamma: float = 0.02    # chronal-tech decay               [S]
    Phi_chronal: float = 6.0     # Field mastery needed for chronal [S]

    # --- inequality (section 22) -----------------------------------------
    g_I: float = 0.6             # inequality generation rate       [E]
    omega_E: float = 0.4         # inequality weight, energy CV     [X]
    omega_L: float = 0.3         # inequality weight, longevity CV  [X]
    omega_Q: float = 0.3         # inequality weight, computation CV[X]
    redistribution: float = 0.5  # redistribution / universal access[E]
    r_I: float = 0.06            # redistribution effectiveness     [E]
    delta_I: float = 0.03        # inequality relaxation            [E]

    # --- legitimacy (section 23) -----------------------------------------
    g_Lam: float = 0.25          # legitimacy generation rate       [E]
    d_Lam: float = 0.2           # legitimacy erosion rate          [E]
    w_wellbeing: float = 0.5     # legitimacy weight, wellbeing     [E]
    w_security: float = 0.3      # legitimacy weight, security      [E]
    w_continuity: float = 0.2    # legitimacy weight, continuity    [E]

    # --- administration (section 24) -------------------------------------
    g_C: float = 0.12            # admin-complexity growth rate     [E]
    alpha_Pc: float = 0.2        # complexity from population        [E]
    alpha_Vc: float = 0.6        # complexity from territory size    [E]
    alpha_Dc: float = 0.5        # complexity from Field distance    [X]
    alpha_Hc: float = 0.1        # complexity from cognition         [E]
    r_C: float = 0.25            # complexity reduction by computation[X]
    delta_C: float = 0.05        # complexity relaxation             [E]
    C_max: float = 25.0          # complexity ceiling (regularizer)  [X]

    # --- governability (section 25) --------------------------------------
    gov_TD: float = 4.0          # communication-lag tolerance      [X]
    gov_TM: float = 4.0          # transport-lag tolerance          [X]
    gov_D0: float = 1.0          # cultural-distance tolerance      [X]
    gov_C0: float = 8.0          # admin-complexity tolerance       [X]

    # --- institutional stability (section 26) ----------------------------
    a_Q: float = 0.3             # stability gain, governability     [E]
    a_R: float = 0.15            # stability gain, resource slack    [E]
    a_Lam: float = 0.25          # stability gain, legitimacy        [E]
    a_Z: float = 0.05            # stability gain, archives          [X]
    a_C: float = 0.2             # stability loss, complexity        [E]
    a_I: float = 0.2             # stability loss, inequality        [E]
    a_U: float = 0.2             # stability loss, unrest            [E]
    a_W: float = 0.25            # stability loss, war               [E]
    sigma_G: float = 0.03        # stability noise                   [E]

    # --- military & conflict (sections 27-28) ----------------------------
    g_M: float = 0.3             # military growth rate              [E]
    m_Y: float = 0.4             # exponent on industry              [E]
    m_E: float = 0.3             # exponent on energy                [E]
    m_A: float = 0.2             # exponent on knowledge             [E]
    m_Q: float = 0.2             # exponent on computation           [X]
    delta_M: float = 0.06        # military decay                    [E]
    M_max: float = 60.0          # military ceiling (regularizer)    [X]
    war_alpha_R: float = 1.2     # war driver, resource overlap      [E]
    war_alpha_T: float = 0.8     # war driver, territorial overlap   [E]
    war_alpha_I: float = 0.6     # war driver, inequality            [E]
    war_alpha_C: float = 0.7     # war driver, cultural distance     [X]
    war_alpha_D: float = 1.5     # war damper, deterrence            [E]
    war_alpha_X: float = 1.0     # war damper, trade                 [E]
    war_bias: float = -1.2       # baseline war logit                [E]
    war_damage: float = 0.9      # damage coefficient                [E]

    # --- archives (section 29) -------------------------------------------
    g_Z: float = 0.2             # archival growth rate              [X]
    delta_Z: float = 0.04        # archival decay                    [E]
    chi_W: float = 0.3           # archive loss from war             [E]
    chi_C_arch: float = 0.4      # archive loss from collapse        [E]
    rho_Z: float = 1.0           # collapse knowledge-loss shielding [X]

    # --- collapse (section 30) -------------------------------------------
    h0_collapse: float = 0.05    # base collapse hazard              [E]
    b_CR: float = 0.6            # hazard, complexity / resources    [E]
    b_I: float = 0.5             # hazard, inequality                [E]
    b_U: float = 0.6            # hazard, unrest                    [E]
    b_W: float = 0.7            # hazard, war damage                [E]
    b_G: float = 1.1            # hazard shield, institutions       [E]
    b_Z: float = 0.5            # hazard shield, archives            [X]
    b_resil: float = 0.5        # hazard shield, resilience (Lambda)[X]
    collapse_loss: Dict[str, float] = field(
        default_factory=lambda: {
            "P": 0.6, "H": 0.5, "A": 0.4, "E": 0.5, "R": 0.3, "Y": 0.6,
            "Q": 0.6, "L": 0.4, "Phi": 0.5, "G": 0.7, "I": 0.3, "M": 0.6,
            "C": 0.5, "Lambda": 0.6, "Z": 0.5,
        }
    )                             # collapse loss fractions (sec. 30) [X]

    # --- fragmentation & merger (sections 31-32) -------------------------
    G_crit: float = 0.4          # fragmentation stability threshold [X]
    D_crit: float = 0.5          # fragmentation cultural threshold  [X]
    merge_benefit_T: float = 0.5 # merger benefit, trade             [X]
    merge_benefit_S: float = 0.4 # merger benefit, security          [X]
    merge_benefit_K: float = 0.3 # merger benefit, knowledge         [X]
    merge_cost_C: float = 0.6    # merger cost, cultural distance     [X]
    merge_cost_D: float = 0.4    # merger cost, distance              [X]
    merge_cost_I: float = 0.3    # merger cost, inequality            [X]

    # --- colonization (section 20) ---------------------------------------
    col_lam0: float = 0.06       # colonization hazard prefactor     [X]
    col_chi_Y: float = 0.4       # colonization exponent, industry   [X]
    col_chi_E: float = 0.3       # colonization exponent, energy     [X]
    col_chi_Phi: float = 0.5     # colonization exponent, Field      [S]
    col_length: float = 3.0      # colonization Field-distance scale [S]

    # --- culture (section 21) --------------------------------------------
    cult_beta: float = 0.3       # idea adoption rate                [E]
    cult_gamma: float = 0.1      # idea abandonment rate             [E]
    cult_transfer: float = 0.05  # idea diffusion between nodes       [E]
    cult_div0: float = 0.02      # baseline cultural divergence       [X]
    n_ideas: int = 4             # tracked cultural ideas             [X]

    # --- aeonic (sections 33-34) -----------------------------------------
    aeon_prime: int = 7          # number of accessible universes P  [S]
    gate_a1: float = 1.2         # gate logit, Field mastery         [S]
    gate_a2: float = 1.0         # gate logit, aeonic knowledge      [S]
    gate_a3: float = 0.002       # gate logit, energy                [S]
    gate_a4: float = 0.02        # gate logit, computation           [S]
    gate_a5: float = 1.5         # gate logit penalty, instability   [S]
    gate_a6: float = 1.5         # gate logit penalty, singularity   [S]
    gate_bias: float = -7.0      # gate baseline logit               [S]
    Phi_gate_min: float = 4.0    # minimum Field mastery for a gate  [S]
    aeon_rate: float = 0.05      # max aeonic-transition hazard      [S]
    aeon_cooldown: float = 4.0   # min time between transitions       [S]

    # --- escape / coherence (section 37) ---------------------------------
    g_Omega: float = 0.0008      # coherence growth rate             [S]
    delta_Omega: float = 0.05    # decoherence rate                  [S]
    Omega_crit: float = 0.9      # escape coherence threshold        [S]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Params":
        """Build a Params, ignoring unknown keys and keeping defaults."""
        known = {f.name for f in fields(cls)}
        clean = {k: v for k, v in (data or {}).items() if k in known}
        return cls(**clean)


# ---------------------------------------------------------------------------
# UI metadata: (group, label, tag, min, max)
# ---------------------------------------------------------------------------
# Only the parameters most useful to expose as sliders are listed; the full set
# is always editable through the JSON payload.  Tag is one of E / X / S.
PARAM_META: Dict[str, Dict[str, Any]] = {
    # scenario
    "n_nodes":        {"group": "Scenario", "label": "Number of nodes", "tag": "E", "min": 4, "max": 80, "step": 1, "int": True},
    "n_civ":          {"group": "Scenario", "label": "Initial civilizations", "tag": "E", "min": 1, "max": 8, "step": 1, "int": True},
    "t_max":          {"group": "Scenario", "label": "Time horizon", "tag": "E", "min": 10, "max": 200, "step": 5},
    "seed":           {"group": "Scenario", "label": "Random seed", "tag": "E", "min": 0, "max": 100000, "step": 1, "int": True},

    "pop_r":          {"group": "Population", "label": "Growth rate r", "tag": "E", "min": 0.0, "max": 1.5, "step": 0.01},
    "pop_mu":         {"group": "Population", "label": "Mortality mu", "tag": "E", "min": 0.0, "max": 0.3, "step": 0.005},
    "migrate_m0":     {"group": "Population", "label": "Migration rate", "tag": "E", "min": 0.0, "max": 0.3, "step": 0.005},

    "eta_know":       {"group": "Knowledge", "label": "Knowledge growth eta", "tag": "E", "min": 0.0, "max": 1.5, "step": 0.01},
    "lam0_break":     {"group": "Knowledge", "label": "Breakthrough hazard", "tag": "S", "min": 0.0, "max": 0.3, "step": 0.005},
    "kappa_transfer": {"group": "Knowledge", "label": "Knowledge transfer", "tag": "E", "min": 0.0, "max": 0.5, "step": 0.01},

    "g_E":            {"group": "Energy", "label": "Energy growth", "tag": "X", "min": 0.0, "max": 1.5, "step": 0.01},
    "E_field":        {"group": "Energy", "label": "Field energy tier", "tag": "S", "min": 100, "max": 5000, "step": 50},

    "g_Q":            {"group": "Computation", "label": "Computation growth", "tag": "X", "min": 0.0, "max": 1.5, "step": 0.01},

    "g_Phi":          {"group": "Field", "label": "Field-mastery growth", "tag": "S", "min": 0.0, "max": 0.6, "step": 0.005},
    "Phi_max":        {"group": "Field", "label": "Field-mastery ceiling", "tag": "S", "min": 1.0, "max": 8.0, "step": 0.5},
    "D_Phi":          {"group": "Field", "label": "Field diffusivity", "tag": "S", "min": 0.0, "max": 1.0, "step": 0.01},
    "sigma_Phi_field":{"group": "Field", "label": "Field turbulence", "tag": "S", "min": 0.0, "max": 0.4, "step": 0.01},

    "g_I":            {"group": "Society", "label": "Inequality growth", "tag": "E", "min": 0.0, "max": 0.4, "step": 0.01},
    "redistribution": {"group": "Society", "label": "Redistribution", "tag": "E", "min": 0.0, "max": 2.0, "step": 0.05},

    "war_bias":       {"group": "Conflict", "label": "War baseline logit", "tag": "E", "min": -5.0, "max": 2.0, "step": 0.1},
    "war_damage":     {"group": "Conflict", "label": "War damage", "tag": "E", "min": 0.0, "max": 2.0, "step": 0.05},

    "h0_collapse":    {"group": "Collapse", "label": "Base collapse hazard", "tag": "E", "min": 0.0, "max": 0.2, "step": 0.005},
    "b_G":            {"group": "Collapse", "label": "Institutional shield", "tag": "E", "min": 0.0, "max": 3.0, "step": 0.05},

    "col_lam0":       {"group": "Expansion", "label": "Colonization rate", "tag": "X", "min": 0.0, "max": 0.4, "step": 0.005},

    "gate_bias":      {"group": "Aeonic", "label": "Gate baseline logit", "tag": "S", "min": -12.0, "max": 0.0, "step": 0.2},
    "aeon_prime":     {"group": "Aeonic", "label": "Accessible universes (prime)", "tag": "S", "min": 2, "max": 31, "step": 1, "int": True},
}

TAG_MEANING = {
    "E": "Empirical / calibratable from real data",
    "X": "Extrapolative but compatible with known physics",
    "S": "Speculative axiom of the fictional universe",
}
