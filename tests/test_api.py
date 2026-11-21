"""Integration tests for the FastAPI serving layer."""

from __future__ import annotations

from fastapi.testclient import TestClient

from payments_platform.api import main as api_main
from payments_platform.config import Settings


def test_fastapi_endpoints(e2e_settings: Settings, monkeypatch: object) -> None:
    monkeypatch.setattr(api_main, "get_settings", lambda: e2e_settings)
    client = TestClient(api_main.app)

    health_resp = client.get("/health")
    assert health_resp.status_code == 200
    assert health_resp.json()["status"] == "healthy"

    catalog_resp = client.get("/metrics/catalog")
    assert catalog_resp.status_code == 200
    assert "gross_tpv_brl" in catalog_resp.json()["metrics"]

    ask_resp = client.post(
        "/copilot/ask",
        json={"question": "Qual o net take rate e gross TPV por regiao?"},
    )
    assert ask_resp.status_code == 200
    body = ask_resp.json()
    assert body["status"] == "ok"
    assert len(body["rows"]) > 0
    assert "select" in body["compiled_sql"].lower()
