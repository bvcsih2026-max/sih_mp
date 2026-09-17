from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import io
import json
from sqlalchemy import select
from sqlalchemy.orm import Session

from .analysis.pipeline import run_analysis
from .database import Base, engine, get_db
from .models import EvidenceLink, Investigation, MP, Project, Signal
from .schemas import AnalyzeResponse, InvestigationOut, MPInput, MPOut, ProjectInput, ProjectOut, SignalOut, StatusUpdate

Base.metadata.create_all(bind=engine)
app = FastAPI(title="MPLADS Guardian API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_methods=["*"], allow_headers=["*"])


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "MPLADS Guardian", "dataset_notice": "Synthetic records are not official MPLADS data."}


@app.get("/api/dashboard/summary")
def dashboard_summary(db: Session = Depends(get_db)) -> dict[str, Any]:
    projects = list(db.scalars(select(Project)))
    signals = list(db.scalars(select(Signal)))
    investigations = list(db.scalars(select(Investigation)))
    synthetic = any(project.is_synthetic for project in projects)
    return {"total_projects": len(projects), "investigation_signals": len(signals), "critical_signals": sum(s.priority == "CRITICAL" for s in signals), "open_investigations": sum(i.status not in {"CLOSED", "EXPLAINED"} for i in investigations), "data_quality_issues": sum(s.detector_type == "data_quality" for s in signals), "dataset_type": "synthetic_demo" if synthetic else "provided_source", "official": False if synthetic else None, "label": "SYNTHETIC / DEMO DATA - NOT OFFICIAL MPLADS DATA" if synthetic else "No project data loaded"}


@app.get("/api/projects", response_model=list[ProjectOut])
def projects(db: Session = Depends(get_db)):
    return list(db.scalars(select(Project).order_by(Project.id.desc())))


@app.get("/api/projects/{work_id}", response_model=ProjectOut)
def project(work_id: str, db: Session = Depends(get_db)):
    item = db.scalar(select(Project).where(Project.work_id == work_id))
    if not item:
        raise HTTPException(404, "Project not found")
    return item


@app.get("/api/projects/{work_id}/signals", response_model=list[SignalOut])
def project_signals(work_id: str, db: Session = Depends(get_db)):
    return list(db.scalars(select(Signal).where(Signal.work_id == work_id).order_by(Signal.anomaly_score.desc())))


@app.get("/api/projects/{work_id}/evidence")
def project_evidence(work_id: str, db: Session = Depends(get_db)):
    project_item = db.scalar(select(Project).where(Project.work_id == work_id))
    if not project_item:
        raise HTTPException(404, "Project not found")
    signals = list(db.scalars(select(Signal).where(Signal.work_id == work_id)))
    signal_ids = [signal.signal_id for signal in signals]
    evidence = list(db.scalars(select(EvidenceLink).where(EvidenceLink.signal_id.in_(signal_ids)))) if signal_ids else []
    return {"work_id": work_id, "source_data": ProjectOut.model_validate(project_item).model_dump(), "signals": [SignalOut.model_validate(s).model_dump() for s in signals], "evidence_links": [{"id": item.id, "signal_id": item.signal_id, "evidence_type": item.evidence_type, "label": item.label, "value": item.value, "source": item.source, "source_record_id": item.source_record_id, "explanation": item.explanation} for item in evidence]}


@app.get("/api/alerts", response_model=list[SignalOut])
def alerts(db: Session = Depends(get_db)):
    return list(db.scalars(select(Signal).order_by(Signal.created_at.desc())))


@app.get("/api/alerts/{signal_id}", response_model=SignalOut)
def alert(signal_id: str, db: Session = Depends(get_db)):
    item = db.scalar(select(Signal).where(Signal.signal_id == signal_id))
    if not item:
        raise HTTPException(404, "Signal not found")
    return item


@app.patch("/api/alerts/{signal_id}/status", response_model=SignalOut)
def update_alert(signal_id: str, payload: StatusUpdate, db: Session = Depends(get_db)):
    item = db.scalar(select(Signal).where(Signal.signal_id == signal_id))
    if not item:
        raise HTTPException(404, "Signal not found")
    item.status = payload.status
    db.commit()
    db.refresh(item)
    return item


@app.get("/api/investigations", response_model=list[InvestigationOut])
def investigations(db: Session = Depends(get_db)):
    return list(db.scalars(select(Investigation).order_by(Investigation.updated_at.desc())))


@app.get("/api/investigations/{investigation_id}", response_model=InvestigationOut)
def investigation(investigation_id: str, db: Session = Depends(get_db)):
    item = db.scalar(select(Investigation).where(Investigation.investigation_id == investigation_id))
    if not item:
        raise HTTPException(404, "Investigation not found")
    return item


@app.patch("/api/investigations/{investigation_id}", response_model=InvestigationOut)
def update_investigation(investigation_id: str, payload: StatusUpdate, db: Session = Depends(get_db)):
    item = db.scalar(select(Investigation).where(Investigation.investigation_id == investigation_id))
    if not item:
        raise HTTPException(404, "Investigation not found")
    item.status = payload.status
    item.notes = payload.notes or item.notes
    db.commit()
    db.refresh(item)
    return item


@app.post("/api/analyze", response_model=AnalyzeResponse)
def analyze(db: Session = Depends(get_db)):
    return run_analysis(db)


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    if not file.filename or Path(file.filename).suffix.lower() not in {".json", ".csv"}:
        raise HTTPException(400, "Only JSON and CSV uploads are supported")
    content = await file.read(5_000_001)
    if len(content) > 5_000_000:
        raise HTTPException(413, "Upload exceeds the 5 MB limit")
    return {"status": "received", "filename": Path(file.filename).name, "bytes": len(content), "message": "Upload accepted for validation; no uploaded code is executed."}


