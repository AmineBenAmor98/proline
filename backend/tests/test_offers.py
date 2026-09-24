"""Sending a client their offer.

An offer email is the most consequential thing this admin does: it is
irreversible, it goes to a stranger, and it is a price the business is then
expected to honour. These tests are mostly about the record it leaves.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.services import mailer, offers


@pytest.fixture
def outbox(monkeypatch):
    """Capture instead of send. Nothing in this suite may open a socket to a
    mail provider -- a test that accidentally emails a real address is a very
    bad test."""
    sent = []

    async def fake_send(settings, message):
        sent.append(message)

    monkeypatch.setattr(mailer, "send", fake_send)
    monkeypatch.setattr(offers, "send", fake_send)
    return sent


@pytest.fixture
def smtp_configured(monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "smtp_host", "smtp.test.invalid", raising=False)
    monkeypatch.setattr(
        settings, "mail_reply_to", "info@prolinecleaningsolutions.ca", raising=False
    )
    return settings


async def _a_request(client: AsyncClient) -> str:
    body = {
        "audience": "residential",
        "property": {"property_type": "condo", "bedrooms": 2, "bathrooms": 1,
                     "area_sqft": 900},
        "frequency": "weekly",
        "extras": {}, "modifiers": {},
        "contact": {"full_name": "Marie Tremblay", "phone": "5145550123",
                    "email": "marie@example.ca", "consent_given": True},
        "attribution": {},
    }
    response = await client.post("/api/quotes", json=body)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_money_uses_french_typography() -> None:
    """A price that line-wraps in a quote email reads as two numbers."""
    assert offers.money(25470) == "254,70 $"
    assert offers.money(125470) == "1 254,70 $"
    assert " $" in offers.money(0)


async def test_preview_does_not_send(
    client: AsyncClient, admin_headers, outbox, smtp_configured
) -> None:
    request_id = await _a_request(client)
    response = await client.post(
        f"/api/admin/requests/{request_id}/offer/preview",
        headers=admin_headers,
        json={"message": "Bonjour, voici notre offre.", "total_cents": 25000},
    )
    assert response.status_code == 200
    assert outbox == []
    body = response.json()
    assert body["to_email"] == "marie@example.ca"
    assert "250,00" in body["text"]
    assert "Marie" in body["text"]


async def test_send_records_exactly_what_went_out(
    client: AsyncClient, admin_headers, outbox, smtp_configured
) -> None:
    request_id = await _a_request(client)
    payload = {"message": "Disponible jeudi matin.", "total_cents": 25000}

    preview = (await client.post(
        f"/api/admin/requests/{request_id}/offer/preview",
        headers=admin_headers, json=payload)).json()

    sent = await client.post(
        f"/api/admin/requests/{request_id}/offer", headers=admin_headers, json=payload)
    assert sent.status_code == 200, sent.text
    assert sent.json()["status"] == "sent"
    assert len(outbox) == 1

    # The stored log, the preview and the delivered message must be one text.
    # Re-rendering later would answer with today's template and today's price.
    logged = (await client.get(
        f"/api/admin/requests/{request_id}/offers", headers=admin_headers)).json()
    assert len(logged) == 1
    assert logged[0]["total_cents"] == 25000
    assert outbox[0]["To"] == "marie@example.ca"
    assert outbox[0].get_content().strip() == preview["text"].strip()


async def test_sending_moves_the_request_out_of_the_inbox(
    client: AsyncClient, admin_headers, outbox, smtp_configured
) -> None:
    request_id = await _a_request(client)
    await client.post(f"/api/admin/requests/{request_id}/offer", headers=admin_headers,
                      json={"message": "Voici l'offre.", "total_cents": 19900})
    rows = (await client.get("/api/admin/requests", headers=admin_headers)).json()["items"]
    row = next(r for r in rows if r["id"] == request_id)
    assert row["status"] == "quoted"
    assert row["quoted_total_cents"] == 19900


async def test_a_revised_offer_is_a_second_record_not_an_edit(
    client: AsyncClient, admin_headers, outbox, smtp_configured
) -> None:
    """The client was told 250 on Monday and 280 on Wednesday. Both happened."""
    request_id = await _a_request(client)
    for cents in (25000, 28000):
        await client.post(f"/api/admin/requests/{request_id}/offer",
                          headers=admin_headers,
                          json={"message": "Offre.", "total_cents": cents})

    logged = (await client.get(
        f"/api/admin/requests/{request_id}/offers", headers=admin_headers)).json()
    assert [r["total_cents"] for r in logged] == [28000, 25000]  # newest first


async def test_unconfigured_smtp_says_so_and_sends_nothing(
    client: AsyncClient, admin_headers, outbox, monkeypatch
) -> None:
    """A 503 Amine can act on, not a silent success."""
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "smtp_host", "", raising=False)

    async def refuse(settings, message):
        raise mailer.MailNotConfigured("SMTP_HOST is not set")

    monkeypatch.setattr(offers, "send", refuse)

    request_id = await _a_request(client)
    response = await client.post(
        f"/api/admin/requests/{request_id}/offer", headers=admin_headers,
        json={"message": "Offre.", "total_cents": 25000})
    assert response.status_code == 503
    assert "SMTP_HOST" in response.json()["detail"]

    # And no attempt was recorded, because none was made.
    logged = (await client.get(
        f"/api/admin/requests/{request_id}/offers", headers=admin_headers)).json()
    assert logged == []


async def test_a_refused_send_is_kept_as_a_failed_attempt(
    client: AsyncClient, admin_headers, monkeypatch, smtp_configured
) -> None:
    """A client saying they got nothing is answered from this row."""

    async def refuse(settings, message):
        raise RuntimeError("550 recipient rejected")

    monkeypatch.setattr(offers, "send", refuse)

    request_id = await _a_request(client)
    response = await client.post(
        f"/api/admin/requests/{request_id}/offer", headers=admin_headers,
        json={"message": "Offre.", "total_cents": 25000})
    assert response.status_code == 502
    assert "550" in response.json()["detail"]

    logged = (await client.get(
        f"/api/admin/requests/{request_id}/offers", headers=admin_headers)).json()
    assert len(logged) == 1
    assert logged[0]["status"] == "failed"
    assert "550" in logged[0]["error"]
    assert logged[0]["sent_at"] is None


async def test_offer_endpoints_need_a_token(client: AsyncClient) -> None:
    request_id = await _a_request(client)
    for path in (f"/api/admin/requests/{request_id}/offer",
                 f"/api/admin/requests/{request_id}/offer/preview"):
        response = await client.post(path, json={"message": "x", "total_cents": 1})
        assert response.status_code == 401
