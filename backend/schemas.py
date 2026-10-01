"""Pydantic response models (Phase 2.2).

Values are keys + numbers only: the Italian texts live in the frontend (methodology §11).
Nulls mean "not analysed" (or, for sensitivity fields, "not applicable").
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

LevelName = Literal["cell", "zone"]


class Health(BaseModel):
    status: str
    built_at: str | None = None


class Weights(BaseModel):
    """Effective weights used (active indicators, sum 1)."""

    weights: dict[str, float]
    is_default: bool


class IndicatorDetail(BaseModel):
    key: str
    raw_column: str
    raw_value: float | None
    score: float | None  # 0–100
    weight: float  # effective weight (0–1)
    contribution: float | None  # weight × score, in IPF points


class Driver(BaseModel):
    indicator: str
    score: float
    weight: float
    contribution: float


class Trees(BaseModel):
    green_deficit_m2: float | None
    plantable_m2: float | None
    trees_new: (
        int | None
    )  # model estimate (plantable share of the deficit); zones: residential cells
    trees_new_nonres: int | None  # zones only: estimate in non-residential cells (Q50)
    target_green_share: float  # e.g. 0.15
    trees_for_target: int | None  # trees whose crowns would close the whole deficit
    cells_below_target: int | None  # zones only: residential cells below the target share


class ItemSensitivity(BaseModel):
    applicable: bool
    top_n: int
    rank_p5: int | None
    rank_p95: int | None
    top_n_freq: float | None
    class_stability: float | None
    robust: bool | None


class ZoneRef(BaseModel):
    zone_id: int | None
    name: str | None


class Detail(Weights):
    level: LevelName
    id: str
    grid: int | None  # cell size in metres (cells only)
    analysed: bool
    ipf: float | None
    ipf_class: int  # 1..4, 0 = not analysed
    class_key: str | None  # i18n key: bassa / media / medio_alta / alta
    rank: int | None
    ranked_items: int  # number of analysed items at this level
    indicators: list[IndicatorDetail]
    top_drivers: list[Driver]
    trees: Trees
    sensitivity: ItemSensitivity
    stats: dict[str, Any]  # level-specific descriptive values (area, residents, green, …)
    zone: ZoneRef | None = None  # cells only


class RankingItem(BaseModel):
    id: str
    name: str | None  # zone name (for cells: the containing zone)
    zone_id: int | None
    ipf: float
    ipf_class: int
    rank: int
    rank_p5: int | None
    rank_p95: int | None
    top_n_freq: float | None
    robust: bool | None
    trees_new: int | None  # zones: residential cells only (Q50)
    trees_new_nonres: int | None  # zones only
    residential: bool | None  # cells only
    residents: float | None
    contributions: dict[str, float]  # weight × score per active indicator (sums to ipf)


class Ranking(Weights):
    level: LevelName
    grid: int | None
    total: int
    items: list[RankingItem]


class SensitivityItem(BaseModel):
    id: str
    rank: int
    rank_p5: int | None
    rank_p95: int | None
    top_n_freq: float | None
    class_stability: float | None
    robust: bool | None


class Sensitivity(Weights):
    level: LevelName
    grid: int | None
    applicable: bool
    parameters: dict[str, Any]
    summary: dict[str, Any] | None  # spearman_mean, top_n_overlap_*, robust_share, one_at_a_time
    items: list[SensitivityItem]


class SimulationState(BaseModel):
    veg_m2: float  # satellite vegetation (Q49)
    veg_share: float
    score_green_deficit: float
    ipf: float
    ipf_class: int
    class_key: str
    rank: int  # against the rest of the city, unchanged


class Simulation(Weights):
    """Tree simulator (FR-28, Q37, Q37b). Only the green-deficit indicator changes."""

    level: LevelName
    id: str
    grid: int | None
    trees: int
    years: int | None = None  # Q37b: years since planting (None = mature crowns, the Q37 view)
    growth_share: float | None = None  # crown fraction at `years` (linear growth model)
    maturity_years: int | None = None  # years to full crown (trees.growth_years_maturity)
    years_to_target: int | None = None  # cells: first year the cell reaches the target share
    years_to_class_change: int | None = None  # cells: first year the class drops
    added_veg_m2: float  # trees × crown area × growth_share
    crown_area_m2: float
    target_green_share: float
    trees_estimate: int | None  # the model's estimate (trees_new)
    trees_for_target: int  # trees to close the whole deficit to the target share
    before: SimulationState
    after: SimulationState


class Metadata(BaseModel):
    """metadata.json as built by the pipeline (docs/artefacts.md), plus API hints."""

    model_config = ConfigDict(extra="allow")

    schema_version: int
    city: str
    built_at: str
    indicators: dict[str, Any]
    weights: dict[str, Any]
    classes: dict[str, Any]
    disclaimers: list[str]
    layers: list[str]
