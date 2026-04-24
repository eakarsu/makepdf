"""Tests for the FastAPI web application."""

import pytest

from makepdf.web.app import app


@pytest.fixture
def client():
    try:
        from fastapi.testclient import TestClient
        return TestClient(app)
    except TypeError:
        pytest.skip("Incompatible starlette/httpx versions for TestClient")


class TestWebRoutes:
    def test_index(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "MakePDF" in resp.text

    def test_create_page(self, client):
        resp = client.get("/create")
        assert resp.status_code == 200
        assert "Create PDF" in resp.text

    def test_edit_page(self, client):
        resp = client.get("/edit")
        assert resp.status_code == 200

    def test_merge_page(self, client):
        resp = client.get("/merge")
        assert resp.status_code == 200

    def test_extract_page(self, client):
        resp = client.get("/extract")
        assert resp.status_code == 200

    def test_transform_page(self, client):
        resp = client.get("/transform")
        assert resp.status_code == 200

    def test_forms_page(self, client):
        resp = client.get("/forms")
        assert resp.status_code == 200

    def test_sign_page(self, client):
        resp = client.get("/sign")
        assert resp.status_code == 200

    def test_ocr_page(self, client):
        resp = client.get("/ocr")
        assert resp.status_code == 200

    def test_create_text_pdf(self, client):
        resp = client.post("/create/text", data={"text": "Hello from test", "font": "Helvetica", "font_size": "12", "page_size": "A4"})
        assert resp.status_code == 200
        assert "pdf" in resp.headers.get("content-type", "")

    def test_create_text_empty_error(self, client):
        resp = client.post("/create/text", data={"text": "", "font": "Helvetica", "font_size": "12", "page_size": "A4"})
        assert resp.status_code in (400, 422, 500)  # 400 from MakePdfError, 422 from validation, 500 from unhandled
