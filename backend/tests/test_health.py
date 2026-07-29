from app.api.health import health_check
from app.main import create_app


def test_health_check() -> None:
    data = health_check()

    assert data["status"] == "ok"
    assert data["service"] == "KnowFlow AI"
    assert data["version"] == "0.1.0"


def test_app_registers_health_route() -> None:
    app = create_app()

    paths = app.openapi()["paths"]

    assert "/api/health" in paths
