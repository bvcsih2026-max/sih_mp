from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class MPInput(BaseModel):
    pc: str = ""
    constituency: str = ""
    mp_name: str = ""
    party: str = ""
    associated_area: str = ""
    state: str = ""


class MPOut(MPInput, ORMModel):
    id: int
    created_at: datetime
    updated_at: datetime


class ProjectInput(BaseModel):
    work_id: str
    state: str = ""
    district: str = ""
    constituency: str = ""
    mp_id: int | None = None
    work_description: str = ""
    work_type: str = ""
    sanctioned_amount: float = 0
    expenditure: float = 0
    physical_progress: float = 0
    start_date: date | None = None
    completion_date: date | None = None
    status: str = "In Progress"
    contractor: str = ""
    implementing_agency: str = ""
    latitude: float | None = None
    longitude: float | None = None
    is_synthetic: bool = True


class ProjectOut(ProjectInput, ORMModel):
    id: int
    created_at: datetime
    updated_at: datetime


class StatusUpdate(BaseModel):
    status: str
    notes: str = ""


class SignalOut(ORMModel):
    id: int
    signal_id: str
    schema_version: str
    work_id: str
    detector_type: str
    priority: str
    anomaly_score: float
    title: str
    observed_evidence: dict[str, Any]
    baseline: dict[str, Any]
    explanation: str
    possible_explanation: list[str]
    recommended_verification: list[str]
    status: str
    source: dict[str, Any]
    metadata_json: dict[str, Any]
    created_at: datetime


class InvestigationOut(ORMModel):
    id: int
    investigation_id: str
    work_id: str
    priority: str
    assigned_to: str
    status: str
    notes: str
    created_at: datetime
    updated_at: datetime


class AnalyzeResponse(BaseModel):
    projects_processed: int
    signals_created: int
    investigations_created: int
    data_quality_issues: int
