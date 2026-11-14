from __future__ import annotations
from pydantic import BaseModel, ConfigDict, Field, model_validator

class Scenario(BaseModel):
    model_config = ConfigDict(extra='forbid')
    site: str = Field(min_length=1)
    period: str = Field(min_length=1)
    assumptions_source: str = Field(min_length=1)
    reviewed: bool
    grid_import_kwh: float = Field(ge=0, allow_inf_nan=False)
    solar_used_kwh: float = Field(ge=0, allow_inf_nan=False)
    wind_used_kwh: float = Field(ge=0, allow_inf_nan=False)
    avoided_grid_rate_inr_per_kwh: float = Field(ge=0, allow_inf_nan=False)
    renewable_cost_inr: float = Field(ge=0, allow_inf_nan=False,
        description='All-in cost including PPA, wheeling, losses, taxes and other incremental costs')
    export_credit_inr: float = Field(ge=0, allow_inf_nan=False)
    grid_emission_kg_per_kwh: float = Field(ge=0, allow_inf_nan=False)
    renewable_emission_kg_per_kwh: float = Field(ge=0, allow_inf_nan=False)
    power_factor: float | None = Field(default=None, gt=0, le=1)
    penalties_inr: float | None = Field(default=None, ge=0, allow_inf_nan=False)

    @model_validator(mode='after')
    def must_review(self):
        if not self.reviewed:
            raise ValueError('Reconcile site, period, units and overlapping bills before calculating')
        return self

def analyze(s: Scenario):
    renewable = s.solar_used_kwh + s.wind_used_kwh
    total = s.grid_import_kwh + renewable
    recommendations = []
    if s.power_factor is not None and s.power_factor < 0.95:
        recommendations.append('Review power-factor trend and tariff penalties with an electrical engineer; 0.95 is a screening threshold, not a tariff rule.')
    if s.penalties_inr is not None and s.penalties_inr > 0:
        recommendations.append('Identify the penalty reason and check payment dates, demand limits and power factor.')
    if s.grid_import_kwh > 0:
        recommendations.append('Compare interval load and renewable generation before sizing additional renewable capacity or storage.')
    recommendations.append('Compare kWh per unit of production and billing days across periods before concluding efficiency improved.')
    return {
        'site': s.site, 'period': s.period, 'type': 'user-supplied counterfactual scenario, not verified realized savings',
        'assumptions': s.model_dump(),
        'total_accounted_consumption_kwh': total,
        'renewable_share_percent': round(100 * renewable / total, 2) if total else None,
        'estimated_net_savings_inr': round(renewable * s.avoided_grid_rate_inr_per_kwh - s.renewable_cost_inr + s.export_credit_inr, 2),
        'estimated_avoided_emissions_kg_co2e': round(renewable * (s.grid_emission_kg_per_kwh - s.renewable_emission_kg_per_kwh), 2),
        'recommendations': recommendations,
        'limitations': ['Energy must represent mutually exclusive, delivered consumption for one site and period.',
            'Fixed grid charges are assumed unchanged. Use the avoidable marginal rate, not total bill divided by units.',
            'Emissions are a scenario estimate; renewable ownership and reporting method require separate verification.',
            'Exports are excluded from consumed energy and emissions estimates; export credits are entered separately.']}
