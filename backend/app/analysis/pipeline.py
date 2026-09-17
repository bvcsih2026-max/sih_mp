from __future__ import annotations

from typing import Any

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ml.detectors.financial_anomaly import detect_financial_anomalies
from ml.detectors.progress_anomaly import detect_progress_anomalies
from ml.detectors.similar_work import SimilarWorkDetector

from ..models import EvidenceLink, Investigation, Project, Signal


def project_record(project: Project) -> dict[str, Any]:
    return {
        "work_id": project.work_id,
        "sanction_amount": project.sanctioned_amount,
        "expenditure_amount": project.expenditure,
        "district": project.district,
        "state": project.state,
        "work_type": project.work_type,
        "physical_progress_percentage": project.physical_progress,
        "project_status": project.status,
        "start_date": project.start_date.isoformat() if project.start_date else None,
        "sanction_date": project.start_date.isoformat() if project.start_date else None,
        "description": project.work_description,
        "location": [project.latitude, project.longitude] if project.latitude is not None and project.longitude is not None else None,
    }


def quality_signals(projects: list[Project]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for project in projects:
        issues: list[tuple[str, dict[str, Any], str]] = []
        if not project.work_id:
            issues.append(("Missing Work ID", {}, "A project cannot be traced without a Work ID."))
        if project.work_id in seen:
            issues.append(("Duplicate Work ID", {"work_id": project.work_id}, "More than one record uses this Work ID."))
        seen.add(project.work_id)
        for value, label in ((project.state, "state"), (project.district, "district"), (project.constituency, "constituency"), (project.work_description, "description")):
            if not value:
                issues.append((f"Missing {label}", {"field": label}, f"The {label} field is empty."))
        if project.sanctioned_amount < 0:
            issues.append(("Negative sanctioned amount", {"sanctioned_amount": project.sanctioned_amount}, "The recorded amount is negative."))
        if project.expenditure < 0:
            issues.append(("Negative expenditure", {"expenditure": project.expenditure}, "The recorded expenditure is negative."))
        if project.expenditure > project.sanctioned_amount >= 0:
            issues.append(("Expenditure exceeds sanctioned amount", {"sanctioned_amount": project.sanctioned_amount, "expenditure": project.expenditure}, "Recorded expenditure exceeds the recorded sanction."))
        if not 0 <= project.physical_progress <= 100:
            issues.append(("Physical progress outside 0-100", {"physical_progress": project.physical_progress}, "Physical progress must be between 0 and 100."))
        if project.start_date and project.completion_date and project.completion_date < project.start_date:
            issues.append(("Invalid project dates", {}, "Completion date occurs before start date."))
        if project.latitude is not None and not -90 <= project.latitude <= 90:
            issues.append(("Invalid latitude", {"latitude": project.latitude}, "Latitude must be between -90 and 90."))
        if project.longitude is not None and not -180 <= project.longitude <= 180:
            issues.append(("Invalid longitude", {"longitude": project.longitude}, "Longitude must be between -180 and 180."))
        for title, evidence, explanation in issues:
            output.append({
                "work_id": project.work_id or f"ROW-{project.id}",
                "detector_type": "data_quality",
                "priority": "HIGH",
                "anomaly_score": 70,
                "title": title,
                "observed_evidence": evidence,
                "baseline": {"validation": "project record rules"},
                "explanation": explanation,
                "possible_explanation": ["Data entry error", "Pending correction or revised source record"],
                "recommended_verification": ["Review the source record", "Correct the project data", "Re-run analysis"],
                "status": "NEW",
                "source": {"method": "project_record_validation", "record_id": project.work_id},
                "metadata": {"dataset_type": "synthetic_demo" if project.is_synthetic else "provided_source"},
            })
    return output


def normalize(raw: list[dict[str, Any]], detector: str, offset: int) -> list[dict[str, Any]]:
    normalized = []
    for index, signal in enumerate(raw, offset + 1):
        item = dict(signal)
        item["signal_id"] = f"SIG-{index:05d}"
        item["schema_version"] = "1.0"
        item["detector_type"] = detector
        item["metadata"] = item.get("metadata", {})
        normalized.append(item)
    return normalized


def run_analysis(db: Session) -> dict[str, int]:
    projects = list(db.scalars(select(Project).order_by(Project.id)))
    prior_signal_status = {signal.signal_id: signal.status for signal in db.scalars(select(Signal))}
    prior_investigation_status = {item.work_id: (item.status, item.notes) for item in db.scalars(select(Investigation))}
    db.execute(delete(EvidenceLink))
    db.execute(delete(Signal))
    db.execute(delete(Investigation))
    records = [project_record(project) for project in projects]
    frame = pd.DataFrame(records)
    signals = normalize(quality_signals(projects), "data_quality", 0)
    signals.extend(normalize(detect_financial_anomalies(frame), "financial_anomaly", len(signals)))
    signals.extend(normalize(detect_progress_anomalies(frame), "progress_mismatch", len(signals)))
    if len(records) <= 500:
        signals.extend(normalize(SimilarWorkDetector().detect(records), "similar_work", len(signals)))

    for data in signals:
        signal = Signal(
            signal_id=data["signal_id"], schema_version="1.0", work_id=data["work_id"], detector_type=data["detector_type"],
            priority=data["priority"], anomaly_score=float(data["anomaly_score"]), title=data["title"],
            observed_evidence=data.get("observed_evidence", {}), baseline=data.get("baseline", {}), explanation=data.get("explanation", ""),
            possible_explanation=data.get("possible_explanation", []), recommended_verification=data.get("recommended_verification", []),
            status=prior_signal_status.get(data["signal_id"], "NEW"), source=data.get("source", {}), metadata_json=data.get("metadata", {}),
        )
        db.add(signal)
        for label, value in (signal.observed_evidence or {}).items():
            db.add(EvidenceLink(signal_id=signal.signal_id, evidence_type="observed", label=label, value=str(value), source="project", source_record_id=signal.work_id, explanation="Observed source or derived detector value."))

    db.flush()
    by_work: dict[str, list[Signal]] = {}
    for signal in db.scalars(select(Signal)):
        by_work.setdefault(signal.work_id, []).append(signal)
    priority_order = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    for work_id, work_signals in by_work.items():
        priority = max((signal.priority for signal in work_signals), key=priority_order.index)
        old_status, old_notes = prior_investigation_status.get(work_id, ("NEW", ""))
        db.add(Investigation(investigation_id=f"INV-{work_id}", work_id=work_id, priority=priority, status=old_status, notes=old_notes or f"{len(work_signals)} investigation signal(s) require review."))
    db.commit()
    return {"projects_processed": len(projects), "signals_created": len(signals), "investigations_created": len(by_work), "data_quality_issues": sum(signal["detector_type"] == "data_quality" for signal in signals)}
