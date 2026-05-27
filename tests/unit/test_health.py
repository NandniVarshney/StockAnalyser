"""Smoke test — FastAPI /health works without external deps."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    # Import here so the env-isolation fixture has already set paths.
    from stockanalyser.api.main import app

    return TestClient(app)


def test_health_ok(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["service"] == "stockanalyser"
    assert "version" in body


def test_rovodev_health_does_not_crash(client: TestClient) -> None:
    # Rovo CLI almost certainly isn't running in CI — endpoint must still
    # respond with ok=false, not 500.
    resp = client.get("/rovodev/health")
    assert resp.status_code == 200
    assert resp.json()["ok"] in (True, False)
