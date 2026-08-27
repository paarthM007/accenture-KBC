"""T0.9 — GET /health."""

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_health_returns_200():
    response = client.get("/health")
    assert response.status_code == 200


def test_health_reports_both_components():
    body = client.get("/health").json()
    assert set(body["components"].keys()) == {"c1", "c3"}
    for component in body["components"].values():
        assert component["mode"] in ("mock", "real")
        assert isinstance(component["importable"], bool)


def test_health_reports_13_metrics_loaded():
    body = client.get("/health").json()
    assert body["config"]["metrics_loaded"] == 13
    assert set(body["config"]["sectors"]) == {"TECH_SAAS", "RETAIL"}
