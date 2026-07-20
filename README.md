# Deep-Time Civilizational Evolution — model & web interface

A working implementation of the **Complete Mathematical Model of Deep-Time
Civilizational Evolution** (the full specification is in
[`docs/deep_time_complete_mathematical_model.md`](docs/deep_time_complete_mathematical_model.md)).

The model is a **hybrid stochastic dynamical network**: ordinary spacetime
coupled to a nonlocal, navigable *Field Ocean*, with civilizations evolving
across many interacting subsystems (population, cognition, science, energy,
computation, resources, industry, longevity, Field mastery, politics, warfare,
culture, collapse, and aeonic transitions). It combines ordinary differential
equations, graph diffusion, stochastic differential equations, jump processes,
state-dependent graph topology and event thresholds — exactly the
`dX = F dt + Σ dW + J dN` structure of §38/§50.

It ships with a **self-contained web interface** (custom SVG charts, no external
JavaScript libraries) for running single histories, exploring the Field network
and event stratigraphy, and estimating the probability questions of §42 over a
Monte-Carlo ensemble.

<p align="center"><em>The universe is modeled as a coupled dynamical ecology in
which civilizations are temporary configurations of matter, information, energy
and Field structure across deep time.</em></p>

## Quick start

Only dependency is **numpy** (the web server uses the Python standard library —
no Flask/FastAPI).

```bash
pip install -r requirements.txt      # numpy
python -m deeptime.server            # open http://localhost:8000
```

Then in the browser:

* **Run one history** — integrate a single stochastic trajectory and watch a
  civilizational ecosystem unfold: observable trajectories (§41), the Field
  network graph (§4–5), the surviving civilizations, and the full historical
  *stratigraphy* of events (§48).
* **Run Monte Carlo** — sample an ensemble of independent histories and estimate
  the probability questions of §42 (with standard errors), plus ensemble mean
  and 10–90% bands for the key observables.
* **The Model** — a glossary of the 15 state variables, the Field-mastery tiers,
  and the full mathematical specification.

Every parameter is tagged by its epistemic status (§2): **E** empirical,
**X** extrapolative, **S** speculative.

### Command line

```bash
python examples/run_example.py --runs 40      # chronicle + probability questions
python tests/test_model.py                    # run the test suite (no pytest needed)
```

```python
from deeptime import Params, Simulation, run_ensemble

sim = Simulation(params=Params(seed=1))
sim.run()
print(sim.records[-1])                          # final observables

ens = run_ensemble(Params(), n_runs=100)
print(ens.probabilities)                         # P(K>=3), P(chronal), ...
```

## The deep-time framework (the diagrams)

On top of the raw dynamics the model exposes the **civilizational-evolution
framework** of the accompanying diagrams:

* **Seven civilizational eras** — `Planetary → Solar → Interstellar → Galactic →
  Oceanic → Eonic → Chronal` (with their Italian names *Terra contemporanea …
  Cronale*). An era is read jointly from the continuous Kardashev index **K**
  (energy mastery) and the Field mastery **Φ**: a civilization enters an era only
  once **both** its K and Φ thresholds are met (`deeptime/state.py: civ_era`).
* **A cosmic-time axis** — the nondimensional integration time is mapped
  log-uniformly onto *years in Earth's future* (Oggi → 10⁶ → … → 5·10¹¹ yr), so a
  run can be read directly on the deep-time ladder. The **narrative present**
  sits at 50 billion years.
* **The cosmological backdrop** — the universe's own ΛCDM lifecycle
  (Stelliferous → Late-Stelliferous → Degenerate → Black-Hole → Heat-Death). The
  civilizational narrative occupies a sliver of the Stelliferous era; stellar and
  galactic energy availability **fades** in later cosmic eras (energy access
  drives complexity), while the **Field-tapped energy tier persists** — *il Campo
  è la costante*.
* **Conformal Cyclic Cosmology (Penrose CCC)** — aeonic transitions are
  conformal crossovers along a linked sequence of aeons; each civilization tracks
  its aeon count, with the accessible-universe index cycling with period *P*
  (§33). This is the model's route past the far-future eras — the "infinity of
  infinities."

The web **History** tab leads with the *Deep-Time Ladder* chart (civilizational
level vs cosmic time, matching the reference diagram) and a cosmological-context
strip; the **The Model** tab lists the era ladder, Field tiers and cosmological
eras.

## What the model produces

Under the illustrative default parameters a typical deep-time arc runs

```
rapid technological acceleration → interstellar expansion → a Field-enabled
galactic ecosystem of a few coexisting civilizations → wars, collapses and
occasional extinctions → mastery of the Field up to aeonic gates and, rarely,
chronal manipulation.
```

Because Field mastery collapses communication and transport lag (the Field Ocean
premise, §17–18), advanced empires stay *governable* at galactic scale — so the
model's turnover comes mainly from **war, collapse and extinction** rather than
cultural fragmentation. All of this is parameter-dependent and fully exposed in
the UI: raise the collapse hazard, war damage or inequality, or shorten the
horizon, and flourishing stops being near-certain.

## Architecture

