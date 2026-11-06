"""The register, profile and My Reading pages (DLBS-40) are served and call real endpoints."""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.main import app

WEB = Path(__file__).resolve().parents[2] / "src" / "web"
PAGES = {
    "register.html": "Create an account",
    "profile.html": "Profile",
    "reading.html": "My Reading",
}


@pytest.mark.parametrize("page, heading", PAGES.items())
def test_page_is_served_with_the_app_shell(page, heading):
    response = TestClient(app).get("/" + page)

    assert response.status_code == 200
    assert f"<h1>{heading}</h1>" in response.text
    assert '<script src="/js/app.js"></script>' in response.text
    assert '<link rel="stylesheet" href="/css/users.css">' in response.text


@pytest.mark.parametrize("page", PAGES)
def test_page_calls_only_endpoints_the_app_has(page):
    html = (WEB / page).read_text(encoding="utf-8")
    called = set(re.findall(r'"(/api/[a-z_/]+)', html))

    assert called
    assert called <= set(app.openapi()["paths"])


@pytest.mark.parametrize("page", ["profile.html", "reading.html"])
def test_page_needs_a_login(page):
    assert "DL.requireLogin()" in (WEB / page).read_text(encoding="utf-8")


def test_stylesheet_is_served():
    response = TestClient(app).get("/css/users.css")

    assert response.status_code == 200
    assert ".reading-list" in response.text


def test_login_page_links_to_register():
    assert 'href="/register.html"' in TestClient(app).get("/login.html").text
