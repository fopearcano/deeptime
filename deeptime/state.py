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
# Field-mastery capability ladder Phi_0 .. Phi_6  (QTR v2, single universe)
# ---------------------------------------------------------------------------
# Every rung is a navigational capability the QTR codex names.  Crucially, this
# is a single-universe ladder: Phi_5 is NOT conversion between universes and
# Phi_6 is NOT routine time-travel -- any becoming-time (P4) effect stays
# conditional and frame-bound.
FIELD_TIERS = [
    (0.0, "Observation of quantum fluctuations"),
    (1.0, "Industrial entanglement & nonlocal comms (ER=EPR)"),
    (2.0, "Field propulsion, Casimir-corridor sailing"),
    (3.0, "Deep-field superluminal navigation (the Idrenes-Bridge dive)"),
    (4.0, "Large-scale topological engineering (kindled seam-wells)"),
    (5.0, "Cosmological Field integration & universe-scale cognition"),
    (6.0, "Universal self-reference & possible trans-universal awareness"),
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
# The Ontological Cantor Tower (OCT) and vessel classes (QTR v2)
# ---------------------------------------------------------------------------
# The OCT is a transfinite hierarchy of *state-depths within one universe*,
# ranked by mutual information.  Diving deeper shortens the effective Field
# route -- a deeper ship is a faster ship (the Ship-Relative Speed Law).  A
# vessel's class IS the deepest OCT rung it can navigate.  None of this leaves
# the home universe.  Depth reach is set by the Field-mastery tier the codex
# fixes: the Idrenes-Bridge dive opens at Phi_3.
#   (Phi_min, oct_level, class_label, class_name, reach)
OCT_LADDER = [
    (0.0, "OCT-0",  "Class 0",   "Crawlers",   "Sub-light; intra-stellar"),
    (2.0, "OCT-0",  "Class I",   "Bridges",    "Any point in the home universe (~1e10 c)"),
    (3.0, "OCT-1",  "Class II",  "Wanderers",  "Remote galactic & intergalactic regions"),
    (4.0, "OCT-2",  "Class III", "Sovereigns", "Remote cosmological causal domains"),
    (6.0, "OCT-ω",  "Class ω",   "the Formless", "Asymptotic depth of the one universe"),
]
# OCT-Omega -- the fixed point of the universe's own self-description -- is
# acknowledged but never crossed, and so is not a reachable class.


def oct_reach(phi: float):
    """Return ``(oct_level, class_label, class_name)`` reachable at a Phi."""
    lvl, cl, name = OCT_LADDER[0][1], OCT_LADDER[0][2], OCT_LADDER[0][3]
    for pmin, oct_level, class_label, class_name, _reach in OCT_LADDER:
        if phi >= pmin:
            lvl, cl, name = oct_level, class_label, class_name
    return lvl, cl, name


def oct_depth_index(phi: float) -> int:
    """Integer OCT depth (0,1,2,3) reachable at a Phi -- deeper = shorter route."""
    d = 0
    for i, (pmin, *_rest) in enumerate(OCT_LADDER):
        if phi >= pmin:
            d = i
    # collapse the two OCT-0 rungs (Class 0 / Class I) to depth 0/0 vs deeper
    return max(0, d - 1)


# ---------------------------------------------------------------------------
# Cosmic fates -- the six competing lifecycles of THIS one universe (QTR v2)
# ---------------------------------------------------------------------------
# Each Monte-Carlo history samples one ultimate fate from this observationally
# weighted prior.  Penrose CCC is the only one that "escapes" heat death -- as a
# recurrent continuation of this universe's lifecycle, NOT travel between
# parallel universes.
COSMIC_FATES = [
    ("heat_death",  "Heat Death / Big Freeze", 0.45, "Eternal expansion to maximum entropy."),
    ("ccc",         "Penrose CCC",             0.25, "Conformal crossover to a next aeon of the same universe."),
    ("big_rip",     "Big Rip",                 0.10, "Runaway dark energy tears structure apart."),
    ("big_bounce",  "Big Bounce / Oscillatory",0.10, "A contracting phase bounces into a new expansion."),
    ("big_crunch",  "Big Crunch",              0.05, "Expansion reverses into a final hot collapse."),
    ("vacuum_decay","Vacuum Decay",            0.05, "A false-vacuum transition changes the local laws."),
]


# ---------------------------------------------------------------------------
# QTR reference material (for the interface's model documentation)
# ---------------------------------------------------------------------------
QTR_LAYERS = [
    ("QTR",  "Quantum Theory of Relativity", "What is the universe made of? Spacetime is emergent -- it grows from a partial order of relational quantum events."),
    ("ΛL",   "Five-valued logic of the limit", "How do we reason at its edges?"),
    ("PIIU", "Physics of Intra-Universe Infinities", "How are the depths of the one universe arranged?"),
    ("NAV",  "Navigating the quantum vacuum", "What does a pilot actually do?"),
]

QTR_POSTULATES = [
    ("P1", "Atomicity", "History is a locally finite partial order of events."),
    ("P2", "Amplitude", "Every finite sub-history carries a complex amplitude."),
    ("P3", "Frames", "No amplitude is absolute; all are relative to an internal quantum reference frame."),
    ("P4", "Growth", "The order is grown one event at a time (‘becoming’)."),
]

LAMBDA_L_VALUES = [
    ("T",  "classical true"),
    ("T⁻", "left / IR approach"),
    ("T•", "seam-truth"),
    ("T⁺", "right / UV approach"),
    ("F",  "classical false"),
]

NAV_DOORS = [
    ("Depth", "The seam \U0001D50D / Idrenes Bridge", "A vertical dive to a deeper OCT rung and back -- the daily basis of FTL. A transition in state-depth, not a border between universes.", "Φ₃"),
    ("Adjacency", "The Penrose bridge", "A one-way, asymmetric throat (black-hole mouth → white-hole exit) joining two remote regions of the same universe.", "Φ₄"),
    ("Constitution", "The curvature limit Κ", "The internal limit of QTR's own description. Approached, never confirmed crossed; the K5 verdicts are competing interpretations, not a navigable multiverse.", "—"),
]


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
# Thresholds encode the K-Phi coupling of QTR v2: deep Field mastery is reserved
# for powers that also command the energy of their era (Oceanic Phi_4 needs
# galactic energy K~3; Eonic/Chronal Phi_5-6 need the cosmological regime K~4-5).
# The narrative present (~50 Gyr) sits at the Oceanic age (level 5).
CIV_ERAS = [
    (1, "planetary",    "Planetary",    "Terra contemporanea", 0.0, 0.0,
     "Incomplete planetary civilization; industrial energy and a global network."),
    (2, "solar",        "Solar",        "Civilta solare",      1.0, 1.0,
     "Industrialized star system; nonlocal communication; first Field probes."),
    (3, "interstellar", "Interstellar", "Diaspora",            2.0, 2.0,
     "First interstellar colonies; Casimir-corridor sailing; network formation."),
    (4, "galactic",     "Galactic",     "Imperi galattici",    3.0, 3.0,
     "Networks of vast numbers of systems; the routine Idrenes-Bridge dive; imperial cycles."),
    (5, "oceanic",      "Oceanic",      "Eta oceanica",        3.0, 4.0,
     "Kindled seam-wells; deep-field superluminal navigation; Field ecosystems. The narrative present."),
    (6, "eonic",        "Eonic",        "Eta eonica",          4.0, 5.0,
     "Intergalactic Field integration; cosmological-scale cognition; a still-forming proto-universal self."),
    (7, "chronal",      "Chronal",      "Cronale",             4.5, 6.0,
     "Universal self-reference (~1e13 yr) and possible trans-universal awareness (~1e14 yr) -- recognition, not travel."),
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
