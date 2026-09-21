"""The rate card screen's API.

The invariant these tests protect: publishing INSERTs a new version and never
mutates the one that priced an existing request, because `computed_breakdown`
records the version it used.
"""

import copy

import pytest

RESIDENTIAL = {
    "audience": "residential",
    "property": {"property_type": "house", "area_sqft": 1450, "bedrooms": 3, "bathrooms": 2},
    "frequency": "biweekly",
    "extras": {},
    "contact": {"full_name": "Test Client", "phone": "5140000000", "consent_given": True},
}


def card_from(payload: dict, **overrides) -> dict:
    """Deep-copied on purpose: editing the returned draft must not touch the
    snapshot a test is comparing against."""
    card = {
        "hourly_rate_cents": payload["hourly_rate_cents"],
        "minimum_visit_cents": payload["minimum_visit_cents"],
        "travel_cents": payload["travel_cents"],
        "grid": copy.deepcopy(payload["grid"]),
    }
    card.update(overrides)
    return card


async def test_rate_card_needs_a_token(client):
    assert (await client.get("/api/admin/rate-card")).status_code == 401


async def test_publishing_creates_a_version_and_closes_the_old_one(client, admin_headers):
    before = (await client.get("/api/admin/rate-card", headers=admin_headers)).json()
    draft = card_from(before)
    draft["grid"]["residential_base_cents"]["3br_2ba"] = 19500

    created = await client.post("/api/admin/rate-card", headers=admin_headers, json=draft)
    assert created.status_code == 201, created.text
    new = created.json()
    assert new["version"] != before["version"]
    assert new["is_active"] is True
    assert new["grid"]["residential_base_cents"]["3br_2ba"] == 19500

    history = (await client.get("/api/admin/rate-cards", headers=admin_headers)).json()["items"]
    by_version = {row["version"]: row for row in history}
    assert by_version[new["version"]]["is_active"] is True
    assert by_version[before["version"]]["is_active"] is False
    assert by_version[before["version"]]["effective_to"] is not None
    # the old card is still there, with its numbers untouched
    assert by_version[before["version"]]["grid"]["residential_base_cents"]["3br_2ba"] \
        == before["grid"]["residential_base_cents"]["3br_2ba"]


async def test_a_sent_quote_keeps_the_version_that_priced_it(client, admin_headers):
    first = await client.post("/api/quotes", json=RESIDENTIAL)
    assert first.status_code == 201, first.text
    card = (await client.get("/api/admin/rate-card", headers=admin_headers)).json()
    priced_with = card["version"]

    draft = card_from((await client.get("/api/admin/rate-card", headers=admin_headers)).json())
    draft["grid"]["residential_base_cents"]["3br_2ba"] = 29500
    await client.post("/api/admin/rate-card", headers=admin_headers, json=draft)

    history = (await client.get("/api/admin/rate-cards", headers=admin_headers)).json()["items"]
    old = next(row for row in history if row["version"] == priced_with)
    assert old["priced_requests"] >= 1
    assert old["grid"]["residential_base_cents"]["3br_2ba"] != 29500


async def test_preview_prices_a_draft_without_saving_it(client, admin_headers):
    before = (await client.get("/api/admin/rate-card", headers=admin_headers)).json()
    draft = card_from(before)
    draft["grid"]["residential_base_cents"]["3br_2ba"] = \
        before["grid"]["residential_base_cents"]["3br_2ba"] + 5000

    response = await client.post(
        "/api/admin/rate-card/preview",
        headers=admin_headers,
        json={
            "card": draft,
            "scenarios": [{
                "label": "Condo", "audience": "residential", "property_type": "condo",
                "area_sqft": 900, "bedrooms": 3, "bathrooms": 2, "frequency": "one_time",
            }],
        },
    )
    assert response.status_code == 200, response.text
    row = response.json()["results"][0]
    assert row["draft_total_cents"] == row["active_total_cents"] + 5000
    assert row["draft_lines"]
    # nothing was written
    assert (await client.get("/api/admin/rate-card", headers=admin_headers)).json()["version"] \
        == before["version"]


