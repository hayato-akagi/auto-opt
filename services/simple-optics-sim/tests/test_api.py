from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


def test_health(client):
    """Test health endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "simple-optics-sim"


def test_simulate_basic(client):
    """Test basic simulation."""
    payload = {
        "wavelength": 780.0,
        "ld_tilt": 0.0,
        "ld_div_fast": 25.0,
        "ld_div_slow": 8.0,
        "ld_div_fast_err": 0.0,
        "ld_div_slow_err": 0.0,
        "ld_emit_w": 3.0,
        "ld_emit_h": 1.0,
        "num_rays": 500,
        "coll_r1": -3.5,
        "coll_r2": -15.0,
        "coll_k1": -1.0,
        "coll_k2": 0.0,
        "coll_t": 2.0,
        "coll_n": 1.517,
        "dist_ld_coll": 4.0,
        "coll_x_shift": 0.0,
        "coll_y_shift": 0.0,
        "obj_f": 4.0,
        "dist_coll_obj": 50.0,
        "sensor_pos": 4.0,
        "return_ray_hits": False,
        "return_ray_path_image": False,
        "return_spot_diagram_image": False,
    }
    
    response = client.post("/simulate", json=payload)
    assert response.status_code == 200
    
    data = response.json()
    assert "spot_center_x" in data
    assert "spot_center_y" in data
    assert "spot_rms_radius" in data
    assert data["num_rays_launched"] == 500
    assert data["num_rays_arrived"] == 500
    assert data["vignetting_ratio"] == 0.0


def test_simulate_with_images(client):
    """Test simulation with image generation."""
    payload = {
        "wavelength": 780.0,
        "ld_tilt": 0.0,
        "ld_div_fast": 25.0,
        "ld_div_slow": 8.0,
        "ld_div_fast_err": 0.0,
        "ld_div_slow_err": 0.0,
        "ld_emit_w": 3.0,
        "ld_emit_h": 1.0,
        "num_rays": 100,
        "coll_r1": -3.5,
        "coll_r2": -15.0,
        "coll_k1": -1.0,
        "coll_k2": 0.0,
        "coll_t": 2.0,
        "coll_n": 1.517,
        "dist_ld_coll": 4.0,
        "coll_x_shift": 0.01,
        "coll_y_shift": -0.02,
        "obj_f": 4.0,
        "dist_coll_obj": 50.0,
        "sensor_pos": 4.0,
        "return_ray_hits": True,
        "return_ray_path_image": True,
        "return_spot_diagram_image": True,
    }
    
    response = client.post("/simulate", json=payload)
    assert response.status_code == 200
    
    data = response.json()
    assert data["ray_hits"] is not None
    assert len(data["ray_hits"]) == 100
    assert data["ray_path_image"] is not None
    assert data["spot_diagram_image"] is not None
