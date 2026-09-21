"""End-to-end against a real Postgres: submission, pricing, and the admin list.

conftest.py creates and seeds the database these run against, so they need no
guard of their own.
"""

import copy

from sqlalchemy import text

RESIDENTIAL = {
    "audience": "residential",
    "property": {"property_type": "house", "area_sqft": 1450, "bedrooms": 3, "bathrooms": 2},
    "frequency": "biweekly",
    "extras": {"fridge": 1},
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
    payload = {
        **RESIDENTIAL,
        "property": {**RESIDENTIAL["property"], "property_type": "industrial"},
    }
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


async def test_the_form_hard_codes_no_extras(client):
    """The guard on the rule this design rests on.

    Both pages used to list the extras as checkboxes, so adding one meant editing
    French, English and the engine, and a checkbox the card had no price for was
    collected and silently ignored. The card is the list now."""
    import re
    from pathlib import Path

    from app.main import FRONTEND_DIR

    for page in ("soumission.html", "en/soumission.html"):
        markup = (Path(FRONTEND_DIR) / page).read_text(encoding="utf-8")
        assert not re.search(r'name="extras" value=', markup), (
            f"{page} hard-codes an extra; it must render /api/quotes/form-config"
        )
        assert 'id="extras"' in markup, f"{page} has nowhere to render the extras"


async def test_the_form_config_offers_what_the_card_prices(client):
    """The form reads this instead of hard-coding extras, so it cannot offer
    something the engine has no price for."""
    response = await client.get("/api/quotes/form-config")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["rate_card_version"]
    codes = {offer["code"] for offer in body["extras"]}
    assert "oven" in codes
    windows = next(o for o in body["extras"] if o["code"] == "windows")
    assert windows["unit"] == "each"
    assert windows["per_fr"] and windows["per_en"]
    for offer in body["extras"]:
        assert offer["cents"] > 0, offer["code"]


async def test_a_quantity_reaches_the_price(client):
    draft = {k: RESIDENTIAL[k] for k in ("audience", "property", "frequency")}
    few = await client.post("/api/quotes/price", json={**draft, "extras": {"windows": 4}})
    many = await client.post("/api/quotes/price", json={**draft, "extras": {"windows": 40}})
    assert few.status_code == 200 and many.status_code == 200
    assert many.json()["total_cents"] > few.json()["total_cents"], (
        "forty windows must not cost the same as four"
    )


async def test_a_negative_quantity_is_refused(client):
    draft = {k: RESIDENTIAL[k] for k in ("audience", "property", "frequency")}
    response = await client.post("/api/quotes/price", json={**draft, "extras": {"windows": -5}})
    assert response.status_code == 422


async def test_the_admin_sees_what_was_asked_for(client, admin_headers):
    """A total is not a work order. Whoever does the job has to be able to read
    that it covers twelve windows, not that windows were ticked."""
    submitted = await client.post("/api/quotes", json={
        **RESIDENTIAL, "extras": {"windows": 12, "fridge": 1}})
    assert submitted.status_code == 201, submitted.text

    rows = (await client.get("/api/admin/requests", headers=admin_headers)).json()["items"]
    row = next(r for r in rows if r["id"] == submitted.json()["id"])

    by_code = {item["code"]: item for item in row["extras"]}
    assert by_code["windows"]["quantity"] == 12
    assert by_code["windows"]["label"] == "Vitres intérieures"
    assert by_code["windows"]["unit"] == "par fenêtre"
    # A flat extra has no quantity to show: "Inside the fridge x 1" reads like a
    # number that could have been different.
    assert by_code["fridge"]["quantity"] is None


async def test_the_admin_labels_survive_a_price_change(client, admin_headers):
    """The request keeps the wording it was quoted with, even after the card that
    priced it has been superseded."""
    submitted = await client.post("/api/quotes", json={**RESIDENTIAL, "extras": {"windows": 6}})
    assert submitted.status_code == 201, submitted.text

    card = (await client.get("/api/admin/rate-card", headers=admin_headers)).json()
    grid = copy.deepcopy(card["grid"])
    grid["extras"]["windows"]["label_fr"] = "Lavage de vitres"
    published = await client.post("/api/admin/rate-card", headers=admin_headers, json={
        "hourly_rate_cents": card["hourly_rate_cents"],
        "minimum_visit_cents": card["minimum_visit_cents"],
        "travel_cents": card["travel_cents"], "grid": grid})
    assert published.status_code == 201, published.text

    rows = (await client.get("/api/admin/requests", headers=admin_headers)).json()["items"]
    row = next(r for r in rows if r["id"] == submitted.json()["id"])
    windows = next(item for item in row["extras"] if item["code"] == "windows")
    assert windows["label"] == "Vitres intérieures"
    assert windows["quantity"] == 6


async def test_a_commercial_request_still_names_its_extras(client, admin_headers):
    """Nothing priced it, so there is no stored breakdown to read the label from.
    The active card answers instead."""
    submitted = await client.post("/api/quotes", json={**COMMERCIAL, "extras": {"windows": 30}})
    assert submitted.status_code == 201, submitted.text

    rows = (await client.get("/api/admin/requests", headers=admin_headers)).json()["items"]
    row = next(r for r in rows if r["id"] == submitted.json()["id"])
    windows = next(item for item in row["extras"] if item["code"] == "windows")
    assert windows["label"] == "Vitres intérieures"
    assert windows["quantity"] == 30
    assert row["services"] == ["office_cleaning"]


async def test_a_note_saves_on_its_own(client, admin_headers):
    """It used to be read only when a price was sent too, so a note-only patch
    answered 200 and wrote nothing."""
    submitted = await client.post("/api/quotes", json=RESIDENTIAL)
    request_id = submitted.json()["id"]

    patched = await client.patch(
        f"/api/admin/requests/{request_id}", headers=admin_headers,
        json={"notes": "Rappelle lundi, chat à la maison"},
    )
    assert patched.status_code == 200, patched.text

    stored = await client.get("/api/admin/requests", headers=admin_headers)
    assert stored.status_code == 200
    # The note lives on the quote row; read it back directly.
    from sqlalchemy import text as sql

    from app.db.session import SessionLocal

    async with SessionLocal() as session:
        note = (await session.execute(
            sql("SELECT notes FROM quotes WHERE request_id = :id"), {"id": request_id}
        )).scalar_one()
    assert note == "Rappelle lundi, chat à la maison"


async def test_a_status_patch_still_reports_the_price_already_sent(client, admin_headers):
    """The response used to say quoted_total_cents: null whenever this particular
    call did not set one, contradicting the database."""
    submitted = await client.post("/api/quotes", json=RESIDENTIAL)
    request_id = submitted.json()["id"]
    await client.patch(f"/api/admin/requests/{request_id}", headers=admin_headers,
                       json={"quoted_total_cents": 24500})

    later = await client.patch(f"/api/admin/requests/{request_id}", headers=admin_headers,
                               json={"status": "won"})
    assert later.status_code == 200
    assert later.json()["quoted_total_cents"] == 24500
    assert later.json()["status"] == "won"


async def test_a_malformed_request_id_is_refused_not_crashed(client, admin_headers):
    response = await client.patch("/api/admin/requests/hello", headers=admin_headers,
                                  json={"status": "won"})
    assert response.status_code == 422


async def test_an_invented_extra_code_never_reaches_the_database(client):
    """POST /api/quotes is public and unauthenticated. Without a bound on the
    keys, an anonymous caller writes arbitrary strings into JSONB and onto the
    operator's screen."""
    for bad in ({"<script>alert(1)</script>": 1}, {"X" * 60: 1}, {"Windows": 1}):
        response = await client.post("/api/quotes", json={**RESIDENTIAL, "extras": bad})
        assert response.status_code == 422, (bad, response.text)

    many = {f"e{index}": 1 for index in range(45)}
    flooded = await client.post("/api/quotes", json={**RESIDENTIAL, "extras": many})
    assert flooded.status_code == 422


async def test_an_area_priced_extra_with_no_area_routes_to_a_human(client):
    """Not a 500, and not a silent zero: the price is unavailable, which the form
    already knows how to say."""
    draft = {
        "audience": "residential",
        "property": {"property_type": "house", "bedrooms": 3, "bathrooms": 2},
        "frequency": "one_time",
        "extras": {"baseboards": 1},
    }
    response = await client.post("/api/quotes/price", json=draft)
    assert response.status_code == 409


async def test_the_form_config_only_offers_rooms_the_card_prices(client, admin_headers):
    """The whole design rests on this: the form asks only what the card can
    price. It used to send a bedrooms_max and a bathrooms_max, which described a
    dense grid the card does not have."""
    card = (await client.get("/api/admin/rate-card", headers=admin_headers)).json()
    priced = {key for key, cents in card["grid"]["residential_base_cents"].items() if cents}

    config = (await client.get("/api/quotes/form-config")).json()
    assert set(config["residential_cells"]) == priced

    # Every advertised cell really does price.
    for cell in config["residential_cells"]:
        bedrooms, bathrooms = cell.replace("ba", "").split("br_")
        response = await client.post("/api/quotes/price", json={
            "audience": "residential",
            "property": {"property_type": "house", "area_sqft": 900,
                         "bedrooms": int(bedrooms), "bathrooms": int(bathrooms)},
            "frequency": "one_time",
        })
        assert response.status_code == 200, (cell, response.text)


async def test_a_request_arrives_new_even_when_it_priced(client, admin_headers):
    """The inbox had no unread state.

    `status` used to be set to `priced` on arrival whenever the engine produced a
    number, so a residential request nobody had opened showed as "Chiffrée", and
    "Nouvelles" meant "the calculator failed" rather than "not dealt with". The
    status is about the client now; whether it priced is the price column."""
    submitted = await client.post("/api/quotes", json=RESIDENTIAL)
    assert submitted.status_code == 201, submitted.text
    assert submitted.json()["price"] is not None, "this one is supposed to price"
    assert submitted.json()["status"] == "new"

    rows = (await client.get("/api/admin/requests", headers=admin_headers)).json()
    row = next(r for r in rows["items"] if r["id"] == submitted.json()["id"])
    assert row["status"] == "new"
    assert row["computed_total_cents"] is not None


async def test_only_four_statuses_exist():
    """`priced` and `enriching` are gone: neither was a status."""
    from app.models.enums import RequestStatus

    assert [s.value for s in RequestStatus] == ["new", "quoted", "won", "lost"]


async def test_sending_a_price_moves_it_out_of_the_inbox(client, admin_headers):
    submitted = await client.post("/api/quotes", json=RESIDENTIAL)
    request_id = submitted.json()["id"]

    sent = await client.patch(f"/api/admin/requests/{request_id}", headers=admin_headers,
                              json={"quoted_total_cents": 24000})
    assert sent.status_code == 200, sent.text
    assert sent.json()["status"] == "quoted"


async def test_correcting_the_price_on_a_won_job_does_not_walk_it_backwards(client, admin_headers):
    """A won job whose number is adjusted is still won."""
    submitted = await client.post("/api/quotes", json=RESIDENTIAL)
    request_id = submitted.json()["id"]
    await client.patch(f"/api/admin/requests/{request_id}", headers=admin_headers,
                       json={"quoted_total_cents": 24000})
    await client.patch(f"/api/admin/requests/{request_id}", headers=admin_headers,
                       json={"status": "won"})

    corrected = await client.patch(f"/api/admin/requests/{request_id}", headers=admin_headers,
                                   json={"quoted_total_cents": 25500})
    assert corrected.status_code == 200
    assert corrected.json()["status"] == "won"
    assert corrected.json()["quoted_total_cents"] == 25500


async def test_the_admin_sees_the_answers_that_changed_the_price(client, admin_headers):
    """A 459 $ quote beside a 221 $ one is otherwise unexplained."""
    submitted = await client.post("/api/quotes", json={
        **RESIDENTIAL,
        "modifiers": {"premier_menage": "yes", "etat": "tres_sale", "animaux": "none"},
    })
    assert submitted.status_code == 201, submitted.text

    rows = (await client.get("/api/admin/requests", headers=admin_headers)).json()["items"]
    row = next(r for r in rows if r["id"] == submitted.json()["id"])
    labels = [item["label"] for item in row["modifiers"]]

    assert labels == ["Premier ménage : Oui", "État : Très sale"], labels
    # The free answer is not reported: nothing happened, so there is nothing to say.
    assert not any("Animaux" in label for label in labels)


async def test_an_answer_the_card_no_longer_offers_is_still_reported(client, admin_headers):
    """The request keeps what it was asked. A question retired from the card
    afterwards must not make an old quote unreadable."""
    submitted = await client.post("/api/quotes", json={
        **RESIDENTIAL, "modifiers": {"retire": "oui"},
    })
    assert submitted.status_code == 201, submitted.text

    rows = (await client.get("/api/admin/requests", headers=admin_headers)).json()["items"]
    row = next(r for r in rows if r["id"] == submitted.json()["id"])
    assert [item["label"] for item in row["modifiers"]] == ["retire : oui"]
