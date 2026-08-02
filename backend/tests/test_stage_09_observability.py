import asyncio

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import create_app
from app.services.readiness_service import ReadinessService


class FakeHealthyVectorStore:
    def __init__(self) -> None:
        self.heartbeat_called = False

    def heartbeat(self) -> None:
        self.heartbeat_called = True


def test_request_id_is_generated_and_can_be_propagated() -> None:
    async def send_requests():
        transport = httpx.ASGITransport(app=create_app())
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            generated_response = await client.get("/api/health")
            propagated_response = await client.get(
                "/api/health",
                headers={"X-Request-ID": "frontend-request-123"},
            )
        return generated_response, propagated_response

    generated_response, propagated_response = asyncio.run(send_requests())

    assert generated_response.status_code == 200
    assert len(generated_response.headers["X-Request-ID"]) == 32
    assert propagated_response.headers["X-Request-ID"] == "frontend-request-123"


def test_readiness_checks_database_and_vector_store() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    testing_session = sessionmaker(bind=engine)
    vector_store = FakeHealthyVectorStore()
    db = testing_session()
    try:
        result = ReadinessService(db, vector_store=vector_store).check()

        assert result == {
            "status": "ready",
            "checks": {"database": "ok", "vector_store": "ok"},
        }
        assert vector_store.heartbeat_called is True
    finally:
        db.close()
