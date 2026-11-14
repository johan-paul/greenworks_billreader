from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

class EvidenceValue(BaseModel):
    model_config = ConfigDict(extra='forbid')
    value: float = Field(allow_inf_nan=False)
    unit: Literal['kWh', 'kVAh', 'kW', 'kVA', 'INR', 'INR/kWh', 'ratio']
    quote: str = Field(min_length=1, description='Exact supporting text from this page')

class PageExtraction(BaseModel):
    model_config = ConfigDict(extra='forbid')
    document_type: Literal['grid', 'solar', 'wind', 'other', 'unknown']
    supplier: str | None
    consumer: str | None
    account_number: str | None
    invoice_number: str | None
    billing_period: str | None = Field(description='Period of supplied energy, not payment date')
    total_consumption: EvidenceValue | None
    grid_import: EvidenceValue | None
    solar_energy: EvidenceValue | None
    wind_energy: EvidenceValue | None
    export_energy: EvidenceValue | None
    current_charges: EvidenceValue | None
    total_payable: EvidenceValue | None
    energy_rate: EvidenceValue | None
    contract_demand: EvidenceValue | None
    maximum_demand: EvidenceValue | None
    power_factor: EvidenceValue | None
    penalties: EvidenceValue | None
    notes: list[str]

ENERGY_FIELDS = ['total_consumption', 'grid_import', 'solar_energy', 'wind_energy', 'export_energy']

def review_issues(data: PageExtraction, text: str | None) -> list[str]:
    issues = ['Human review required before aggregation or reporting.']
    for name in PageExtraction.model_fields:
        item = getattr(data, name)
        if not isinstance(item, EvidenceValue):
            continue
        if text is not None and ' '.join(item.quote.split()) not in ' '.join(text.split()):
            issues.append(f'{name}: supporting quote not found in page text')
        if name in ENERGY_FIELDS and (item.value < 0 or item.unit != 'kWh'):
            issues.append(f'{name}: expected nonnegative kWh; do not convert kVAh without verified power factor')
        if name == 'power_factor' and (item.unit != 'ratio' or not 0 < item.value <= 1):
            issues.append('power_factor: expected a ratio in (0, 1]')
    if text is None:
        issues.append('Vision extraction: verify all values against the original page.')
    return issues
