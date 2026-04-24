"""Tests for the new web routes (all GET pages)."""

import pytest

from makepdf.web.app import app


@pytest.fixture
def client():
    try:
        from fastapi.testclient import TestClient
        return TestClient(app)
    except TypeError:
        pytest.skip("Incompatible starlette/httpx versions for TestClient")


class TestNewWebPages:
    def test_redact_page(self, client):
        resp = client.get("/redact")
        assert resp.status_code == 200

    def test_crop_page(self, client):
        resp = client.get("/crop")
        assert resp.status_code == 200

    def test_stamp_page(self, client):
        resp = client.get("/stamp")
        assert resp.status_code == 200

    def test_bates_page(self, client):
        resp = client.get("/bates")
        assert resp.status_code == 200

    def test_compare_page(self, client):
        resp = client.get("/compare")
        assert resp.status_code == 200

    def test_flatten_page(self, client):
        resp = client.get("/flatten")
        assert resp.status_code == 200

    def test_metadata_page(self, client):
        resp = client.get("/metadata")
        assert resp.status_code == 200

    def test_attach_page(self, client):
        resp = client.get("/attach")
        assert resp.status_code == 200

    def test_link_page(self, client):
        resp = client.get("/link")
        assert resp.status_code == 200

    def test_optimize_page(self, client):
        resp = client.get("/optimize")
        assert resp.status_code == 200

    def test_a11y_page(self, client):
        resp = client.get("/a11y")
        assert resp.status_code == 200

    def test_markup_page(self, client):
        resp = client.get("/markup")
        assert resp.status_code == 200
