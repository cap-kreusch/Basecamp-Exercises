"""
Tests for order creation (POST /api/orders) used by the Restocking feature.
"""
from datetime import datetime


class TestCreateOrder:
    """Test suite for the POST /api/orders endpoint."""

    def test_create_order_returns_submitted_order(self, client):
        payload = {
            "items": [
                {"sku": "PCB-001", "name": "Single Layer PCB Assembly", "quantity": 50, "unit_price": 24.99}
            ],
            "lead_time_days": 14,
        }
        response = client.post("/api/orders", json=payload)
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "Submitted"
        assert data["customer"] == "Internal Restock"
        assert data["total_value"] == 50 * 24.99
        assert data["order_number"].startswith("ORD-")
        assert len(data["items"]) == 1
        assert data["items"][0]["sku"] == "PCB-001"

    def test_create_order_lead_time_reflected_in_expected_delivery(self, client):
        payload = {
            "items": [
                {"sku": "PCB-001", "name": "Single Layer PCB Assembly", "quantity": 10, "unit_price": 24.99}
            ],
            "lead_time_days": 7,
        }
        response = client.post("/api/orders", json=payload)
        assert response.status_code == 200
        data = response.json()

        ordered = datetime.fromisoformat(data["order_date"])
        expected = datetime.fromisoformat(data["expected_delivery"])
        delta_days = (expected - ordered).days
        # Allow off-by-one tolerance for clock-edge cases when computing days
        assert delta_days in (6, 7)

    def test_create_order_appears_in_orders_list(self, client):
        payload = {
            "items": [
                {"sku": "PCB-001", "name": "Single Layer PCB Assembly", "quantity": 5, "unit_price": 24.99}
            ],
            "lead_time_days": 30,
        }
        create_response = client.post("/api/orders", json=payload)
        assert create_response.status_code == 200
        created_id = create_response.json()["id"]

        list_response = client.get("/api/orders?status=Submitted")
        assert list_response.status_code == 200
        ids = [o["id"] for o in list_response.json()]
        assert created_id in ids

    def test_create_order_with_multiple_items_sums_total_value(self, client):
        payload = {
            "items": [
                {"sku": "PCB-001", "name": "Single Layer PCB Assembly", "quantity": 4, "unit_price": 25.0},
                {"sku": "WDG-001", "name": "Industrial Widget Type A", "quantity": 10, "unit_price": 12.5},
            ],
            "lead_time_days": 14,
        }
        response = client.post("/api/orders", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["total_value"] == 4 * 25.0 + 10 * 12.5
