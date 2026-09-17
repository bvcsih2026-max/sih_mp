from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest


DEFAULT_SIGNAL_TEMPLATE = {
    "signal_id": "",
    "schema_version": "1.0",
    "work_id": "",
    "detector_type": "financial_anomaly",
    "priority": "LOW",
    "anomaly_score": 0,
    "title": "Unusual financial pattern",
    "observed_evidence": {},
    "baseline": {},
    "explanation": "",
    "possible_explanation": [],
    "recommended_verification": [],
    "status": "NEW",
    "source": {},
    "metadata": {},
}


def _score_to_priority(score: int) -> str:
    if score < 30:
        return "LOW"
    if score < 60:
        return "MEDIUM"
    if score < 80:
        return "HIGH"
    return "CRITICAL"


def _generate_signal_id(index: int) -> str:
    return f"SIG-{index:05d}"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if pd.isna(value) or value is None:
            return default
        val = float(value)
        if np.isinf(val) or np.isnan(val):
            return default
        return val
    except (TypeError, ValueError):
        return default


def _build_financial_features(df: pd.DataFrame) -> pd.DataFrame:
    frame = df.copy()
    numeric_columns = [
        "sanction_amount",
        "expenditure_amount",
        "cost_per_unit",
        "physical_progress_percentage",
    ]
    for column in numeric_columns:
        if column in frame.columns:
            frame[column] = frame[column].apply(lambda x: _safe_float(x, 0.0))
        else:
            frame[column] = 0.0

    frame["expenditure_percentage"] = np.where(
        frame["sanction_amount"] > 0,
        (frame["expenditure_amount"] / frame["sanction_amount"]) * 100.0,
        0.0,
    )

    overall_median = float(frame["expenditure_percentage"].median()) if not frame.empty else 0.0
    frame["overall_median"] = overall_median
    frame["overall_delta"] = frame["expenditure_percentage"] - overall_median

    for group_col, group_name in [("district", "district"), ("state", "state"), ("work_type", "work_type")]:
        if group_col in frame.columns and not frame[group_col].isna().all():
            counts = frame.groupby(group_col)[group_col].transform("count")
            medians = frame.groupby(group_col)["expenditure_percentage"].transform("median")
            # If group has only 1 record, fallback to overall median for robust comparison
            effective_medians = np.where(counts >= 2, medians, overall_median)
            frame[f"{group_name}_median"] = effective_medians
        else:
            frame[f"{group_name}_median"] = overall_median

    frame["district_delta"] = frame["expenditure_percentage"] - frame["district_median"]
    frame["state_delta"] = frame["expenditure_percentage"] - frame["state_median"]
    frame["work_type_delta"] = frame["expenditure_percentage"] - frame["work_type_median"]

    if "cost_per_unit" in frame.columns and frame["cost_per_unit"].gt(0).any():
        frame["cost_per_unit_ratio"] = np.where(
            frame["cost_per_unit"] > 0,
            frame["sanction_amount"] / frame["cost_per_unit"],
            0.0,
        )
        overall_cpu_median = float(frame[frame["cost_per_unit"] > 0]["cost_per_unit"].median()) if frame["cost_per_unit"].gt(0).any() else 0.0
        frame["overall_cpu_median"] = overall_cpu_median
        for group_col, group_name in [("district", "district"), ("work_type", "work_type")]:
            if group_col in frame.columns:
                counts = frame.groupby(group_col)[group_col].transform("count")
                cpu_medians = frame.groupby(group_col)["cost_per_unit"].transform("median")
                effective_cpu = np.where(counts >= 2, cpu_medians, overall_cpu_median)
                frame[f"{group_name}_cpu_median"] = effective_cpu
            else:
                frame[f"{group_name}_cpu_median"] = overall_cpu_median
        frame["cost_per_unit_delta"] = frame["cost_per_unit"] - frame["district_cpu_median"]
    else:
        frame["cost_per_unit_ratio"] = 0.0
        frame["district_cpu_median"] = 0.0
        frame["work_type_cpu_median"] = 0.0
        frame["cost_per_unit_delta"] = 0.0

    return frame


