"""The in-code domain registry: the label-neutral vocabulary a chart is dressed in.

A :class:`Domain` bundles the subject matter of a chart - titles, category names, series names, the y-axis quantity and
its unit, and a value range. None of it touches a verdict (docs/adr/0018), so domains are pure variety: adding one is
appending a literal to :data:`DOMAINS`, and the more unlike each other they are, the better the dataset.

Two domains are deliberately absurd (``improbable``, ``mundane-absurd``). Whimsical categories and units give a vision
model no pre-encoded prior to lean on ("revenue trends up", "this axis is probably dollars"), forcing it to judge the
chart's actual content - which is exactly what the checker is meant to do.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Domain:
  """The label-neutral vocabulary for a chart. Every field is cosmetic; none affects a rule verdict.

  ``categories`` must hold at least six entries (recipes sample up to five), and ``series_names`` at least two.
  ``quantity`` and ``unit`` compose the numeric-axis label, e.g. ``"Revenue (thousands USD)"``.
  """

  name: str
  titles: tuple[str, ...]
  categories: tuple[str, ...]
  category_axis_label: str
  series_names: tuple[str, ...]
  quantity: str
  unit: str
  value_range: tuple[float, float]


DOMAINS: tuple[Domain, ...] = (
  Domain(
    name="business",
    titles=("Quarterly revenue by region", "Sales performance", "Revenue breakdown"),
    categories=("North", "South", "East", "West", "Central", "Coastal", "Metro", "Rural"),
    category_axis_label="Region",
    series_names=("2023", "2024", "2025", "Plan", "Actual"),
    quantity="Revenue",
    unit="thousands USD",
    value_range=(20.0, 950.0),
  ),
  Domain(
    name="lab-science",
    titles=("Reaction yield by compound", "Assay results", "Catalyst efficiency"),
    categories=("Reagent A", "Reagent B", "Catalyst X", "Buffer", "Control", "Enzyme", "Substrate"),
    category_axis_label="Compound",
    series_names=("Trial 1", "Trial 2", "Replicate", "Baseline"),
    quantity="Yield",
    unit="%",
    value_range=(2.0, 98.0),
  ),
  Domain(
    name="public-health",
    titles=("Recovery time by treatment", "Patient outcomes", "Treatment comparison"),
    categories=("Placebo", "Dose low", "Dose high", "Therapy", "Combined", "Standard care"),
    category_axis_label="Treatment",
    series_names=("Cohort A", "Cohort B", "Follow-up"),
    quantity="Recovery time",
    unit="days",
    value_range=(1.0, 45.0),
  ),
  Domain(
    name="climate-energy",
    titles=("Emissions by sector", "Energy mix", "Carbon output by source"),
    categories=("Coal", "Gas", "Solar", "Wind", "Hydro", "Nuclear", "Biomass"),
    category_axis_label="Sector",
    series_names=("2020", "2025", "Projected"),
    quantity="Emissions",
    unit="Mt CO2",
    value_range=(0.5, 120.0),
  ),
  Domain(
    name="sports",
    titles=("Points by team", "Season standings", "Scoring by club"),
    categories=("Falcons", "Sharks", "Wolves", "Eagles", "Bears", "Lions", "Hawks"),
    category_axis_label="Team",
    series_names=("Home", "Away", "Last season"),
    quantity="Points",
    unit="points",
    value_range=(5.0, 110.0),
  ),
  Domain(
    name="demographics",
    titles=("Population by city", "Urban growth", "Residents by district"),
    categories=("Riverton", "Lakeside", "Hilltop", "Bayview", "Oakdale", "Fairmont", "Westgate"),
    category_axis_label="City",
    series_names=("Census", "Estimate", "Forecast"),
    quantity="Population",
    unit="thousands",
    value_range=(8.0, 4200.0),
  ),
  Domain(
    name="improbable",
    titles=("Towel readiness across species", "Babel fish uptake by planet", "Improbability by star system"),
    categories=("Vogons", "Dolphins", "Magratheans", "Betelgeuse V", "Golgafrinchans", "Earthlings", "Krikkiters"),
    category_axis_label="Species",
    series_names=("Before lunch", "After lunch", "Improbable epoch"),
    quantity="Improbability",
    unit="kilo-Adams",
    value_range=(1.0, 42.0),
  ),
  Domain(
    name="mundane-absurd",
    titles=("Sock loss by wash cycle", "Odd-sock incidents by machine", "Laundry entropy by method"),
    categories=("Front-loader", "Top-loader", "Launderette", "Hand wash", "Tumble dry", "Spin only"),
    category_axis_label="Method",
    series_names=("Whites", "Colours", "Delicates"),
    quantity="Socks lost",
    unit="socks per load",
    value_range=(0.0, 7.0),
  ),
)
