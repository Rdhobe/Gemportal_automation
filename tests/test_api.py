from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_health_and_meta():
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    meta = client.get("/api/meta")
    assert meta.status_code == 200
    payload = meta.json()
    assert "Software" in payload["it_categories"]
    assert "Maharashtra" in payload["states"]
    assert payload["bid_types"] == ["Product", "Service"]


def test_settings_round_trip():
    current = client.get("/api/settings")
    assert current.status_code == 200
    payload = current.json()
    payload["max_emd"] = 45_000
    updated = client.put("/api/settings", json=payload)
    assert updated.status_code == 200
    assert updated.json()["max_emd"] == 45_000

    # Restore the original value so local development data is unchanged.
    payload["max_emd"] = current.json()["max_emd"]
    client.put("/api/settings", json=payload)