async def test_preview_reports_a_missing_grid_cell_instead_of_failing(client, admin_headers):
    active = (await client.get("/api/admin/rate-card", headers=admin_headers)).json()
    response = await client.post(
        "/api/admin/rate-card/preview",
        headers=admin_headers,
        json={
            "card": card_from(active),
            "scenarios": [{
                "label": "Immense", "audience": "residential", "property_type": "house",
                "bedrooms": 5, "bathrooms": 1, "frequency": "one_time",
            }],
        },
    )
    assert response.status_code == 200
    row = response.json()["results"][0]
    assert row["draft_total_cents"] is None
    assert row["error"]


async def test_a_decimal_slip_is_refused(client, admin_headers):
    active = (await client.get("/api/admin/rate-card", headers=admin_headers)).json()
    draft = card_from(active)
    draft["grid"]["residential_base_cents"]["3br_2ba"] = 1850  # 18,50 $, not 185,00 $

    response = await client.post("/api/admin/rate-card", headers=admin_headers, json=draft)
    assert response.status_code == 422
    assert "minimum" in response.text
    assert (await client.get("/api/admin/rate-card", headers=admin_headers)).json()["version"] \
        == active["version"]


async def test_the_kill_switch_stops_residential_prices(client, admin_headers):
    off = await client.patch(
        "/api/admin/rate-card/online-pricing", headers=admin_headers, json={"enabled": False}
    )
    assert off.status_code == 200
    assert off.json()["residential_online_pricing"] is False

    draft = {k: RESIDENTIAL[k] for k in ("audience", "property", "frequency", "extras")}
    priced = await client.post("/api/quotes/price", json=draft)
    assert priced.status_code == 409

    submitted = await client.post("/api/quotes", json=RESIDENTIAL)
    assert submitted.status_code == 201
    assert submitted.json()["price"] is None
    assert submitted.json()["status"] == "new"

    on = await client.patch(
        "/api/admin/rate-card/online-pricing", headers=admin_headers, json={"enabled": True}
    )
    assert on.json()["residential_online_pricing"] is True
    assert (await client.post("/api/quotes/price", json=draft)).status_code == 200


async def test_the_switch_survives_a_publish(client, admin_headers):
    await client.patch(
        "/api/admin/rate-card/online-pricing", headers=admin_headers, json={"enabled": False}
    )
    active = (await client.get("/api/admin/rate-card", headers=admin_headers)).json()
    created = await client.post(
        "/api/admin/rate-card", headers=admin_headers, json=card_from(active)
    )
    assert created.json()["residential_online_pricing"] is False

    await client.patch(
        "/api/admin/rate-card/online-pricing", headers=admin_headers, json={"enabled": True}
    )


async def test_a_missing_grid_cell_routes_to_a_human(client, admin_headers):
    active = (await client.get("/api/admin/rate-card", headers=admin_headers)).json()
    draft = card_from(active)
    draft["grid"]["residential_base_cents"].pop("3br_2ba", None)
    republished = await client.post(
        "/api/admin/rate-card", headers=admin_headers, json=draft
    )
    assert republished.status_code == 201

    submitted = await client.post("/api/quotes", json=RESIDENTIAL)
    assert submitted.status_code == 201
    assert submitted.json()["price"] is None


async def test_a_multiplied_extra_must_say_what_it_counts(client, admin_headers):
    """"Vitres intérieures × 6" with no unit leaves the client guessing what six is."""
    active = (await client.get("/api/admin/rate-card", headers=admin_headers)).json()
    draft = card_from(active)
    draft["grid"]["extras"]["windows"]["per_fr"] = ""

    response = await client.post("/api/admin/rate-card", headers=admin_headers, json=draft)
    assert response.status_code == 422
    assert "unit label" in response.text


async def test_a_flat_extra_carries_no_unit_label(client, admin_headers):
    """A leftover 'par fenêtre' on a forfait would print on a quote and be wrong."""
    active = (await client.get("/api/admin/rate-card", headers=admin_headers)).json()
    draft = card_from(active)
    draft["grid"]["extras"]["fridge"]["per_fr"] = "par réfrigérateur"

    response = await client.post("/api/admin/rate-card", headers=admin_headers, json=draft)
    assert response.status_code == 422
    assert "not billed per anything" in response.text


