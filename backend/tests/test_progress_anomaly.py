import pandas as pd
from ml.detectors.progress_anomaly import detect_progress_anomalies


def test_progress_anomaly_detects_mismatch_and_inconsistent_state():
    records = [
        {
            "work_id": "WORK-101",
            "sanction_amount": 1000000,
            "expenditure_amount": 900000,
            "physical_progress_percentage": 34,
            "project_status": "In Progress",
            "start_date": "2024-01-01",
        },
        {
            "work_id": "WORK-102",
            "sanction_amount": 800000,
            "expenditure_amount": 0,
            "physical_progress_percentage": 100,
            "project_status": "Completed",
            "start_date": "2023-06-01",
        },
        {
            "work_id": "WORK-103",
            "sanction_amount": 1500000,
            "expenditure_amount": 1200000,
            "physical_progress_percentage": 80,
            "project_status": "In Progress",
            "start_date": "2020-01-01",
        },
        {
            "work_id": "WORK-104",
            "sanction_amount": 1000000,
            "expenditure_amount": 450000,
            "physical_progress_percentage": 45,
            "project_status": "In Progress",
            "start_date": "2024-05-01",
        },
    ]

    df = pd.DataFrame(records)
    signals = detect_progress_anomalies(df)

    assert len(signals) == 3
    assert all(signal["detector_type"] == "progress_mismatch" for signal in signals)

    work_ids = [signal["work_id"] for signal in signals]
    assert "WORK-101" in work_ids
    assert "WORK-102" in work_ids
    assert "WORK-103" in work_ids
    assert "WORK-104" not in work_ids

    for signal in signals:
        assert "signal_id" in signal
        assert signal["schema_version"] == "1.0"
        assert signal["priority"] in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
        assert 30 <= signal["anomaly_score"] <= 100
        assert "observed_evidence" in signal
        assert "baseline" in signal
        assert "explanation" in signal
        assert len(signal["possible_explanation"]) > 0
        assert len(signal["recommended_verification"]) > 0

        # Verify legal/safety guardrails
        text = (
            signal["title"]
            + " "
            + signal["explanation"]
            + " ".join(signal["possible_explanation"])
            + " ".join(signal["recommended_verification"])
        ).lower()
        assert "fraud" not in text
        assert "corrupt" not in text


def test_progress_anomaly_empty_dataframe():
    assert detect_progress_anomalies(pd.DataFrame()) == []
    assert detect_progress_anomalies(None) == []
