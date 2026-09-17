from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class MP(Base):
    __tablename__ = "mps"
    id: Mapped[int] = mapped_column(primary_key=True)
    pc: Mapped[str] = mapped_column(String(120), default="")
    constituency: Mapped[str] = mapped_column(String(160), default="")
    mp_name: Mapped[str] = mapped_column(String(160), default="")
    party: Mapped[str] = mapped_column(String(120), default="")
    associated_area: Mapped[str] = mapped_column(String(160), default="")
    state: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    projects: Mapped[list["Project"]] = relationship(back_populates="mp")


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    work_id: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    state: Mapped[str] = mapped_column(String(120), default="")
    district: Mapped[str] = mapped_column(String(120), default="")
    constituency: Mapped[str] = mapped_column(String(160), default="")
    mp_id: Mapped[int | None] = mapped_column(ForeignKey("mps.id"), nullable=True)
    work_description: Mapped[str] = mapped_column(Text, default="")
    work_type: Mapped[str] = mapped_column(String(120), default="")
    sanctioned_amount: Mapped[float] = mapped_column(Float, default=0)
    expenditure: Mapped[float] = mapped_column(Float, default=0)
    physical_progress: Mapped[float] = mapped_column(Float, default=0)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    completion_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(60), default="In Progress")
    contractor: Mapped[str] = mapped_column(String(160), default="")
    implementing_agency: Mapped[str] = mapped_column(String(160), default="")
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    mp: Mapped[MP | None] = relationship(back_populates="projects")
    payments: Mapped[list["Payment"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    amount: Mapped[float] = mapped_column(Float, default=0)
    contractor: Mapped[str] = mapped_column(String(160), default="")
    payment_reference: Mapped[str] = mapped_column(String(160), default="")
    status: Mapped[str] = mapped_column(String(60), default="Recorded")
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)
    project: Mapped[Project] = relationship(back_populates="payments")


class Signal(Base):
    __tablename__ = "signals"
    id: Mapped[int] = mapped_column(primary_key=True)
    signal_id: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    schema_version: Mapped[str] = mapped_column(String(20), default="1.0")
    work_id: Mapped[str] = mapped_column(String(120), index=True)
    detector_type: Mapped[str] = mapped_column(String(60))
    priority: Mapped[str] = mapped_column(String(20))
    anomaly_score: Mapped[float] = mapped_column(Float, default=0)
    title: Mapped[str] = mapped_column(String(240))
    observed_evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    baseline: Mapped[dict] = mapped_column(JSON, default=dict)
    explanation: Mapped[str] = mapped_column(Text, default="")
    possible_explanation: Mapped[list] = mapped_column(JSON, default=list)
    recommended_verification: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(40), default="NEW")
    source: Mapped[dict] = mapped_column(JSON, default=dict)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Investigation(Base):
    __tablename__ = "investigations"
    id: Mapped[int] = mapped_column(primary_key=True)
    investigation_id: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    work_id: Mapped[str] = mapped_column(String(120), index=True)
    priority: Mapped[str] = mapped_column(String(20), default="MEDIUM")
    assigned_to: Mapped[str] = mapped_column(String(160), default="")
    status: Mapped[str] = mapped_column(String(40), default="NEW")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class EvidenceLink(Base):
    __tablename__ = "evidence_links"
    id: Mapped[int] = mapped_column(primary_key=True)
    signal_id: Mapped[str] = mapped_column(String(120), index=True)
    evidence_type: Mapped[str] = mapped_column(String(80))
    label: Mapped[str] = mapped_column(String(160))
    value: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(160), default="")
    source_record_id: Mapped[str] = mapped_column(String(120), default="")
    explanation: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
