"""Smoke tests for public API endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_health_ok() -> None:
    with TestClient(create_app()) as client:
        res = client.get("/api/v1/health")
        assert res.status_code == 200
        assert res.json()["message"] == "ok"


def test_ready_ok() -> None:
    with TestClient(create_app()) as client:
        res = client.get("/api/v1/ready")
        assert res.status_code == 200
        assert res.json()["message"] == "ready"
