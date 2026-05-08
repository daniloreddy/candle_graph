from fastapi.testclient import TestClient
from unittest.mock import patch
from main import app
from datetime import datetime, timedelta

client = TestClient(app)


# Helper to generate valid mock payload
def get_valid_payload(points=100):
    data = []
    for i in range(points):
        data.append(
            {
                "date": (datetime.now() - timedelta(days=points - i)).isoformat(),
                "open": 100.0 + i,
                "high": 110.0 + i,
                "low": 90.0 + i,
                "close": 105.0 + i,
                "volume": 1000.0,
            }
        )
    return {"symbol": "BTC/USDT", "data": data, "bb_k": 2.0, "max_ohlcv_points": 180}


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_api_unauthorized_no_token():
    # If API_TOKENS is configured, this should fail
    with patch("main.VALID_TOKENS", {"secret-token"}):
        response = client.post("/api/v1/chart", json=get_valid_payload())
        assert response.status_code in [401, 403]


def test_api_validation_error_symbol_length():
    with patch("main.VALID_TOKENS", {"secret-token"}):
        payload = get_valid_payload()
        payload["symbol"] = "A" * 51  # Limit is 50
        response = client.post(
            "/api/v1/chart",
            json=payload,
            headers={"Authorization": "Bearer secret-token"},
        )
        assert response.status_code == 422  # Pydantic error


def test_api_validation_error_max_points():
    with patch("main.VALID_TOKENS", {"secret-token"}):
        payload = get_valid_payload()
        payload["max_ohlcv_points"] = 5  # Min is 10
        response = client.post(
            "/api/v1/chart",
            json=payload,
            headers={"Authorization": "Bearer secret-token"},
        )
        assert response.status_code == 422


def test_api_dos_protection():
    with patch("main.VALID_TOKENS", {"secret-token"}):
        payload = get_valid_payload()
        payload["data"] = payload["data"] * 60  # More than 5000 elements
        response = client.post(
            "/api/v1/chart",
            json=payload,
            headers={"Authorization": "Bearer secret-token"},
        )
        assert response.status_code == 422


def test_api_insufficient_data():
    with patch("main.VALID_TOKENS", {"secret-token"}):
        payload = get_valid_payload(10)  # Less than 26 needed for indicators
        response = client.post(
            "/api/v1/chart",
            json=payload,
            headers={"Authorization": "Bearer secret-token"},
        )
        assert response.status_code == 400
        assert "Insufficient data" in response.json()["detail"]
