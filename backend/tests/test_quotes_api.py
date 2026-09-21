"""End-to-end against a real Postgres: submission, pricing, and the admin list."""

import os

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="needs a Postgres DATABASE_URL"
)

RESIDENTIAL = {
    "audience": "residential",
    "property": {"property_type": "house", "area_sqft": 1450, "bedrooms": 3, "bathrooms": 2},
    "frequency": "biweekly",
    "extras": ["fridge"],
    "contact": {
        "full_name": "Marie Tremblay",
        "email": "marie@example.ca",
        "phone": "514 555-0111",
        "locale": "fr",
        "consent_given": True,
    },
    "attribution": {"utm_campaign": "mtl-menage", "gclid": "abc123"},
}

COMMERCIAL = {
    "audience": "commercial",
    "property": {"property_type": "office", "area_sqft": 4000, "restrooms": 4, "floors": 2},
    "services": ["office_cleaning"],
    "frequency": "weekly",
    "night_access": True,
    "access_notes": "Accès par la ruelle après 19 h.",
    "contact": {
        "full_name": "Groupe Lemieux",
        "email": "info@example.ca",
        "company": "Lemieux inc.",
        "locale": "fr",
        "consent_given": True,
    },
}


async def test_residential_submission_returns_a_firm_price(client):
    response = await client.post("/api/quotes", json=RESIDENTIAL)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["price"] is not None
    assert body["price"]["is_firm"] is True
    assert body["price"]["total_cents"] > 0
    assert body["price"]["discount_cents"] > 0  # biweekly discount applied
    assert "24 h" not in body["message_fr"]


async def test_commercial_submission_hides_the_price(client):
    response = await client.post("/api/quotes", json=COMMERCIAL)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["price"] is None, "a commercial visitor must never see a computed number"
    assert "24 h" in body["message_fr"]


async def test_live_calculator_prices_without_saving(client):
    draft = {k: RESIDENTIAL[k] for k in ("audience", "property", "frequency", "extras")}
    response = await client.post("/api/quotes/price", json=draft)
    assert response.status_code == 200, response.text
    assert response.json()["total_cents"] > 0


async def test_calculator_refuses_commercial(client):
    draft = {"audience": "commercial", "property": COMMERCIAL["property"],
             "services": ["office_cleaning"], "frequency": "weekly"}
    response = await client.post("/api/quotes/price", json=draft)
    assert response.status_code == 403


async def test_consent_is_required(client):
    payload = {**RESIDENTIAL, "contact": {**RESIDENTIAL["contact"], "consent_given": False}}
    response = await client.post("/api/quotes", json=payload)
    assert response.status_code == 422


async def test_contact_channel_is_required(client):
    payload = {**RESIDENTIAL, "contact": {"full_name": "Sans Contact", "locale": "fr",
                                          "consent_given": True}}
    response = await client.post("/api/quotes", json=payload)
    assert response.status_code == 422


async def test_honeypot_saves_nothing(client):
    from app.db.session import SessionLocal

    async with SessionLocal() as session:
        before = (await session.execute(text("select count(*) from leads"))).scalar_one()

    payload = {**RESIDENTIAL, "website": "http://spam.example"}
    response = await client.post("/api/quotes", json=payload)
    assert response.status_code == 201

    async with SessionLocal() as session:
        after = (await session.execute(text("select count(*) from leads"))).scalar_one()
    assert after == before


async def test_attribution_is_stored(client):
    await client.post("/api/quotes", json=RESIDENTIAL)
    from app.db.session import SessionLocal

    async with SessionLocal() as session:
        campaign = (
            await session.execute(
                text("select utm_campaign from leads where gclid = 'abc123' limit 1")
            )
        ).scalar_one()
    assert campaign == "mtl-menage"


async def test_admin_requires_a_token(client):
    response = await client.get("/api/admin/requests")
    assert response.status_code == 401


async def test_admin_lists_and_updates(client, admin_headers):
    created = await client.post("/api/quotes", json=COMMERCIAL)
    request_id = created.json()["id"]

    listing = await client.get("/api/admin/requests", headers=admin_headers)
    assert listing.status_code == 200
    data = listing.json()
    assert data["total"] >= 1
    assert any(row["id"] == request_id for row in data["items"])

    patched = await client.patch(
        f"/api/admin/requests/{request_id}",
        headers=admin_headers,
        json={"quoted_total_cents": 48000, "notes": "Révisé après appel"},
    )
    assert patched.status_code == 200
    assert patched.json()["quoted_total_cents"] == 48000
    assert patched.json()["status"] == "quoted"


async def test_commercial_audience_rejects_a_house(client):
    """The quote form derives the audience from the property type, so a mismatch
    means a tampered or stale client. Reject it rather than storing a row the
    pricing engine cannot read."""
    payload = {**COMMERCIAL, "property": {**COMMERCIAL["property"], "property_type": "house"}}
    response = await client.post("/api/quotes", json=payload)
    assert response.status_code == 422
    assert "residential" in response.text


async def test_residential_audience_rejects_a_warehouse(client):
    payload = {**RESIDENTIAL, "property": {**RESIDENTIAL["property"], "property_type": "industrial"}}
    response = await client.post("/api/quotes", json=payload)
    assert response.status_code == 422


async def test_price_draft_rejects_a_mismatched_pair(client):
    draft = {k: RESIDENTIAL[k] for k in ("audience", "property", "frequency", "extras")}
    draft["property"] = {**draft["property"], "property_type": "office"}
    response = await client.post("/api/quotes/price", json=draft)
    assert response.status_code == 422


async def test_an_unknown_service_code_is_refused(client):
    """`services` is a list of ServiceCode now, not free text: a code the pricing
    grid has never heard of should not reach the database."""
    payload = {**COMMERCIAL, "services": ["office_cleaning", "window_washing_by_drone"]}
    response = await client.post("/api/quotes", json=payload)
    assert response.status_code == 422


async def test_every_service_the_form_offers_is_a_real_code(client):
    """The quote form and the enum drift apart silently otherwise."""
    import re
    from pathlib import Path

    from app.main import FRONTEND_DIR
    from app.models.enums import ServiceCode

    markup = (Path(FRONTEND_DIR) / "soumission.html").read_text(encoding="utf-8")
    offered = set(re.findall(r'name="services" value="([^"]+)"', markup))
    assert offered, "the form offers no services at all"
    assert offered <= {code.value for code in ServiceCode}, offered
