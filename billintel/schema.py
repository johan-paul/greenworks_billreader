"""Typed extraction fields and evidence checks; not a training-data model."""

from __future__ import annotations
from typing import Literal
import re
import math
from pydantic import BaseModel, ConfigDict, Field


class EvidenceValue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: float = Field(allow_inf_nan=False)
    unit: Literal["kWh", "kVAh", "kW", "kVA", "INR", "INR/kWh", "ratio"]
    quote: str = Field(min_length=1, description="Exact supporting text from this page")


class EnergyValue(EvidenceValue):
    value: float = Field(ge=0, allow_inf_nan=False)
    unit: Literal["kWh", "kVAh"]


class MoneyValue(EvidenceValue):
    unit: Literal["INR"]


class RateValue(EvidenceValue):
    unit: Literal["INR/kWh"]


class DemandValue(EvidenceValue):
    value: float = Field(ge=0, allow_inf_nan=False)
    unit: Literal["kW", "kVA"]


class PowerFactorValue(EvidenceValue):
    value: float = Field(gt=0, le=1, allow_inf_nan=False)
    unit: Literal["ratio"]


class PageExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_type: Literal["grid", "solar", "wind", "other", "unknown"]
    supplier: str | None
    consumer: str | None
    account_number: str | None
    invoice_number: str | None
    billing_period: str | None = Field(
        description="Period of supplied energy, not payment date"
    )
    total_consumption: EnergyValue | None
    grid_import: EnergyValue | None
    solar_energy: EnergyValue | None
    wind_energy: EnergyValue | None
    export_energy: EnergyValue | None
    current_charges: MoneyValue | None
    total_payable: MoneyValue | None
    energy_rate: RateValue | None
    contract_demand: DemandValue | None
    maximum_demand: DemandValue | None
    power_factor: PowerFactorValue | None
    penalties: MoneyValue | None
    notes: list[str]


ENERGY_FIELDS = [
    "total_consumption",
    "grid_import",
    "solar_energy",
    "wind_energy",
    "export_energy",
]


def review_issues(data: PageExtraction, text: str | None) -> list[str]:
    issues = ["Human review required before aggregation or reporting."]
    for name in PageExtraction.model_fields:
        item = getattr(data, name)
        if not isinstance(item, EvidenceValue):
            continue
        if text is not None and " ".join(item.quote.split()) not in " ".join(
            text.split()
        ):
            issues.append(f"{name}: supporting quote not found in page text")
        numbers = [
            float(n.replace(",", ""))
            for n in re.findall(r"-?\d[\d,]*(?:\.\d+)?", item.quote)
        ]
        if not any(
            math.isclose(item.value, n, rel_tol=1e-9, abs_tol=1e-6) for n in numbers
        ):
            issues.append(f"{name}: reported number is absent from supporting quote")
        source_labels = {
            "grid_import": r"\b(grid|import)\b",
            "solar_energy": r"\bsolar\b",
            "wind_energy": r"\bwind\b",
            "export_energy": r"\bexport\b",
        }
        if name in source_labels and not re.search(
            source_labels[name], item.quote, re.I
        ):
            issues.append(f"{name}: source label is absent from supporting quote")
        if name in ENERGY_FIELDS and (item.value < 0 or item.unit != "kWh"):
            issues.append(
                f"{name}: expected nonnegative kWh; do not convert kVAh without verified power factor"
            )
        if name == "power_factor" and (item.unit != "ratio" or not 0 < item.value <= 1):
            issues.append("power_factor: expected a ratio in (0, 1]")
    if text is None:
        issues.append("Vision extraction: verify all values against the original page.")
    return issues