@app.post("/api/admin/mps", response_model=MPOut)
def create_mp(payload: MPInput, db: Session = Depends(get_db)):
    item = MP(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@app.get("/api/admin/mps", response_model=list[MPOut])
def list_mps(db: Session = Depends(get_db)):
    return list(db.scalars(select(MP).order_by(MP.state, MP.constituency)))


@app.get("/api/admin/mps/{mp_id}", response_model=MPOut)
def get_mp(mp_id: int, db: Session = Depends(get_db)):
    item = db.get(MP, mp_id)
    if not item:
        raise HTTPException(404, "MP not found")
    return item


@app.put("/api/admin/mps/{mp_id}", response_model=MPOut)
def update_mp(mp_id: int, payload: MPInput, db: Session = Depends(get_db)):
    item = db.get(MP, mp_id)
    if not item:
        raise HTTPException(404, "MP not found")
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return item


@app.delete("/api/admin/mps/{mp_id}")
def delete_mp(mp_id: int, db: Session = Depends(get_db)):
    item = db.get(MP, mp_id)
    if not item:
        raise HTTPException(404, "MP not found")
    db.delete(item)
    db.commit()
    return {"deleted": True}


@app.post("/api/admin/import/mps")
def import_mps(payload: list[MPInput], db: Session = Depends(get_db)):
    items = [MP(**item.model_dump()) for item in payload]
    db.add_all(items)
    db.commit()
    return {"imported": len(items)}


@app.get("/api/admin/export/mps")
def export_mps(db: Session = Depends(get_db)):
    rows = [MPOut.model_validate(item).model_dump(mode="json") for item in db.scalars(select(MP))]
    return StreamingResponse(io.StringIO(json.dumps(rows)), media_type="application/json", headers={"Content-Disposition": "attachment; filename=mps.json"})


@app.get("/api/admin/states")
def states(db: Session = Depends(get_db)):
    return sorted({project.state for project in db.scalars(select(Project)) if project.state})


@app.get("/api/admin/constituencies")
def constituencies(db: Session = Depends(get_db)):
    return sorted({project.constituency for project in db.scalars(select(Project)) if project.constituency})


@app.post("/api/admin/projects", response_model=ProjectOut)
def create_project(payload: ProjectInput, db: Session = Depends(get_db)):
    if db.scalar(select(Project).where(Project.work_id == payload.work_id)):
        raise HTTPException(409, "Work ID already exists")
    item = Project(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@app.get("/api/admin/projects", response_model=list[ProjectOut])
def admin_projects(db: Session = Depends(get_db)):
    return list(db.scalars(select(Project).order_by(Project.id.desc())))


@app.put("/api/admin/projects/{project_id}", response_model=ProjectOut)
def update_project(project_id: int, payload: ProjectInput, db: Session = Depends(get_db)):
    item = db.get(Project, project_id)
    if not item:
        raise HTTPException(404, "Project not found")
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return item


@app.delete("/api/admin/projects/{project_id}")
def delete_project(project_id: int, db: Session = Depends(get_db)):
    item = db.get(Project, project_id)
    if not item:
        raise HTTPException(404, "Project not found")
    db.delete(item)
    db.commit()
    return {"deleted": True}


@app.post("/api/admin/import/projects")
def import_projects(payload: list[ProjectInput], db: Session = Depends(get_db)):
    items = [Project(**item.model_dump()) for item in payload]
    db.add_all(items)
    try:
        db.commit()
    except Exception as error:
        db.rollback()
        raise HTTPException(400, "Project import failed; check Work IDs and field values.") from error
    return {"imported": len(items)}


@app.get("/api/admin/export/projects")
def export_projects(db: Session = Depends(get_db)):
    rows = [ProjectOut.model_validate(item).model_dump(mode="json") for item in db.scalars(select(Project))]
    return StreamingResponse(io.StringIO(json.dumps(rows)), media_type="application/json", headers={"Content-Disposition": "attachment; filename=projects.json"})


@app.get("/api/data-quality")
def data_quality(db: Session = Depends(get_db)):
    return [SignalOut.model_validate(s).model_dump() for s in db.scalars(select(Signal).where(Signal.detector_type == "data_quality"))]


@app.get("/api/data-sources")
def data_sources(db: Session = Depends(get_db)):
    count = len(list(db.scalars(select(Project))))
    mp_count = len(list(db.scalars(select(MP))))
    return [
        {"source": "SIH_10_States_MPs-1.json", "type": "MP Master / Reference Data", "status": "Loaded" if mp_count else "Awaiting source data", "official": False, "record_count": mp_count},
        {"source": "Synthetic demo projects", "type": "Synthetic Demo", "status": "Loaded" if count else "Awaiting source data", "official": False, "record_count": count},
    ]


@app.get("/api/network")
def network(db: Session = Depends(get_db)):
    projects = list(db.scalars(select(Project)))
    nodes = [{"id": project.work_id, "type": "project", "label": project.work_id} for project in projects]
    edges = []
    for project in projects:
        if project.contractor:
            nodes.append({"id": f"contractor:{project.contractor}", "type": "contractor", "label": project.contractor})
            edges.append({"source": project.work_id, "target": f"contractor:{project.contractor}", "relationship": "contracted_by"})
        if project.implementing_agency:
            nodes.append({"id": f"agency:{project.implementing_agency}", "type": "agency", "label": project.implementing_agency})
            edges.append({"source": project.work_id, "target": f"agency:{project.implementing_agency}", "relationship": "implemented_by"})
    unique_nodes = {node["id"]: node for node in nodes}
    return {"nodes": list(unique_nodes.values()), "edges": edges, "label": "Relationship signals require human review; relationships alone are not suspicious."}
