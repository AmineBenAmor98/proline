"""The rate card screen's API.

The invariant these tests protect: publishing INSERTs a new version and never
mutates the one that priced an existing request, because `computed_breakdown`
records the version it used.
"""

import copy

RESIDENTIAL = {
    "audience": "residential",
    "property": {"property_type": "house", "area_sqft": 1450, "bedrooms": 3, "bathrooms": 2},
    "frequency": "biweekly",
    "extras": [],
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
    priced_with = (await client.get("/api/admin/rate-card", headers=admin_headers)).json()["version"]

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
    created = await client.post("/api/admin/rate-card", headers=admin_headers, json=card_from(active))
    assert created.json()["residential_online_pricing"] is False

    await client.patch(
        "/api/admin/rate-card/online-pricing", headers=admin_headers, json={"enabled": True}
    )


async def test_a_missing_grid_cell_routes_to_a_human(client, admin_headers):
    active = (await client.get("/api/admin/rate-card", headers=admin_headers)).json()
    draft = card_from(active)
    draft["grid"]["residential_base_cents"].pop("3br_2ba", None)
    assert (await client.post("/api/admin/rate-card", headers=admin_headers, json=draft)).status_code == 201

    submitted = await client.post("/api/quotes", json=RESIDENTIAL)
    assert submitted.status_code == 201
    assert submitted.json()["price"] is None
