from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_analysis_and_signal_retrieval():
    response = client.post("/api/analyze")
    assert response.status_code == 200
    assert "signals_created" in response.json()
    alerts = client.get("/api/alerts")
    assert alerts.status_code == 200
    assert isinstance(alerts.json(), list)


def test_status_update_and_evidence_endpoint():
    alerts = client.get("/api/alerts").json()
    if not alerts:
        return
    signal_id = alerts[0]["signal_id"]
    updated = client.patch(f"/api/alerts/{signal_id}/status", json={"status": "EVIDENCE_REQUESTED"})
    assert updated.status_code == 200
    evidence = client.get(f"/api/projects/{alerts[0]['work_id']}/evidence")
    assert evidence.status_code == 200
    assert "signals" in evidence.json()
