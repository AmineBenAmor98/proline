"""Correcting what the customer told us, from the admin detail page.

The interesting behaviour is not "a field can be saved". It is the difference
between a field left out of the request and a field explicitly cleared, and the
refusal to leave a request with no way to answer it.
"""

from tests.test_quotes_api import COMMERCIAL, RESIDENTIAL


async def _submit(client, payload=RESIDENTIAL):
    response = await client.post("/api/quotes", json=payload)
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _patch(client, request_id, headers, body):
    return await client.patch(
        f"/api/admin/requests/{request_id}/customer", headers=headers, json=body
    )


async def _detail(client, request_id, headers):
    response = await client.get(f"/api/admin/requests/{request_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


# --------------------------------------------------------------------------
# The door
# --------------------------------------------------------------------------

async def test_editing_needs_a_token(client):
    request_id = await _submit(client)
    response = await _patch(client, request_id, {}, {"full_name": "Quelqu'un"})
    assert response.status_code == 401


async def test_a_missing_request_is_404(client, admin_headers):
    ghost = "00000000-0000-4000-8000-000000000000"
    assert (await _patch(client, ghost, admin_headers, {"city": "Laval"})).status_code == 404


# --------------------------------------------------------------------------
# What a save does
# --------------------------------------------------------------------------

async def test_contact_and_address_are_corrected(client, admin_headers):
    request_id = await _submit(client)
    response = await _patch(client, request_id, admin_headers, {
        "full_name": "Amine Ben Amor",
        "phone": "514 242-4779",
        "address_line": "1234 rue Sainte-Catherine",
        "city": "Montréal",
        "borough": "Ville-Marie",
        "postal_code": "H3B 1A1",
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["full_name"] == "Amine Ben Amor"
    assert body["phone"] == "514 242-4779"
    assert body["address_line"] == "1234 rue Sainte-Catherine"
    assert body["borough"] == "Ville-Marie"

    # The answer IS the page's next state, so it has to be the full detail shape.
    assert "photos" in body and "offers" in body and "computed_breakdown" in body


async def test_the_property_numbers_are_corrected(client, admin_headers):
    """"You said 1200 -- it's 2100." The commonest correction there is."""
    request_id = await _submit(client)
    response = await _patch(client, request_id, admin_headers, {"area_sqft": 2100, "bathrooms": 3})
    assert response.status_code == 200, response.text
    assert response.json()["area_sqft"] == 2100
    assert response.json()["bathrooms"] == 3


async def test_whitespace_is_trimmed(client, admin_headers):
    request_id = await _submit(client)
    body = (await _patch(client, request_id, admin_headers, {"city": "  Laval  "})).json()
    assert body["city"] == "Laval"


# --------------------------------------------------------------------------
# Absent is not null -- the whole mechanism
# --------------------------------------------------------------------------

async def test_a_field_left_out_is_left_alone(client, admin_headers):
    """One card's form must not blank the fields belonging to another."""
    request_id = await _submit(client)
    before = await _detail(client, request_id, admin_headers)
    assert before["email"], "the fixture needs an email for this test to mean anything"

    body = (await _patch(client, request_id, admin_headers, {"city": "Laval"})).json()
    assert body["email"] == before["email"]
    assert body["full_name"] == before["full_name"]
    assert body["area_sqft"] == before["area_sqft"]


async def test_an_emptied_field_is_cleared(client, admin_headers):
    request_id = await _submit(client)
    await _patch(client, request_id, admin_headers, {"company": "Proline"})
    body = (await _patch(client, request_id, admin_headers, {"company": ""})).json()
    assert body["company"] is None


async def test_an_explicit_null_clears_too(client, admin_headers):
    request_id = await _submit(client)
    await _patch(client, request_id, admin_headers, {"borough": "Rosemont"})
    body = (await _patch(client, request_id, admin_headers, {"borough": None})).json()
    assert body["borough"] is None


async def test_an_empty_patch_changes_nothing(client, admin_headers):
    request_id = await _submit(client)
    before = await _detail(client, request_id, admin_headers)
    body = (await _patch(client, request_id, admin_headers, {})).json()
    for field in ("full_name", "email", "phone", "area_sqft", "city"):
        assert body[field] == before[field]


# --------------------------------------------------------------------------
# What must not become possible
# --------------------------------------------------------------------------

async def test_a_request_cannot_be_left_unanswerable(client, admin_headers):
    """No email and no phone is a lead nobody can reply to. The public form
    refuses it; so must this."""
    request_id = await _submit(client)
    response = await _patch(client, request_id, admin_headers, {"email": "", "phone": ""})
    assert response.status_code == 422
    assert "courriel" in response.json()["detail"]

    # And nothing was written on the way to the refusal.
    after = await _detail(client, request_id, admin_headers)
    assert after["email"] or after["phone"]


async def test_clearing_the_email_is_fine_when_a_phone_remains(client, admin_headers):
    request_id = await _submit(client)
    await _patch(client, request_id, admin_headers, {"phone": "514 242-4779"})
    response = await _patch(client, request_id, admin_headers, {"email": ""})
    assert response.status_code == 200, response.text
    assert response.json()["email"] is None
    assert response.json()["phone"] == "514 242-4779"


async def test_a_bad_email_is_refused(client, admin_headers):
    request_id = await _submit(client)
    response = await _patch(client, request_id, admin_headers, {"email": "pas-un-courriel"})
    assert response.status_code == 422


async def test_an_out_of_range_area_is_refused(client, admin_headers):
    """The same bounds the public form is held to. 12 pi² is a typo, not a property."""
    request_id = await _submit(client)
    assert (await _patch(client, request_id, admin_headers, {"area_sqft": 12})).status_code == 422


async def test_the_property_type_is_editable_within_its_audience(client, admin_headers):
    """"They ticked condo, it's a triplex." A correction, and a common one."""
    request_id = await _submit(client)          # residential
    body = (await _patch(client, request_id, admin_headers,
                         {"property_type": "house"})).json()
    assert body["property_type"] == "house"
    assert body["audience"] == "residential"


async def test_the_audience_cannot_be_changed_through_the_property_type(
    client, admin_headers
):
    """THE AUDIENCE IS THE INVARIANT. The public form refuses a house filed as
    commercial; this has to stay true afterwards, or the request is priced by a
    half of the grid that never asked it any questions."""
    request_id = await _submit(client, COMMERCIAL)
    before = await _detail(client, request_id, admin_headers)
    response = await _patch(client, request_id, admin_headers, {
        "property_type": "house", "city": "Laval",
    })
    assert response.status_code == 422, response.text

    # And the whole patch is refused, not half-applied.
    after = await _detail(client, request_id, admin_headers)
    assert after["property_type"] == before["property_type"]
    assert after["audience"] == before["audience"]
    assert after["city"] == before["city"]


async def test_the_audience_itself_is_not_editable(client, admin_headers):
    request_id = await _submit(client, COMMERCIAL)
    before = await _detail(client, request_id, admin_headers)
    body = (await _patch(client, request_id, admin_headers,
                         {"audience": "residential", "city": "Laval"})).json()
    assert body["audience"] == before["audience"]
    assert body["city"] == "Laval", "the editable field in the same payload still saves"


async def test_what_was_asked_for_is_editable(client, admin_headers):
    """Frequency decides the recurring discount AND the period printed on the
    quote email. "Actually, make it monthly" could be corrected nowhere."""
    request_id = await _submit(client, COMMERCIAL)
    body = (await _patch(client, request_id, admin_headers, {
        "frequency": "monthly",
        "night_access": True,
        "services": ["office_cleaning", "common_areas"],
    })).json()
    assert body["frequency"] == "monthly"
    assert body["night_access"] is True
    assert sorted(body["services"]) == ["common_areas", "office_cleaning"]


async def test_the_language_of_the_quote_is_editable(client, admin_headers):
    """"Could you send that in English?" -- the offer email follows locale."""
    request_id = await _submit(client)
    body = (await _patch(client, request_id, admin_headers, {"locale": "en"})).json()
    assert body["locale"] == "en"


async def test_a_required_field_cannot_be_emptied(client, admin_headers):
    """An emptied text box means "clear this". An emptied dropdown means the
    browser sent nothing useful, and NULL in a NOT NULL column is an
    IntegrityError with a message nobody can act on."""
    request_id = await _submit(client)
    before = await _detail(client, request_id, admin_headers)
    for field in ("frequency", "locale", "property_type", "full_name"):
        response = await _patch(client, request_id, admin_headers, {field: ""})
        assert response.status_code == 422, (field, response.text)
    after = await _detail(client, request_id, admin_headers)
    assert after["frequency"] == before["frequency"]
    assert after["locale"] == before["locale"]


async def test_consent_is_not_editable(client, admin_headers):
    request_id = await _submit(client)
    before = await _detail(client, request_id, admin_headers)
    body = (await _patch(client, request_id, admin_headers, {"consent_given": False})).json()
    assert body["consent_given"] == before["consent_given"]


async def test_attribution_is_not_editable(client, admin_headers):
    """Captured once on arrival. A campaign you can rewrite afterwards is a campaign
    report you cannot trust."""
    request_id = await _submit(client)
    before = await _detail(client, request_id, admin_headers)
    body = (await _patch(client, request_id, admin_headers, {
        "utm_source": "inventé", "landing_path": "/ailleurs",
    })).json()
    assert body["utm_source"] == before["utm_source"]
    assert body["landing_path"] == before["landing_path"]


async def test_the_computed_price_survives_an_area_change(client, admin_headers):
    """What the visitor was shown is a record, not a live calculation. Editing the
    area afterwards must not rewrite what they were quoted online."""
    request_id = await _submit(client)
    before = await _detail(client, request_id, admin_headers)
    body = (await _patch(client, request_id, admin_headers, {"area_sqft": 3000})).json()
    assert body["area_sqft"] == 3000
    assert body["computed_total_cents"] == before["computed_total_cents"]
    assert body["computed_breakdown"] == before["computed_breakdown"]
