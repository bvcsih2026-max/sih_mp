from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

import numpy as np
import pandas as pd


DEFAULT_SIGNAL_TEMPLATE = {
    "signal_id": "",
    "schema_version": "1.0",
    "work_id": "",
    "detector_type": "progress_mismatch",
    "priority": "LOW",
    "anomaly_score": 0,
    "title": "Progress expenditure mismatch",
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


def _parse_year(val: Any) -> int | None:
    if pd.isna(val) or not val:
        return None
    val_str = str(val).strip()
    # Try ISO or standard YYYY-MM-DD format
    try:
        dt = datetime.fromisoformat(val_str[:10])
        return dt.year
    except ValueError:
        pass
    # Try parsing purely as 4 digit year
    if len(val_str) >= 4 and val_str[:4].isdigit():
        try:
            return int(val_str[:4])
        except ValueError:
            pass
    # Try slash format DD/MM/YYYY or YYYY/MM/DD
    parts = val_str.split("/")
    for part in parts:
        if len(part) == 4 and part.isdigit():
            return int(part)
    return None


def _project_is_very_old(record: pd.Series, current_year: int = 2026) -> bool:
    start_date = record.get("start_date") or record.get("sanction_date")
    year = _parse_year(start_date)
    if year is None:
        return False
    return (current_year - year) >= 3 or year <= 2021


def _is_completed_status(record: pd.Series) -> bool:
    status = str(record.get("project_status", "")).strip().lower()
    return status in {"completed", "closed", "finished", "complete"}


def detect_progress_anomalies(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Detect inconsistencies between reported expenditure and physical progress."""
    if df is None or df.empty:
        return []

    records = df.copy()
    for column in ["expenditure_amount", "sanction_amount", "physical_progress_percentage"]:
        if column in records.columns:
            records[column] = records[column].apply(lambda val: _safe_float(val, 0.0))
        else:
            records[column] = 0.0

    if "expenditure_percentage" in records.columns:
        records["expenditure_percentage"] = records["expenditure_percentage"].apply(
            lambda val: _safe_float(val, 0.0)
        )
    else:
        records["expenditure_percentage"] = np.where(
            records["sanction_amount"] > 0,
            (records["expenditure_amount"] / records["sanction_amount"]) * 100.0,
            0.0,
        )

    signals: List[Dict[str, Any]] = []
    signal_counter = 1

    for idx, row in records.iterrows():
        work_id = str(row.get("work_id", f"WORK-{idx:03d}"))
        expenditure = _safe_float(row.get("expenditure_percentage"), 0.0)
        progress = _safe_float(row.get("physical_progress_percentage"), 0.0)
        gap = expenditure - progress
        status_str = str(row.get("project_status", "")).strip()
        status_lower = status_str.lower()

        reasons: List[str] = []
        base_score = 0

        # Condition 1: Expenditure substantially ahead of physical progress (e.g. 90% exp vs 30% progress)
        if expenditure >= 80.0 and progress <= 40.0:
            reasons.append("Reported expenditure is substantially ahead of reported physical progress.")
            gap_severity = (expenditure - progress) * 0.8
            base_score = max(base_score, int(round(50 + gap_severity)))

        # Condition 2: Completed project with 0% expenditure
        if _is_completed_status(row) and expenditure == 0.0:
            reasons.append("Completed project has 0% expenditure reported.")
            base_score = max(base_score, 85)

        # Condition 3: Very high progress (>=90%) with negligible expenditure (<=5%)
        if progress >= 90.0 and expenditure <= 5.0 and not _is_completed_status(row):
            reasons.append("Project is reported as nearly complete while showing negligible expenditure.")
            base_score = max(base_score, 75)

        # Condition 4: 100% expenditure with 0% physical progress
        if expenditure >= 95.0 and progress == 0.0:
            reasons.append("High expenditure reported with zero physical progress recorded.")
            base_score = max(base_score, 90)

        # Condition 5: Very old project still marked In Progress
        is_old = _project_is_very_old(row)
        if status_lower in {"in progress", "ongoing", "started", "wip"} and is_old:
            reasons.append("Very old project is still marked In Progress.")
            base_score = max(base_score, 70)

        # Condition 6: Significant overall expenditure-progress gap
        if not reasons and abs(gap) >= 50.0:
            reasons.append("Significant mismatch between expenditure and physical progress indicates an anomalous pattern.")
            base_score = max(base_score, int(round(30 + abs(gap) * 0.6)))

        if not reasons:
            continue

        score = int(round(max(30, min(100, base_score))))

        recommended_verification = [
            "BOQ comparison",
            "payment records",
            "measurement records",
            "site verification",
        ]
        possible_explanations = [
            "reporting delay",
            "procurement/payment timing",
            "scope variation",
            "contractor billing frequency",
            "weather or access constraints",
        ]

        title = "Progress expenditure mismatch"
        explanation = " ".join(reasons)

        signal = dict(DEFAULT_SIGNAL_TEMPLATE)
        signal["signal_id"] = _generate_signal_id(signal_counter)
        signal["work_id"] = work_id
        signal["priority"] = _score_to_priority(score)
        signal["anomaly_score"] = score
        signal["title"] = title
        signal["observed_evidence"] = {
            "expenditure_percentage": round(expenditure, 2),
            "physical_progress_percentage": round(progress, 2),
            "gap": round(gap, 2),
            "project_status": status_str,
        }
        signal["baseline"] = {
            "expected_alignment_range": {"min": 0, "max": 20},
            "comparison": "Expenditure percentage compared against physical progress percentage",
        }
        signal["explanation"] = explanation
        signal["possible_explanation"] = possible_explanations
        signal["recommended_verification"] = recommended_verification
        signal["source"] = {
            "method": "progress_gap_check",
            "fields": ["expenditure_percentage", "physical_progress_percentage", "project_status"],
        }
        signal["metadata"] = {
            "status": status_str,
            "gap_threshold": 20,
            "is_very_old_project": is_old,
        }

        signals.append(signal)
        signal_counter += 1

    return signals
