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
        settings, "mail_reply_to", "contact@proline-cleaningsolutions.com", raising=False
    )
    return settings


def text_part(message) -> str:
    """The text/plain half of a multipart/alternative message.

    `get_content()` on the message itself raises KeyError once there is more
    than one part, which is how this test caught the change rather than passing
    against an email nobody had looked at.
    """
    part = message.get_body(preferencelist=("plain",))
    assert part is not None, "every offer must carry a plain-text part"
    return part.get_content()


def html_part(message) -> str | None:
    part = message.get_body(preferencelist=("html",))
    return part.get_content() if part is not None else None


async def _a_request(
    client: AsyncClient, *, audience="residential", property_type="condo",
    bedrooms=2, bathrooms=1, restrooms=None, floors=None, area_sqft=900,
    frequency="weekly", locale="fr",
) -> str:
    """A submitted request, with the knobs these tests actually turn."""
    prop = {"property_type": property_type, "area_sqft": area_sqft}
    for key, value in (("bedrooms", bedrooms), ("bathrooms", bathrooms),
                       ("restrooms", restrooms), ("floors", floors)):
        if value is not None:
            prop[key] = value
    body = {
        "audience": audience,
        "property": prop,
        "frequency": frequency,
        "extras": {}, "modifiers": {},
        "contact": {"full_name": "Marie Tremblay", "phone": "5145550123",
                    "email": "marie@example.ca", "locale": locale,
                    "consent_given": True},
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
    assert text_part(outbox[0]).strip() == preview["text"].strip()


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


# --------------------------------------------------------------------------
# What the email has to carry
#
# Every case below is something the sent email did not say. None of them is a
# crash or a 500; each is a quote that reads wrong to the person receiving it,
# which is the only kind of bug this particular email can have.
# --------------------------------------------------------------------------

async def _send(client, admin_headers, request_id, *, total_cents=269450,
                message="Merci pour votre demande."):
    response = await client.post(
        f"/api/admin/requests/{request_id}/offer",
        headers=admin_headers,
        json={"message": message, "total_cents": total_cents},
    )
    assert response.status_code == 200, response.text
    return response


async def test_the_price_says_what_period_it_covers(
    client, admin_headers, outbox, smtp_configured
):
    """THE EXPENSIVE ONE. Every price here is per visit. A bare "2 694,50 $" on a
    quote for a job that recurs weekly reads as the price of the arrangement,
    and the misunderstanding only surfaces on the first invoice."""
    request_id = await _a_request(client)          # weekly
    await _send(client, admin_headers, request_id)
    body = text_part(outbox[0])
    assert "par visite" in body, body
    assert "chaque semaine" in body, body


async def test_a_one_time_job_does_not_say_per_visit(
    client, admin_headers, outbox, smtp_configured
):
    request_id = await _a_request(client, frequency="one_time")
    await _send(client, admin_headers, request_id)
    body = text_part(outbox[0])
    assert "pour la visite" in body, body


async def test_the_email_carries_a_reference(
    client, admin_headers, outbox, smtp_configured
):
    """The confirmation page gives the visitor one and the admin shows one. A
    reply three weeks later had nothing to match it against."""
    request_id = await _a_request(client)
    await _send(client, admin_headers, request_id)
    short = request_id[:8]
    assert short in text_part(outbox[0])
    assert short in outbox[0]["Subject"]


async def test_the_area_is_grouped_like_the_price(
    client, admin_headers, outbox, smtp_configured
):
    """"Prix : 2 694,50 $" three lines above "12000 pi²"."""
    request_id = await _a_request(client, area_sqft=12000)
    await _send(client, admin_headers, request_id)
    body = text_part(outbox[0])
    assert "12 000 pi²" in body, body
    assert "12000" not in body


async def test_a_commercial_property_is_described(
    client, admin_headers, outbox, smtp_configured
):
    """It listed bedrooms, bathrooms and area. A shop has none of the first two,
    so the property line came out as a bare number of square feet."""
    request_id = await _a_request(
        client, audience="commercial", property_type="retail",
        bedrooms=None, bathrooms=None, restrooms=4, floors=2, area_sqft=2100,
    )
    await _send(client, admin_headers, request_id)
    body = text_part(outbox[0])
    assert "4 sanitaires" in body, body
    assert "2 étages" in body, body
    assert "chambre" not in body


async def test_an_english_lead_gets_an_english_quote(
    client, admin_headers, outbox, smtp_configured
):
    """`Lead.locale` records which form they filled. It was ignored."""
    request_id = await _a_request(client, locale="en")
    await _send(client, admin_headers, request_id)
    body = text_part(outbox[0])
    assert "Hello" in body, body
    assert "per visit" in body, body
    assert "Taxes extra." in body, body
    assert "Bonjour" not in body
    assert "Your quote" in outbox[0]["Subject"], outbox[0]["Subject"]


async def test_the_email_offers_a_telephone_number_and_an_expiry(
    client, admin_headers, outbox, smtp_configured
):
    """Someone ready to accept had a reply button and nothing else."""
    request_id = await _a_request(client)
    await _send(client, admin_headers, request_id)
    body = text_part(outbox[0])
    assert "514 242-4779" in body, body
    assert "valide" in body.lower(), body


async def test_both_parts_are_sent_and_agree_on_the_price(
    client, admin_headers, outbox, smtp_configured
):
    """A client that renders neither well is not a client that gets a different
    price."""
    request_id = await _a_request(client)
    await _send(client, admin_headers, request_id, total_cents=269450)
    text, html = text_part(outbox[0]), html_part(outbox[0])
    assert html, "the offer must carry an HTML alternative"
    assert outbox[0].get_content_type() == "multipart/alternative"
    price = offers.money(269450)
    assert price in text
    assert price in html


async def test_the_html_fetches_nothing_from_the_network(
    client, admin_headers, outbox, smtp_configured
):
    """The logo travels WITH the message, as cid:, never as a URL.

    A remote <img> is what makes a mail client print "this message has blocked
    content" across the top of a quote -- to a stranger deciding whether to
    trust us with their keys -- and it doubles as a read receipt they never
    agreed to. So an image is fine; an image the recipient's client has to go
    and fetch from us is not.
    """
    import re

    request_id = await _a_request(client)
    await _send(client, admin_headers, request_id)
    html = html_part(outbox[0])

    sources = re.findall(r'src="([^"]*)"', html)
    assert sources, "the logo should be there"
    for src in sources:
        assert src.startswith("cid:"), f"remote or inline-data source: {src}"

    assert "fonts.googleapis" not in html, "no web fonts"
    assert "<script" not in html.lower()
    # url() in a style attribute would fetch just as surely as an <img>.
    assert "url(" not in html.lower()


async def test_the_logo_is_attached_to_the_html_part(
    client, admin_headers, outbox, smtp_configured
):
    """Related to the HTML, not attached to the message.

    Attaching it to the message makes it multipart/mixed, and the badge then
    arrives as a file to download sitting under the quote instead of a picture
    inside it.
    """
    request_id = await _a_request(client)
    await _send(client, admin_headers, request_id)
    message = outbox[0]

    assert message.get_content_type() == "multipart/alternative"
    images = [p for p in message.walk() if p.get_content_maintype() == "image"]
    assert len(images) == 1, [p.get_content_type() for p in message.walk()]
    assert images[0].get("Content-ID") == f"<{offers.LOGO_CID}>"
    assert images[0].get_content_disposition() == "inline"
    assert len(images[0].get_payload(decode=True)) < 40_000, "keep the badge small"

    # And the plain-text half is untouched by any of it.
    assert "cid:" not in text_part(message)


async def test_a_missing_logo_does_not_cost_the_quote(
    client, admin_headers, outbox, smtp_configured, monkeypatch
):
    monkeypatch.setattr(offers, "logo_bytes", lambda _dir: None)
    request_id = await _a_request(client)
    await _send(client, admin_headers, request_id)
    html = html_part(outbox[0])
    assert html, "the quote still goes out"
    assert "<img" not in html.lower()
    assert "PROLINE" in html.upper()


async def test_a_name_of_pure_whitespace_does_not_500(monkeypatch):
    """`full_name.split()[0]` on "   ", which clears the form's min_length of 2.
    It would have surfaced as a 500 at the moment the send button was pressed."""
    from types import SimpleNamespace

    from app.core.config import get_settings

    lead = SimpleNamespace(full_name="   ", locale="fr", email="x@example.ca")
    prop = SimpleNamespace(bedrooms=2, bathrooms=1, restrooms=None, floors=None,
                           area_sqft=900)
    subject, text = offers.render(
        get_settings(), lead=lead, prop=prop, message="Bonjour", total_cents=25000
    )
    assert text.startswith("Bonjour,")
    assert subject


async def test_the_preview_is_what_gets_sent(
    client, admin_headers, outbox, smtp_configured
):
    """The preview used to be rendered without the request, so it showed neither
    the reference nor the frequency the sent email would carry."""
    request_id = await _a_request(client)
    preview = (await client.post(
        f"/api/admin/requests/{request_id}/offer/preview",
        headers=admin_headers,
        json={"message": "Merci pour votre demande.", "total_cents": 269450},
    )).json()
    await _send(client, admin_headers, request_id)
    assert text_part(outbox[0]).strip() == preview["text"].strip()
    assert outbox[0]["Subject"] == preview["subject"]