async def test_an_extra_code_stays_a_code(client, admin_headers):
    """The code is what stored requests key on, so it is not free text."""
    active = (await client.get("/api/admin/rate-card", headers=admin_headers)).json()
    draft = card_from(active)
    draft["grid"]["extras"]["Vitres Intérieures!"] = {
        "unit": "flat", "cents": 1000, "label_fr": "x", "label_en": "x",
    }

    response = await client.post("/api/admin/rate-card", headers=admin_headers, json=draft)
    assert response.status_code == 422
    assert "extra code" in response.text


async def test_the_preview_prices_a_quantity(client, admin_headers):
    """A preview that could only say "windows: yes" would never catch a per-unit
    decimal slip -- the very thing this screen exists to catch."""
    active = (await client.get("/api/admin/rate-card", headers=admin_headers)).json()
    draft = card_from(active)
    draft["grid"]["extras"]["windows"]["cents"] = 4000  # 40 $ per window, not 4 $

    scenario = {
        "label": "Condo", "audience": "residential", "property_type": "condo",
        "area_sqft": 1400, "bedrooms": 3, "bathrooms": 2,
        "frequency": "one_time", "extras": {"windows": 8},
    }
    response = await client.post(
        "/api/admin/rate-card/preview", headers=admin_headers,
        json={"card": draft, "scenarios": [scenario]},
    )
    assert response.status_code == 200, response.text
    row = response.json()["results"][0]
    # 8 windows at 40 $ instead of 4 $: 288 $ more than the live card.
    assert row["draft_total_cents"] - row["active_total_cents"] == 8 * (4000 - 400)
    line = next(item for item in row["draft_lines"] if item["code"] == "extra:windows")
    assert line["quantity"] == 8 and line["unit_fr"] == "par fenêtre"


async def test_only_one_card_can_be_active(client, admin_headers):
    """The invariant every price on the site rests on. `get_active_rate_card`
    returns `.first()`, so two active rows would make the price depend on row
    order. `uq_rate_cards_one_active` makes that unrepresentable."""
    import sqlalchemy

    from app.db.session import SessionLocal

    async with SessionLocal() as session:
        active = (await session.execute(
            sqlalchemy.text("SELECT id FROM rate_cards WHERE is_active")
        )).scalars().all()
        assert len(active) == 1

        with pytest.raises(sqlalchemy.exc.IntegrityError):
            await session.execute(sqlalchemy.text(
                """INSERT INTO rate_cards (id, version, effective_from, is_active,
                                           hourly_rate_cents, minimum_visit_cents,
                                           travel_cents, grid)
                   VALUES (gen_random_uuid(), 'second-active', CURRENT_DATE, true,
                           4500, 12000, 0, '{}'::jsonb)"""
            ))
        await session.rollback()


async def test_an_unpriced_request_stores_sql_null_not_json_null(client, admin_headers):
    """`computed_breakdown IS NOT NULL` has to mean "this one got a price".

    SQLAlchemy writes a Python None into a JSON column as the literal `null`
    unless told otherwise, so it did not -- and nothing noticed, because reading
    the column back gives None either way."""
    import sqlalchemy

    from app.db.session import SessionLocal

    # Switch online pricing off: the request is stored with no price.
    await client.patch("/api/admin/rate-card/online-pricing",
                       headers=admin_headers, json={"enabled": False})
    submitted = await client.post("/api/quotes", json=RESIDENTIAL)
    assert submitted.status_code == 201, submitted.text
    assert submitted.json()["price"] is None

    async with SessionLocal() as session:
        row = (await session.execute(sqlalchemy.text(
            """SELECT computed_breakdown IS NULL AS sql_null,
                      jsonb_typeof(computed_breakdown) AS kind
                 FROM quote_requests WHERE id = :id"""
        ), {"id": submitted.json()["id"]})).mappings().one()
    assert row["sql_null"] is True, f"stored a JSON {row['kind']} instead of SQL NULL"


