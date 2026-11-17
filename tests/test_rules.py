from billintel.rules import parse_rules


def test_unknown_layout_abstains():
    assert parse_rules("Ordinary purchase invoice 42") is None


def test_solar_hsn_is_not_energy_and_arithmetic_is_checked():
    text = """Invoice GST/099/25-26
Supply of Electricity (Green Solar Energy) 27160000 | 100.00 kwh 5.00/kwh| 500.00
Peak HR- APRIL-2025
Supply of Electricity (Green Solar Energy) 27160000 | 200.00 kwh 5.00/kwh| 1,000.00
Total | 1,500.00"""
    data, meta = parse_rules(text)
    assert data.total_consumption is None
    assert data.solar_energy is None
    assert meta["derived"]["solar_supply_kwh"]["value"] == 300
    assert data.total_payable.value == 1500
    assert data.invoice_number == "GST/099/25-26"
    _, meta = parse_rules(text.replace("1,000.00", "1,100.00"))
    assert not meta["derived"]


def test_grid_header_excludes_discounted_amount():
    text = """MAHARASHTRA STATE ELECTRICITY DISTRIBUTION
BILL OF SUPPLY FOR THE MONTH OF JUNE-2026 12345678901
11,000 Consumer Name : EXAMPLE
IF PAID UPTO 01/07/2026 10,000
Contract Demand (KVA) : 500"""
    data, _ = parse_rules(text)
    assert data.total_payable.value == 11000
    assert data.total_consumption is None
    assert data.contract_demand.value == 500


def test_consumption_uses_kwh_column_not_kvah():
    text = """CURRENT CONSUMPTION DETAILS
Reading Details KWH KVAH
Total Consumption 123.00 145.00
Billed PF : 0.99"""
    data, _ = parse_rules(text)
    assert data.total_consumption.value == 123
    assert data.total_consumption.unit == "kWh"
    assert data.power_factor.value == 0.99


def test_tangedco_does_not_sum_surcharge_units():
    text = """High Tension Bill for the Month of April 2025
1. Industrial Consumption 8.00 per unit 100 800.00
2. Peak Hour Consumption 2.00 per unit 30 60.00
Net Amount Payable 900.00
Amount Payable after due date 950.00"""
    data, _ = parse_rules(text)
    assert data.total_payable.value == 900
    assert data.total_consumption is None
