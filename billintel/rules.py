"""Conservative layout-specific parsers. Unknown layouts abstain; no values are hardcoded."""

import re
from .schema import PageExtraction

NUM = r"\d[\d,]*(?:\.\d+)?"


def number(value):
    return float(value.replace(",", ""))


def parse_rules(text):
    data = {key: None for key in PageExtraction.model_fields}
    data.update(document_type="unknown", notes=[])
    derived = {}
    template = None

    def string(field, pattern):
        m = re.search(pattern, text, re.I | re.M)
        if m:
            data[field] = m.group(1).strip()

    def numeric(field, pattern, unit, group=1):
        m = re.search(pattern, text, re.I | re.M)
        if m:
            data[field] = {
                "value": number(m.group(group)),
                "unit": unit,
                "quote": m.group(0).strip(),
            }

    if "MAHARASHTRA STATE ELECTRICITY DISTRIBUTION" in text.upper():
        template = "msedcl-header-v1"
        data.update(
            document_type="grid",
            supplier="MAHARASHTRA STATE ELECTRICITY DISTRIBUTION CO. LTD.",
        )
        string("billing_period", r"BILL OF SUPPLY FOR THE MONTH OF\s+([A-Z]+-\d{4})")
        string(
            "invoice_number",
            r"BILL OF SUPPLY FOR THE MONTH OF\s+[A-Z]+-\d{4}\s+(\d{10,})",
        )
        string("account_number", r"Consumer No\.\s*:\s*(\d+)")
        string("consumer", r"Consumer Name\s*:\s*([^\n]+)")
        numeric("contract_demand", rf"Contract Demand\s*\(KVA\)\s*:\s*({NUM})", "kVA")
        # Specific text layout: normal payable precedes Consumer Name; excludes early/late rows.
        numeric("total_payable", rf"^\s*({NUM})\s+Consumer Name\s*:", "INR")
    elif "CURRENT CONSUMPTION DETAILS" in text.upper() and "Billed PF" in text:
        template = "msedcl-consumption-v1"
        data["document_type"] = "grid"
        string("account_number", r"Consumer No\.\s*:\s*(\d+)")
        string("billing_period", r"Bill Month\s*:\s*([A-Z]+-\d{4})")
        if re.search(r"Reading Details\s+KWH\s+KVAH", text, re.I):
            numeric("total_consumption", rf"^\s*Total Consumption\s+({NUM})", "kWh")
        numeric("power_factor", rf"Billed PF\s*:\s*({NUM})", "ratio")
    elif "High Tension Bill" in text and "Net Amount Payable" in text:
        template = "tangedco-header-v1"
        data.update(
            document_type="grid",
            supplier="TamilNadu Generation and Distribution Corporation Ltd.",
        )
        string("consumer", r"To:\s*(.+?)(?:\s{2,}|\n)")
        string("account_number", r"Service No\.\s*(\d+)")
        string("invoice_number", r"Bill No\.\s*(\S+)")
        string("billing_period", r"for the Month of\s+([A-Za-z]+\s+\d{4})")
        numeric("total_payable", rf"^\s*Net Amount Payable\s+({NUM})", "INR")
        numeric("current_charges", rf"21\.\s*Assessment Amount\s+({NUM})", "INR")
        numeric("contract_demand", rf"Permitted MD\s*:\s*({NUM})\s*KVA", "kVA")
        data["notes"].append(
            "Industrial billed units are not assumed to be total facility consumption. Annexures and renewable adjustments need reconciliation."
        )
    elif "Supply of Electricity (Green Solar Energy)" in text:
        template = "solar-supply-lines-v1"
        data["document_type"] = "solar"
        string("invoice_number", r"\b(GST/\d+/\d{2}-\d{2})\b")
        string("billing_period", r"(?:Peak HR|Normal HR)\s*-\s*([A-Z]+-\d{4})")
        rows = []
        for line in text.splitlines():
            if "Supply of Electricity (Green Solar Energy)" not in line:
                continue
            m = re.search(
                rf"({NUM})\s*kwh\s*({NUM})\s*[|/]?\s*kwh\s*[|]?\s*({NUM})", line, re.I
            )
            if m:
                quantity, rate, amount = [number(v) for v in m.groups()]
                if abs(quantity * rate - amount) <= 0.05:
                    rows.append(
                        {
                            "quantity_kwh": quantity,
                            "rate_inr_per_kwh": rate,
                            "amount_inr": amount,
                            "quote": line.strip(),
                        }
                    )
        expected = text.count("Supply of Electricity (Green Solar Energy)")
        if rows and len(rows) == expected:
            derived["solar_supply_kwh"] = {
                "value": round(sum(r["quantity_kwh"] for r in rows), 3),
                "unit": "kWh",
                "formula": "sum of solar supply line quantities",
                "line_items": rows,
                "warning": "Supplied energy, not necessarily delivered self-consumption; reconcile losses and utility adjustments.",
            }
            rates = {r["rate_inr_per_kwh"] for r in rows}
            if len(rates) == 1:
                data["energy_rate"] = {
                    "value": next(iter(rates)),
                    "unit": "INR/kWh",
                    "quote": rows[0]["quote"],
                }
        else:
            data["notes"].append(
                "Solar line arithmetic or row coverage failed; no energy sum returned."
            )
        numeric("total_payable", rf"^\s*Total\s*\|\s*({NUM})\s*$", "INR")
        data["notes"].append(
            "Solar energy sum is reported separately as derived, not as a printed total."
        )
    if template is None:
        return None
    data["notes"].append(
        "Template rules; human review required. Unmatched fields remain null."
    )
    return PageExtraction(**data), {"template": template, "derived": derived}