```
deeptime/
  state.py        state-variable layout (§6), knowledge domains (§10), Field tiers (§16)
  config.py       every coefficient as a tagged Params field + UI metadata
  graph.py        ordinary-space & Field graphs, Laplacian, Floyd–Warshall Field distance (§4–5)
  model.py        the Simulation: drift (§7–29), events (§11,20,28,30–34), adaptive integrator (§40)
  montecarlo.py   parallel ensembles + the §42 probability questions (§45)
  serialize.py    JSON snapshots (graph + trajectories) for the web layer
  server.py       stdlib HTTP server + JSON API + background MC jobs
web/              self-contained interface (index.html, styles.css, charts.js, app.js)
docs/             the mathematical specification (copied verbatim)
examples/, tests/
```

### How the maths maps to the code

| Specification | Where |
|---|---|
| §4 Spatial structure, Field distance | `graph.SpaceGraph` (Floyd–Warshall in the min-+ semiring) |
| §5 Field-state ψ dynamics, route weights | `model.step_field`, `graph.field_weights` |
| §6 State vector `x_{ai}` (15 vars) | `state.py`, `model.Simulation.x` |
| §7 Population (logistic + carrying capacity + migration) | `continuous_drift`, `_migrate` |
| §8 Longevity | `continuous_drift` (L) |
| §9 Effective cognition with fragmentation penalties | `effective_cognition` |
| §10–11 Knowledge domains, diffusion, breakthrough jumps | `continuous_drift`, `_diffuse_knowledge`, `_sample_breakthroughs` |
| §12–15 Computation, energy (Kardashev), resources, industry | `continuous_drift` |
| §16 Field mastery Φ (+ paradigm jumps) | `continuous_drift`, `_sample_field_breakthroughs` |
| §17–18 Communication & transport times | `_governability` (τ_com, τ_transp) |
| §19 Chronal technology Γ | `continuous_drift` (Gamma) |
| §20 Migration & colonization | `_migrate`, `_colonize` |
| §21 Culture, cultural distance, divergence | `_evolve_ideas`, `_node_cultural_spread` |
| §22–26 Inequality, legitimacy, admin complexity, governability, stability | `continuous_drift`, `_governability` |
| §27–28 Military & conflict | `_compute_war_damage`, `_sample_war_transitions` |
| §29 Archival integrity | `continuous_drift` (Z) |
| §30 Collapse hazard & jump | `_sample_collapse`, `_apply_collapse` |
| §31–32 Fragmentation & merger | `_sample_fragmentation`, `_sample_merger` |
| §33–34 Aeonic structure & gates (Penrose CCC crossovers) | `_sample_aeonic`, `aeon_count` |
| Civilizational era ladder (K × Φ → 7 eras) | `state.civ_era`, `CIV_ERAS` |
| Cosmic-time axis & cosmological eras | `Simulation.cosmic_years`, `state.cosmo_era`, `cosmo_energy_factor` |
| §37 Closed-universe escape coherence Ω | `continuous_drift` (Omega) |
| §39 Constraints | `enforce_constraints` |
| §40 Nondimensional adaptive timestep | `_adaptive_dt` |
| §41 Observables | `record`, `serialize` |
| §42/§45 Probability questions & Monte Carlo | `montecarlo.py` |
| §47 Minimal implementable model | subsumed by the full `Simulation` |

## Implementation & numerical notes

The specification is a *research-grade* mathematical object; a faithful,
*stable*, *fast* simulator requires a handful of documented engineering choices.
These are all local to `model.py`/`config.py` and are called out in comments:

* **Soft ceilings** on military capacity (`M_max`) and administrative complexity
  (`C_max`), and a saturating form for the bounded archival integrity `Z`, are
  numerical regularizers so the adaptive integrator is not driven to its floor by
  otherwise-unbounded growth. (Without them, `dZ = g_Z Q Y` on `Z ∈ [0,1]` alone
  pins the step size.)
* **Per-variable characteristic scales** drive the adaptive timestep, so a fast
  but bounded variable can't dictate a tiny global step.
* **dt-invariant hazards**: war onset/peace, mergers, colonization, collapse,
  breakthroughs and gates are sampled as `1 − exp(−rate·dt)` so results don't
  depend on the number of integration steps. Collapse, fragmentation and aeonic
  transitions carry cooldowns so a single event can't cascade every step.
* **Bounded feedbacks**: breakthrough and Field-paradigm hazards use saturating
  (`tanh`) dependence on cognition/computation/knowledge so paradigm jumps stay
  rare and momentous instead of firing continuously at maturity.
* **Multi-mind cognition** (§9): the default configuration tracks a single
  biological mind pool; the additional enhanced/artificial/collective pools of
  §9 are structurally supported (`H` is a weighted sum) but collapsed to one term
  at these defaults.

Runtime: a single history is a few seconds; a Monte-Carlo ensemble is
embarrassingly parallel and is spread across processes automatically.

## API

The server exposes a small JSON API (all responses are JSON):

| Method & path | Purpose |
|---|---|
| `GET  /api/config` | defaults, UI metadata, glossary, tiers, question list |
| `GET  /api/model` | the specification markdown |
| `POST /api/simulate` | run one history → full snapshot (synchronous) |
| `POST /api/montecarlo` | start an ensemble job → `{job_id}` |
| `GET  /api/montecarlo/<job_id>` | poll progress / collect the result |

`POST` bodies are a JSON object of parameters (any subset of `Params`; unknown
keys are ignored), optionally with `n_runs` / `record_every`.

## License

MIT.
