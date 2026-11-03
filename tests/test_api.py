import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app

# Setup in-memory SQLite for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


def test_system_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_create_and_get_service():
    payload = {
        "name": "Cloudflare Test",
        "url": "https://1.1.1.1",
        "method": "GET",
        "interval_seconds": 30,
        "timeout_seconds": 5,
        "expected_status": 200,
        "is_active": True,
    }
    # Create service
    create_res = client.post("/api/services", json=payload)
    assert create_res.status_code == 201
    data = create_res.json()
    assert data["name"] == "Cloudflare Test"
    assert "id" in data
    service_id = data["id"]

    # Get single service
    get_res = client.get(f"/api/services/{service_id}")
    assert get_res.status_code == 200
    assert get_res.json()["name"] == "Cloudflare Test"

    # List services
    list_res = client.get("/api/services")
    assert list_res.status_code == 200
    assert len(list_res.json()) >= 1


def test_system_stats():
    res = client.get("/api/stats")
    assert res.status_code == 200
    stats = res.json()
    assert "total_services" in stats
    assert "overall_uptime_pct" in stats
    assert "avg_response_time_ms" in stats


def test_trigger_check():
    # Create a service
    create_res = client.post(
        "/api/services",
        json={"name": "HTTPBin Check", "url": "https://httpbin.org/status/200"},
    )
    assert create_res.status_code == 201
    service_id = create_res.json()["id"]

    # Trigger manual check
    check_res = client.post(f"/api/services/{service_id}/check")
    assert check_res.status_code == 200
    check_data = check_res.json()
    assert check_data["service_id"] == service_id
    assert "is_up" in check_data

    # Check history
    hist_res = client.get(f"/api/services/{service_id}/history")
    assert hist_res.status_code == 200
    assert len(hist_res.json()) >= 1


def test_delete_service():
    create_res = client.post(
        "/api/services",
        json={"name": "To Delete", "url": "https://example.com"},
    )
    service_id = create_res.json()["id"]

    del_res = client.delete(f"/api/services/{service_id}")
    assert del_res.status_code == 204

    # Confirm 404
    get_res = client.get(f"/api/services/{service_id}")
    assert get_res.status_code == 404