async def test_the_history_counts_what_each_card_actually_priced(client, admin_headers):
    """Counted by the foreign key now, not by digging the version out of every
    stored breakdown's JSONB -- which no index could serve and which quietly
    included the requests that never got a price."""
    priced = await client.post("/api/quotes", json=RESIDENTIAL)
    assert priced.json()["price"] is not None

    await client.patch("/api/admin/rate-card/online-pricing",
                       headers=admin_headers, json={"enabled": False})
    unpriced = await client.post("/api/quotes", json=RESIDENTIAL)
    assert unpriced.json()["price"] is None

    history = (await client.get("/api/admin/rate-cards", headers=admin_headers)).json()["items"]
    active = next(row for row in history if row["is_active"])
    assert active["priced_requests"] == 1


async def test_the_preview_shows_its_arithmetic(client, admin_headers):
    """The tester listed the lines and stopped.

    A scenario with a recurring discount therefore showed four numbers summing
    to one figure under a total that was another, with nothing on screen
    accounting for the difference -- in the one place whose whole job is checking
    a price before it is published."""
    active = (await client.get("/api/admin/rate-card", headers=admin_headers)).json()
    scenario = {
        "label": "Condo", "audience": "residential", "property_type": "condo",
        "area_sqft": 1400, "bedrooms": 3, "bathrooms": 2,
        "frequency": "biweekly", "extras": {"oven": 1, "windows": 8},
    }
    response = await client.post(
        "/api/admin/rate-card/preview", headers=admin_headers,
        json={"card": card_from(active), "scenarios": [scenario]},
    )
    assert response.status_code == 200, response.text
    row = response.json()["results"][0]

    assert row["draft_subtotal_cents"] == sum(line["amount_cents"] for line in row["draft_lines"])
    assert row["draft_discount_cents"] > 0, "biweekly is discounted on this card"
    assert row["draft_total_cents"] == (
        row["draft_subtotal_cents"]
        - row["draft_discount_cents"]
        + row["draft_minimum_adjustment_cents"]
    )

    # And a per-unit line says what it is a quantity of, as the client's does.
    windows = next(line for line in row["draft_lines"] if line["code"] == "extra:windows")
    assert windows["quantity"] == 8
    assert windows["unit_fr"] == "par fenêtre"


async def test_a_card_with_no_questions_can_be_given_the_standard_ones(client, admin_headers):
    """A card seeded before modifiers existed carries none, so /admin/tarifs was
    an empty box, a ceiling on nothing, and a form that asked nothing. Building
    four questions by hand -- each with answers in two languages -- is enough
    friction that the feature would simply go unused."""
    presets = await client.get("/api/admin/rate-card/modifier-presets", headers=admin_headers)
    assert presets.status_code == 200, presets.text
    assert set(presets.json()) == {"premier_menage", "etat", "animaux", "vide"}

    active = (await client.get("/api/admin/rate-card", headers=admin_headers)).json()
    draft = card_from(active)
    draft["grid"]["residential_modifiers"] = presets.json()

    published = await client.post("/api/admin/rate-card", headers=admin_headers, json=draft)
    assert published.status_code == 201, published.text

    # And the form starts asking them, with no deploy in between.
    config = (await client.get("/api/quotes/form-config")).json()
    assert [item["code"] for item in config["modifiers"]] == [
        "premier_menage", "etat", "animaux", "vide"
    ], "asked in the card's order, not alphabetically"


async def test_every_preset_is_a_card_the_server_would_accept(client, admin_headers):
    """They are starting values, not a special case: they go through the same
    validation as anything typed by hand -- including the rule that every
    question needs a free answer."""
    presets = (await client.get(
        "/api/admin/rate-card/modifier-presets", headers=admin_headers
    )).json()
    active = (await client.get("/api/admin/rate-card", headers=admin_headers)).json()

    for code, question in presets.items():
        draft = card_from(active)
        draft["grid"]["residential_modifiers"] = {code: question}
        response = await client.post("/api/admin/rate-card", headers=admin_headers, json=draft)
        assert response.status_code == 201, (code, response.text)
