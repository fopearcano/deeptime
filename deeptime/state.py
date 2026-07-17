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
