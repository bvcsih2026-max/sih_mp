from datetime import date
import json
from pathlib import Path

from app.database import Base, SessionLocal, engine
from app.models import MP, Project

LABEL = "SYNTHETIC / DEMO DATA - NOT OFFICIAL MPLADS DATA"
MP_SOURCE = Path(__file__).resolve().parent / "data" / "SIH_10_States_MPs-1.json"


def seed_mps(db) -> int:
    source = json.loads(MP_SOURCE.read_text(encoding="utf-8"))
    records = [
        MP(
            state=state["state"],
            pc=str(member["pc"]),
            constituency=member["constituency"],
            mp_name=member["mp"],
            party=member["party"],
            associated_area=member["associated_area"],
        )
        for state in source["states"]
        for member in state["members"]
    ]
    existing = {item.mp_name: item for item in db.query(MP).all()}
    for record in records:
        current = existing.get(record.mp_name)
        if current is None:
            db.add(record)
        else:
            current.state = record.state
            current.pc = record.pc
            current.constituency = record.constituency
            current.party = record.party
            current.associated_area = record.associated_area
    db.commit()
    return len(records)


def seed() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    mp_count = seed_mps(db)
    if db.query(Project).count():
        db.close()
        print(f"Loaded {mp_count} MP Master / Reference Data records")
        return
    records = [
        dict(work_id="WORK-DEMO-001", state="Synthetic State A", district="Demo District North", constituency="Demo Constituency 1", work_description="Construction of community hall at Demo Village", work_type="Community Infrastructure", sanctioned_amount=1000000, expenditure=420000, physical_progress=40, start_date=date(2025, 1, 15), status="In Progress", contractor="Demo Contractor Alpha", implementing_agency="Demo Agency North", latitude=28.61, longitude=77.20),
        dict(work_id="WORK-DEMO-002", state="Synthetic State A", district="Demo District North", constituency="Demo Constituency 1", work_description="Construction of community hall near Demo Village", work_type="Community Infrastructure", sanctioned_amount=1050000, expenditure=900000, physical_progress=34, start_date=date(2024, 1, 1), status="In Progress", contractor="Demo Contractor Alpha", implementing_agency="Demo Agency North", latitude=28.615, longitude=77.205),
        dict(work_id="WORK-DEMO-003", state="Synthetic State B", district="Demo District South", constituency="Demo Constituency 2", work_description="Installation of solar street lights in Demo Ward", work_type="Solar Lighting", sanctioned_amount=500000, expenditure=250000, physical_progress=48, start_date=date(2025, 3, 10), status="In Progress", contractor="Demo Contractor Beta", implementing_agency="Demo Agency South", latitude=19.07, longitude=72.87),
        dict(work_id="WORK-DEMO-004", state="Synthetic State B", district="Demo District South", constituency="Demo Constituency 2", work_description="Completed demo water tank", work_type="Water Supply", sanctioned_amount=800000, expenditure=0, physical_progress=100, start_date=date(2023, 6, 1), completion_date=date(2024, 3, 1), status="Completed", contractor="Demo Contractor Gamma", implementing_agency="Demo Agency South", latitude=19.075, longitude=72.875),
        dict(work_id="WORK-DEMO-005", state="Synthetic State C", district="Demo District West", constituency="Demo Constituency 3", work_description="Demo record with invalid progress for validation testing", work_type="Road", sanctioned_amount=600000, expenditure=650000, physical_progress=140, start_date=date(2025, 5, 1), status="In Progress", contractor="Demo Contractor Delta", implementing_agency="Demo Agency West"),
    ]
    db.add_all([Project(**record, is_synthetic=True) for record in records])
    db.commit()
    db.close()
    print(f"Loaded {mp_count} MP Master / Reference Data records")
    print(LABEL)


if __name__ == "__main__":
    seed()