def _compute_anomaly_scores(frame: pd.DataFrame) -> List[int]:
    n_samples = len(frame)
    if n_samples == 0:
        return []

    model_features = [
        "expenditure_percentage",
        "overall_delta",
        "district_delta",
        "state_delta",
        "work_type_delta",
        "cost_per_unit_ratio",
        "cost_per_unit_delta",
    ]
    model_data = frame[model_features].astype(float).fillna(0.0)

    # Use IsolationForest for larger datasets
    if n_samples >= 5:
        model = IsolationForest(contamination=0.1, random_state=42, n_estimators=100)
        model.fit(model_data)
        dec_scores = model.decision_function(model_data)

        scores = []
        for idx, dec_score in enumerate(dec_scores):
            row = frame.iloc[idx]
            max_delta = max(
                abs(row["district_delta"]),
                abs(row["state_delta"]),
                abs(row["work_type_delta"]),
                abs(row["overall_delta"]),
            )

            # Check if this is truly an outlier (either dec_score <= -0.03 or max_delta >= 25.0)
            if dec_score <= -0.03 or max_delta >= 25.0:
                magnitude = max(0.0, -dec_score)
                base_score = 30.0 + (magnitude * 200.0) + (max_delta * 0.7)
                raw_score = min(100.0, max(30.0, base_score))
            else:
                # Normal inlier
                raw_score = min(25.0, max(0.0, max_delta * 0.5))

            scores.append(int(round(raw_score)))
        return scores
    else:
        # Statistical fallback for small datasets (< 5 samples)
        scores = []
        for _, row in frame.iterrows():
            max_delta = max(
                abs(row["district_delta"]),
                abs(row["state_delta"]),
                abs(row["work_type_delta"]),
                abs(row["overall_delta"]),
            )
            exp_pct = row["expenditure_percentage"]

            if max_delta >= 30.0 or exp_pct >= 90.0 or (exp_pct <= 5.0 and row["sanction_amount"] > 500000):
                score = min(100, max(30, int(30 + max_delta * 0.8)))
            else:
                score = min(25, int(max_delta * 0.4))
            scores.append(score)
        return scores


def _build_signal_from_record(
    record: pd.Series, score: int, index: int, anomaly_basis: Dict[str, Any]
) -> Dict[str, Any]:
    work_id = str(record.get("work_id", f"WORK-{index:03d}"))
    expenditure_percentage = float(record.get("expenditure_percentage", 0.0))
    district_median = float(record.get("district_median", expenditure_percentage))
    state_median = float(record.get("state_median", expenditure_percentage))
    work_type_median = float(record.get("work_type_median", expenditure_percentage))

    title = "Unusual financial pattern"
    explanation = (
        "Reported expenditure is unusually high or low relative to comparable projects in the same "
        "district, state, and work type."
    )

    possible_explanations = [
        "reporting delay",
        "procurement/payment timing",
        "scope variation",
        "local price escalation",
    ]
    recommended_verification = [
        "BOQ comparison",
        "payment records",
        "measurement records",
        "site verification",
    ]

    evidence: Dict[str, Any] = {
        "sanction_amount": _safe_float(record.get("sanction_amount"), 0.0),
        "expenditure_amount": _safe_float(record.get("expenditure_amount"), 0.0),
        "expenditure_percentage": round(expenditure_percentage, 2),
        "district": str(record.get("district", "")),
        "state": str(record.get("state", "")),
        "work_type": str(record.get("work_type", "")),
    }

    if "cost_per_unit" in record and record["cost_per_unit"] > 0:
        evidence["cost_per_unit"] = _safe_float(record.get("cost_per_unit"), 0.0)

    signal = dict(DEFAULT_SIGNAL_TEMPLATE)
    signal["signal_id"] = _generate_signal_id(index)
    signal["work_id"] = work_id
    signal["priority"] = _score_to_priority(score)
    signal["anomaly_score"] = score
    signal["title"] = title
    signal["observed_evidence"] = evidence
    signal["baseline"] = {
        "district_median_expenditure_percentage": round(district_median, 2),
        "state_median_expenditure_percentage": round(state_median, 2),
        "work_type_median_expenditure_percentage": round(work_type_median, 2),
        "comparison_basis": anomaly_basis,
    }
    signal["explanation"] = explanation
    signal["possible_explanation"] = possible_explanations
    signal["recommended_verification"] = recommended_verification
    signal["source"] = {
        "method": "IsolationForest",
        "feature_set": ["expenditure_percentage", "district_delta", "state_delta", "work_type_delta"],
    }
    signal["metadata"] = {
        "expenditure_vs_district_median": round(expenditure_percentage - district_median, 2),
        "expenditure_vs_state_median": round(expenditure_percentage - state_median, 2),
        "expenditure_vs_work_type_median": round(expenditure_percentage - work_type_median, 2),
    }
    return signal


def detect_financial_anomalies(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Detect unusual financial patterns in normalized MPLADS project records.

    Args:
        df: A DataFrame with at least work_id, sanction_amount, expenditure_amount,
            district, state, and work_type fields.

    Returns:
        A list of signal dictionaries following the shared alert schema.
    """
    if df is None or df.empty:
        return []

    frame = _build_financial_features(df)
    if frame.empty:
        return []

    anomaly_scores = _compute_anomaly_scores(frame)

    signals: List[Dict[str, Any]] = []
    signal_counter = 1
    for idx, record in frame.iterrows():
        score = anomaly_scores[idx]
        if score < 30:
            continue

        baseline = {
            "district_median": round(float(record.get("district_median", 0.0)), 2),
            "state_median": round(float(record.get("state_median", 0.0)), 2),
            "work_type_median": round(float(record.get("work_type_median", 0.0)), 2),
            "expenditure_percentage": round(float(record.get("expenditure_percentage", 0.0)), 2),
        }
        signals.append(_build_signal_from_record(record, score, signal_counter, baseline))
        signal_counter += 1

    return signals
