"""Comprehensive test suite for TRANSIQ API endpoints and routing engine."""

import pytest
from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert "TRANSIQ" in data["system"]


def test_get_anchor_locations():
    response = client.get("/api/routes/anchors")
    assert response.status_code == 200
    data = response.json()
    assert "origins" in data
    assert "destinations" in data
    assert len(data["origins"]) > 0
    assert len(data["destinations"]) > 0
    # Verify origin structure
    o0 = data["origins"][0]
    assert "postal_code" in o0
    assert "latitude" in o0
    assert "longitude" in o0


def test_route_search_rain_shield():
    payload = {
        "origin_postal": "640183",
        "dest_postal": "648886",
        "mode": "RAIN_SHIELD",
        "strict_mode": False
    }
    response = client.post("/api/routes/search", json=payload)
    assert response.status_code == 200
    routes = response.json()
    assert len(routes) > 0
    r0 = routes[0]
    assert r0["score"] > 0
    assert r0["base_travel_time"] > 0
    assert len(r0["steps"]) > 0
    assert len(r0["coordinates"]) > 0
    # Rain shield should maximize sheltered walking
    assert r0["sheltered_m"] > 0


def test_route_search_comfort_seats():
    payload = {
        "origin_postal": "640183",
        "dest_postal": "648886",
        "mode": "COMFORT_SEATS",
        "strict_mode": False
    }
    response = client.post("/api/routes/search", json=payload)
    assert response.status_code == 200
    routes = response.json()
    assert len(routes) > 0


def test_route_search_least_transfers():
    payload = {
        "origin_postal": "640183",
        "dest_postal": "648886",
        "mode": "LEAST_TRANSFERS",
        "strict_mode": False
    }
    response = client.post("/api/routes/search", json=payload)
    assert response.status_code == 200
    routes = response.json()
    assert len(routes) > 0


def test_route_search_strict_filter():
    payload = {
        "origin_postal": "640183",
        "dest_postal": "648886",
        "mode": "RAIN_SHIELD",
        "strict_mode": True
    }
    response = client.post("/api/routes/search", json=payload)
    assert response.status_code == 200
    routes = response.json()
    for r in routes:
        assert r["unsheltered_m"] == 0.0


def test_profiles_crud():
    # 1. List profiles
    list_res = client.get("/api/profiles/")
    assert list_res.status_code == 200
    initial_count = len(list_res.json())

    # 2. Create profile
    new_profile = {
        "email": f"tester_{initial_count + 1}@transiq.sg",
        "preferred_mode": "RAIN_SHIELD",
        "max_uncovered_walk_m": 40,
        "require_barrier_free": True
    }
    create_res = client.post("/api/profiles/", json=new_profile)
    assert create_res.status_code == 200
    user_id = create_res.json()["user_id"]
    route_payload = {
        "user_id": user_id,
        "route_name": "Test Commute to Ang Mo Kio",
        "origin_postal": "640183",
        "dest_postal": "560101",
        "preferred_mode": "RAIN_SHIELD",
        "stops": ["01012", "01013"]
    }
    save_res = client.post("/api/profiles/save_route", json=route_payload)
    assert save_res.status_code == 200
    assert save_res.json()["status"] == "success"

    # 4. Fetch saved routes
    get_routes_res = client.get(f"/api/profiles/{user_id}/saved_routes")
    assert get_routes_res.status_code == 200
    saved = get_routes_res.json()
    assert len(saved) >= 1
    assert saved[0]["route_name"] == "Test Commute to Ang Mo Kio"


def test_analytics_views():
    # View 1: Sheltered Access
    res1 = client.get("/api/analytics/sheltered_access?postal_code=640183")
    assert res1.status_code == 200

    # View 2: Peak Congestion
    res2 = client.get("/api/analytics/peak_congestion?limit=10")
    assert res2.status_code == 200
    cong_data = res2.json()
    assert len(cong_data) > 0
    assert "rolling_3hr_avg" in cong_data[0]

    # View 3: Comfort Routes
    res3 = client.get("/api/analytics/comfort_routes")
    assert res3.status_code == 200

    # Live Crowd Distribution
    res4 = client.get("/api/analytics/live_crowd")
    assert res4.status_code == 200
    assert "distribution" in res4.json()


def test_benchmarks_matrix():
    res = client.get("/api/benchmarks/")
    assert res.status_code == 200
    matrix = res.json()
    assert len(matrix) >= 5
    for pair in matrix:
        assert "pair" in pair
        assert "speedup" in pair
