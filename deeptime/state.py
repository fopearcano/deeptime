"""State-variable layout for the Deep-Time civilizational model.

The per-(civilization, node) local state vector ``x_{ai}`` from section 6 of the
specification has 15 components.  We keep them in a fixed order so the whole
ensemble can be stored as a single ``(n_civ, n_node, N_VARS)`` numpy array and
manipulated with vectorised operations.

    x_{ai} = [P, H, A, E, R, Y, Q, L, Phi, G, I, M, C, Lambda, Z]

Alongside this primary array the model tracks a handful of auxiliary fields that
the specification introduces separately:

* ``A_dom``  -- the six knowledge domains of section 10 (phys, bio, comp, soc,
  field, aeon); the aggregate ``A`` is a weighted sum of these.
* ``psi``    -- the per-node Field navigational state of section 5 (a property of
  the node, shared by everyone at that node, not of a civilization).
* ``Gamma``  -- chronal technology of section 19.
* ``Omega``  -- closed-universe escape coherence of section 37.

Everything here is pure data description; the dynamics live in :mod:`deeptime.model`.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Primary state vector indices (section 6)
# ---------------------------------------------------------------------------
P = 0      # population / active minds
H = 1      # effective cognitive capacity (stored; recomputed each step)
A = 2      # aggregate scientific knowledge
E = 3      # usable energy capacity
R = 4      # accessible resources
Y = 5      # industrial output
Q = 6      # computation
L = 7      # longevity / repair capability
PHI = 8    # Field mastery  (Phi)
G = 9      # institutional stability
I = 10     # inequality
M = 11     # military capacity
C = 12     # administrative complexity
LAM = 13   # legitimacy (Lambda)
Z = 14     # archival integrity

N_VARS = 15

VAR_NAMES = [
    "P", "H", "A", "E", "R", "Y", "Q", "L",
    "Phi", "G", "I", "M", "C", "Lambda", "Z",
]

VAR_LABELS = {
    "P": "Population / active minds",
    "H": "Effective cognitive capacity",
    "A": "Scientific knowledge",
    "E": "Usable energy capacity",
    "R": "Accessible resources",
    "Y": "Industrial output",
    "Q": "Computation",
    "L": "Longevity / repair",
    "Phi": "Field mastery",
    "G": "Institutional stability",
    "I": "Inequality",
    "M": "Military capacity",
    "C": "Administrative complexity",
    "Lambda": "Legitimacy",
    "Z": "Archival integrity",
}

# Variables constrained to the unit interval [0, 1] (section 39).
UNIT_INTERVAL_VARS = (G, LAM, Z)

# Variables constrained to be non-negative (section 39).
NONNEGATIVE_VARS = (P, H, A, E, R, Y, Q, L, PHI, I, M, C)

# ---------------------------------------------------------------------------
# Knowledge domains (section 10)
# ---------------------------------------------------------------------------
DOM_PHYS = 0
DOM_BIO = 1
DOM_COMP = 2
DOM_SOC = 3
DOM_FIELD = 4
DOM_AEON = 5

N_DOMAINS = 6

DOMAIN_NAMES = ["phys", "bio", "comp", "soc", "field", "aeon"]

DOMAIN_LABELS = {
    "phys": "Physics",
    "bio": "Biology",
    "comp": "Computation science",
    "soc": "Social science",
    "field": "Field science",
    "aeon": "Aeonic science",
}

# ---------------------------------------------------------------------------
# Field-mastery capability tiers (section 16)
# ---------------------------------------------------------------------------
FIELD_TIERS = [
    (0.0, "Field observation"),
    (1.0, "Nonlocal communication"),
    (2.0, "Field-assisted propulsion"),
    (3.0, "Deep-field navigation"),
    (4.0, "Aeonic gates"),
    (5.0, "Ontological conversion"),
    (6.0, "Chronal manipulation"),
]


def field_tier(phi: float) -> str:
    """Return the capability label for a given Field-mastery value."""
    label = FIELD_TIERS[0][1]
    for threshold, name in FIELD_TIERS:
        if phi >= threshold:
            label = name
        else:
            break
    return label


# ---------------------------------------------------------------------------
# Civilizational eras / levels  ("Tempo profondo delle civilta", Image 1)
# ---------------------------------------------------------------------------
# A civilization's *era* is the joint reading of its energy mastery (the
# continuous Kardashev index K) and its Field mastery (Phi).  Each era is reached
# only when BOTH thresholds are met -- energy and Field advance together but an
# era is defined by the pair.  The named ladder runs from a contemporary
# planetary civilization up to the chronal / universally self-referential stage.
#
#   (level, key, English name, Italian name, K_min, Phi_min, description)
CIV_ERAS = [
    (1, "planetary",    "Planetary",    "Terra contemporanea", 0.0, 0.0,
     "Incomplete planetary civilization; industrial energy and a global network."),
    (2, "solar",        "Solar",        "Civilta solare",      1.0, 1.0,
     "Industrialized star system; first network structures; first Field probes."),
    (3, "interstellar", "Interstellar", "Diaspora",            2.0, 2.0,
     "First interstellar colonies; network formation; instantaneous communication."),
    (4, "galactic",     "Galactic",     "Imperi galattici",    2.5, 3.0,
     "Networks of vast numbers of systems; millennial longevity; imperial cycles."),
    (5, "oceanic",      "Oceanic",      "Eta oceanica",        3.0, 3.5,
     "Mapping the quantum currents; superluminal navigation; Field ecosystems."),
    (6, "eonic",        "Eonic",        "Eta eonica",          3.8, 4.5,
     "Intergalactic network; cosmological-scale cognition; migration between conformal aeons."),
    (7, "chronal",      "Chronal",      "Cronale",             4.2, 6.0,
     "Universal self-referential consciousness; trans-universal awareness of the Field."),
]

CIV_ERA_NAMES = [e[2] for e in CIV_ERAS]


def civ_era(K: float, Phi: float):
    """Return ``(level, english_name, italian_name)`` for a (K, Phi) pair.

    The highest era whose energy AND Field thresholds are both satisfied wins.
    """
    level, en, it = CIV_ERAS[0][0], CIV_ERAS[0][2], CIV_ERAS[0][3]
    for lvl, key, name_en, name_it, kmin, pmin, _desc in CIV_ERAS:
        if K >= kmin and Phi >= pmin:
            level, en, it = lvl, name_en, name_it
    return level, en, it


# ---------------------------------------------------------------------------
# Cosmological eras of the universe (Images 4-5: standard ΛCDM timeline)
# ---------------------------------------------------------------------------
# Keyed on the total cosmic age (years after the Big Bang).  Present day is
# ~1.38e10 yr; the civilizational narrative plays out inside the Stelliferous
# era, with the Degenerate / Black-Hole / Heat-Death eras as the far-future
# backdrop that aeonic (CCC) transitions are meant to escape.
#   (key, name, age_start, age_end, note)
COSMO_ERAS = [
    ("stelliferous",      "Stelliferous Era",        0.0,   1.0e12,  "Stars form and shine."),
    ("late_stelliferous", "Late Stelliferous Era",   1.0e12, 1.0e14, "Star formation winds down; compact remnants accumulate."),
    ("degenerate",        "Degenerate Era",          1.0e14, 1.0e40, "Stellar remnants dominate; ordinary matter slowly disappears."),
    ("black_hole",        "Black-Hole Era",          1.0e40, 1.0e100, "Black holes dominate and slowly evaporate via Hawking radiation."),
    ("heat_death",        "Heat Death / Big Freeze", 1.0e100, float("inf"), "Maximum entropy; a cold, dilute, ever-expanding cosmos."),
]

UNIVERSE_AGE_NOW = 1.38e10   # years after the Big Bang, today


def cosmo_era(age_years: float):
    """Return ``(key, name)`` of the cosmological era at a given cosmic age."""
    for key, name, lo, hi, _note in COSMO_ERAS:
        if lo <= age_years < hi:
            return key, name
    return COSMO_ERAS[-1][0], COSMO_ERAS[-1][1]


def cosmo_energy_factor(age_years: float) -> float:
    """Availability of *stellar/galactic* energy vs cosmic age (Image 3).

    Falls as stars fade after the Stelliferous era.  Field-tapped energy is not
    scaled by this factor -- in this universe the Field is the constant, so it is
    the energy source that persists into the deep cosmological future.
    """
    if age_years < 1.0e12:
        return 1.0
    if age_years < 1.0e14:
        return 0.6
    if age_years < 1.0e40:
        return 0.15
    if age_years < 1.0e100:
        return 0.03
    return 0.005
