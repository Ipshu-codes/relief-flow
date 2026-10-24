import asyncio
from unittest.mock import Mock

import httpx
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app import main
from app.db import get_db


def test_health_reports_database_and_ollama(monkeypatch):
    db = Mock()
    app_client = TestClient(main.app)
    main.app.dependency_overrides[get_db] = lambda: db

    async def ollama_available():
        return {
            "reachable": True,
            "model": "qwen2.5:3b",
            "model_available": True,
            "fallback_active": False,
        }

    monkeypatch.setattr(main, "check_ollama", ollama_available)
    try:
        response = app_client.get("/api/health")
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "connected",
        "ollama": {
            "reachable": True,
            "model": "qwen2.5:3b",
            "model_available": True,
            "fallback_active": False,
        },
    }
    db.execute.assert_called_once()


def test_health_reports_database_failure(monkeypatch):
    db = Mock()
    db.execute.side_effect = SQLAlchemyError("database unavailable")
    main.app.dependency_overrides[get_db] = lambda: db

    async def ollama_unavailable():
        return {
            "reachable": False,
            "model": "qwen2.5:3b",
            "model_available": False,
            "fallback_active": True,
        }

    monkeypatch.setattr(main, "check_ollama", ollama_unavailable)
    try:
        response = TestClient(main.app).get("/api/health")
    finally:
        main.app.dependency_overrides.clear()

    assert response.json()["status"] == "error"
    assert response.json()["database"] == "unavailable"
    db.rollback.assert_called_once()


def test_check_ollama_marks_unavailable_service_as_fallback(monkeypatch):
    transport = httpx.MockTransport(
        lambda request: httpx.Response(503, request=request)
    )
    async_client = httpx.AsyncClient
    monkeypatch.setattr(
        main.httpx,
        "AsyncClient",
        lambda timeout: async_client(transport=transport, timeout=timeout),
    )

    result = asyncio.run(main.check_ollama())

    assert result["reachable"] is False
    assert result["fallback_active"] is True
