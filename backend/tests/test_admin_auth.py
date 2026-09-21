"""Admin sign-in. The panel is the only door to client data, so these matter."""

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="needs a Postgres DATABASE_URL"
)

GOOD = {"username": os.environ.get("ADMIN_USERNAME", "admin"),
        "password": os.environ.get("ADMIN_PASSWORD", "test-password")}


async def test_login_returns_a_token(client):
    response = await client.post("/api/admin/login", json=GOOD)
    assert response.status_code == 200
    body = response.json()
    assert body["token"] and body["username"] == GOOD["username"]
    assert body["expires_in"] > 0


async def test_wrong_password_is_refused(client):
    response = await client.post(
        "/api/admin/login", json={"username": GOOD["username"], "password": "nope"}
    )
    assert response.status_code == 401


async def test_unknown_user_is_refused(client):
    response = await client.post(
        "/api/admin/login", json={"username": "someone", "password": GOOD["password"]}
    )
    assert response.status_code == 401


async def test_token_opens_the_panel(client, admin_headers):
    response = await client.get("/api/admin/me", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["username"] == GOOD["username"]


async def test_a_tampered_token_is_refused(client, admin_headers):
    tampered = admin_headers["Authorization"] + "x"
    response = await client.get("/api/admin/me", headers={"Authorization": tampered})
    assert response.status_code == 401


async def test_no_header_is_refused(client):
    assert (await client.get("/api/admin/requests")).status_code == 401


async def test_an_accented_password_does_not_break_sign_in(client, monkeypatch):
    """Montreal. The password is going to have an accent in it sooner or later.

    `hmac.compare_digest` refuses str arguments with non-ASCII characters, so this
    used to be a 500 on every attempt -- including the right one."""
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "admin_password", "Été2026!", raising=False)

    wrong = await client.post("/api/admin/login", json={"username": "admin", "password": "nope"})
    assert wrong.status_code == 401

    right = await client.post(
        "/api/admin/login", json={"username": "admin", "password": "Été2026!"}
    )
    assert right.status_code == 200, right.text
    assert right.json()["token"]


async def test_a_non_ascii_authorization_header_is_a_401_not_a_500(client):
    """Starlette decodes headers as latin-1, so any byte above 0x7f arrives as a
    non-ASCII str. That reached the comparison and took down every admin
    endpoint for anyone who sent one."""
    # httpx will not encode a non-ASCII header from a str, which is exactly how
    # such a header reaches the app in the wild: as raw bytes off the wire.
    response = await client.get(
        "/api/admin/requests", headers={b"Authorization": "Bearer ab.ç".encode("latin-1")}
    )
    assert response.status_code == 401
