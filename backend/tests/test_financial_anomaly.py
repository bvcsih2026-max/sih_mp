import pandas as pd
from ml.detectors.financial_anomaly import detect_financial_anomalies


def test_financial_anomaly_detects_unusual_project():
    records = [
        {
            "work_id": "WORK-001",
            "sanction_amount": 1000000,
            "expenditure_amount": 420000,
            "district": "District A",
            "state": "State A",
            "work_type": "Road",
            "cost_per_unit": 5000,
        },
        {
            "work_id": "WORK-002",
            "sanction_amount": 980000,
            "expenditure_amount": 450000,
            "district": "District A",
            "state": "State A",
            "work_type": "Road",
            "cost_per_unit": 4900,
        },
        {
            "work_id": "WORK-003",
            "sanction_amount": 1050000,
            "expenditure_amount": 470000,
            "district": "District A",
            "state": "State A",
            "work_type": "Road",
            "cost_per_unit": 5100,
        },
        {
            "work_id": "WORK-004",
            "sanction_amount": 1500000,
            "expenditure_amount": 700000,
            "district": "District B",
            "state": "State A",
            "work_type": "Bridge",
            "cost_per_unit": 15000,
        },
        {
            "work_id": "WORK-005",
            "sanction_amount": 1400000,
            "expenditure_amount": 680000,
            "district": "District B",
            "state": "State A",
            "work_type": "Bridge",
            "cost_per_unit": 14500,
        },
        {
            "work_id": "WORK-006",
            "sanction_amount": 2000000,
            "expenditure_amount": 1950000,
            "district": "District C",
            "state": "State B",
            "work_type": "Drainage",
            "cost_per_unit": 50000,
        },
    ]

    df = pd.DataFrame(records)
    signals = detect_financial_anomalies(df)

    assert len(signals) > 0
    assert all(signal["detector_type"] == "financial_anomaly" for signal in signals)
    assert any(signal["work_id"] == "WORK-006" for signal in signals)

    # Check signal fields and values
    for signal in signals:
        assert "signal_id" in signal
        assert signal["schema_version"] == "1.0"
        assert signal["priority"] in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
        assert 0 <= signal["anomaly_score"] <= 100
        assert "observed_evidence" in signal
        assert "baseline" in signal
        assert "explanation" in signal
        assert isinstance(signal["possible_explanation"], list)
        assert isinstance(signal["recommended_verification"], list)

        # Check safety/legal compliance - no fraud accusations
        full_text = (
            signal["title"]
            + " "
            + signal["explanation"]
            + " ".join(signal["possible_explanation"])
            + " ".join(signal["recommended_verification"])
        ).lower()
        assert "fraud" not in full_text
        assert "corrupt" not in full_text


def test_financial_anomaly_inliers_not_flagged():
    # Normal consistent projects should not produce high anomaly signals
    records = [
        {
            "work_id": f"WORK-NORM-{i}",
            "sanction_amount": 1000000,
            "expenditure_amount": 450000 + (i * 1000),
            "district": "District X",
            "state": "State Y",
            "work_type": "School",
        }
        for i in range(10)
    ]
    df = pd.DataFrame(records)
    signals = detect_financial_anomalies(df)
    assert len(signals) == 0


def test_financial_anomaly_empty_dataframe():
    assert detect_financial_anomalies(pd.DataFrame()) == []
    assert detect_financial_anomalies(None) == []
