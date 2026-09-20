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
