from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from gooey_gui.types.run_debug_info_props import AuthorProps


class EcoRegionProps(BaseModel):
    """Where the run's electricity came from, for the modal's region block."""

    country_code: str  # ISO 3166-1 alpha-2; the modal shows its flag and name
    # tooltip when the serving site isn't known; None when the provider pins it
    assumption: str | None = None
    gco2e_per_kwh: float
    gco2e_per_kwh_min: float
    gco2e_per_kwh_max: float
    # energy source -> share of generation, 0..1, largest first
    mix: dict[str, float]


class EcoModelTokens(BaseModel):
    """One model's tokens in the run, shown under the cost."""

    model_id: str
    label: str
    input_tokens: int
    output_tokens: int


class EcoCostProps(BaseModel):
    """A run's summed eco estimate, as `usage_costs.eco.run_eco_cost` returns it."""

    confidence: Literal["low", "medium", "high"]
    reasons: list[str] = []
    models: list[EcoModelTokens] = []
    co2e_grams: float
    co2e_min: float
    co2e_max: float
    energy_wh: float
    water_ml: float
    water_data_center_ml: float
    region: EcoRegionProps | None = None


class EcoLabelProps(EcoCostProps):
    """Per-run figures for the "Run Cost & Environment Impact" modal, opened
    from the top bar's cost readout. The modal scales them client-side with a
    runs slider. Nested in RecipeTopBarProps."""

    run_cost: str
    run_cost_usd: float | None = None
    methodology_url: str
    run_by: AuthorProps | None = None
    charged_to: AuthorProps | None = None
    balance: str | None = None
    balance_url: str | None = None
