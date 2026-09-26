"""Customer photos: the upload token, the limits, and who can read them back.

The token tests are the important ones. The upload endpoint is anonymous by
necessity -- the customer has no account -- so the signature is the only thing
between it and anybody who can guess a request id, which is not secret.
"""

import time

import pytest

from app.core.config import Settings, get_settings
from app.services import photos as photo_store
from tests.test_quotes_api import RESIDENTIAL

# No `pytestmark = pytest.mark.asyncio` here: pytest.ini already sets
# asyncio_mode = auto, and marking the module too applies the mark to the sync
# tests at the bottom as well, which pytest warns about.

# The smallest real files of each type, so magic-byte sniffing is exercised with
# actual signatures rather than something that merely starts with the right bytes.
PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001080600000"
    "01f15c4890000000a49444154789c6300010000050001"
    "0d0a2db40000000049454e44ae426082"
)
JPEG_HEAD = b"\xff\xd8\xff\xe0" + b"\x00" * 200
NOT_AN_IMAGE = b"<?php system($_GET['c']); ?>" + b"\x00" * 50


@pytest.fixture
def photos_dir(tmp_path, monkeypatch):
    """Point the app at a temporary photo store for one test.

    Overriding the dependency rather than the environment: get_settings is
    lru_cached, so a late environment change would be read by nothing.
    """
    from app.main import app

    base = get_settings()
    test_settings = Settings(
        **{**base.model_dump(), "photos_dir": str(tmp_path), "photo_max_count": 3}
    )
    app.dependency_overrides[get_settings] = lambda: test_settings
    yield tmp_path
    app.dependency_overrides.pop(get_settings, None)


async def _submit(client) -> tuple[str, str]:
    response = await client.post("/api/quotes", json=RESIDENTIAL)
    assert response.status_code == 201, response.text
    body = response.json()
    return body["id"], body["photo_upload_token"]


async def _upload(
    client, request_id, token, *, data=PNG_1PX, zone="kitchen", name="a.png", zone_label=None
):
    form = {"token": token, "zone": zone}
    if zone_label is not None:
        form["zone_label"] = zone_label
    return await client.post(
        f"/api/quotes/{request_id}/photos",
        data=form,
        files={"file": (name, data, "image/png")},
    )


async def _photos(client, request_id, admin_headers):
    detail = await client.get(f"/api/admin/requests/{request_id}", headers=admin_headers)
    assert detail.status_code == 200, detail.text
    return detail.json()["photos"]


# --------------------------------------------------------------------------
# The token
# --------------------------------------------------------------------------

async def test_submission_returns_an_upload_token(client, photos_dir):
    _, token = await _submit(client)
    assert token, "the browser has no way to upload without this"


async def test_no_token_when_storage_is_off(client):
    """PHOTOS_DIR empty is the off switch, and it has to be the whole switch."""
    response = await client.post("/api/quotes", json=RESIDENTIAL)
    assert response.json()["photo_upload_token"] is None


async def test_honeypot_gets_no_token(client, photos_dir):
    """A bot gets a cheerful 201 and no way to write anything to the disk."""
    response = await client.post("/api/quotes", json={**RESIDENTIAL, "website": "spam"})
    assert response.status_code == 201
    assert response.json()["photo_upload_token"] is None


async def test_token_for_another_request_is_refused(client, photos_dir):
    first_id, _ = await _submit(client)
    _, other_token = await _submit(client)
    response = await _upload(client, first_id, other_token)
    assert response.status_code == 403, "a token must name exactly one request"


async def test_forged_token_is_refused(client, photos_dir):
    request_id, token = await _submit(client)
    tampered = token.rsplit(".", 1)[0] + ".not-the-signature"
    assert (await _upload(client, request_id, tampered)).status_code == 403


async def test_expired_token_is_refused(client, photos_dir):
    request_id, _ = await _submit(client)
    stale = photo_store.make_upload_token(
        request_id, "test-secret", now=time.time() - photo_store.TOKEN_TTL_SECONDS - 10
    )
    response = await _upload(client, request_id, stale)
    assert response.status_code == 403
    assert "expir" in response.json()["detail"].lower()


# --------------------------------------------------------------------------
# What we will and will not store
# --------------------------------------------------------------------------

async def test_a_photo_is_stored_on_disk_and_in_the_row(client, photos_dir, admin_headers):
    request_id, token = await _submit(client)
    assert (await _upload(client, request_id, token)).status_code == 201

    on_disk = [p for p in photos_dir.rglob("*") if p.is_file()]
    assert len(on_disk) == 1
    assert on_disk[0].read_bytes() == PNG_1PX
    # Dated folders, not a flat dump.
    assert on_disk[0].parent.parent.parent == photos_dir

    detail = await client.get(f"/api/admin/requests/{request_id}", headers=admin_headers)
    assert detail.status_code == 200, detail.text
    photos = detail.json()["photos"]
    assert len(photos) == 1
    assert photos[0]["zone"] == "kitchen"
    assert photos[0]["zone_label_fr"] == "Cuisine"
    assert photos[0]["bytes_size"] == len(PNG_1PX)


async def test_jpeg_is_accepted(client, photos_dir):
    request_id, token = await _submit(client)
    response = await _upload(client, request_id, token, data=JPEG_HEAD, name="photo.jpg")
    assert response.status_code == 201


async def test_a_script_renamed_as_an_image_is_refused(client, photos_dir):
    """The declared content type is whatever the client felt like sending."""
    request_id, token = await _submit(client)
    response = await _upload(client, request_id, token, data=NOT_AN_IMAGE, name="x.png")
    assert response.status_code == 422
    assert not [p for p in photos_dir.rglob("*") if p.is_file()], "nothing may reach the disk"


async def test_oversize_is_refused(client, photos_dir):
    request_id, token = await _submit(client)
    huge = PNG_1PX + b"\x00" * (2 * 1024 * 1024 + 1)
    response = await _upload(client, request_id, token, data=huge)
    assert response.status_code == 413


async def test_empty_file_is_refused(client, photos_dir):
    request_id, token = await _submit(client)
    assert (await _upload(client, request_id, token, data=b"")).status_code == 422


async def test_the_count_limit_holds(client, photos_dir):
    """Three is the cap in this fixture; the fourth must not land."""
    request_id, token = await _submit(client)
    for _ in range(3):
        assert (await _upload(client, request_id, token)).status_code == 201
    response = await _upload(client, request_id, token)
    assert response.status_code == 409
    assert len([p for p in photos_dir.rglob("*") if p.is_file()]) == 3


# --------------------------------------------------------------------------
# The room the customer names themselves
# --------------------------------------------------------------------------

async def test_a_customer_named_room_is_kept(client, photos_dir, admin_headers):
    """"Autre" alone tells the person writing the quote nothing."""
    request_id, token = await _submit(client)
    assert (
        await _upload(client, request_id, token, zone="other", zone_label="Salle de lavage")
    ).status_code == 201

    photo = (await _photos(client, request_id, admin_headers))[0]
    assert photo["zone"] == "other"
    assert photo["zone_label_fr"] == "Salle de lavage"
    assert photo["customer_named"] is True


async def test_other_with_no_name_still_reads_as_autre(client, photos_dir, admin_headers):
    request_id, token = await _submit(client)
    assert (await _upload(client, request_id, token, zone="other")).status_code == 201
    photo = (await _photos(client, request_id, admin_headers))[0]
    assert photo["zone_label_fr"] == "Autre"
    assert photo["customer_named"] is False


async def test_a_name_on_a_known_room_is_dropped(client, photos_dir, admin_headers):
    """The enum is what the screen groups by; a second name beside it could only
    contradict it."""
    request_id, token = await _submit(client)
    assert (
        await _upload(client, request_id, token, zone="kitchen", zone_label="le garage")
    ).status_code == 201
    photo = (await _photos(client, request_id, admin_headers))[0]
    assert photo["zone_label_fr"] == "Cuisine"
    assert photo["customer_named"] is False


@pytest.mark.parametrize(
    "typed, stored",
    [
        ("  salle   de   lavage \n", "salle de lavage"),   # collapsed and trimmed
        ("ligne1\nligne2", "ligne1 ligne2"),                # no newline in a one-line field
        ("   ", None),                                      # whitespace is not a name
        ("\x00\x07", None),                                 # control characters are not either
        ("x" * 200, "x" * 60),                              # cut to the column's width
    ],
)
async def test_a_typed_name_is_bounded(client, photos_dir, admin_headers, typed, stored):
    """Anonymous free text that ends up on the operator's screen."""
    request_id, token = await _submit(client)
    assert (
        await _upload(client, request_id, token, zone="other", zone_label=typed)
    ).status_code == 201, "a bad name must never cost the photo"
    photo = (await _photos(client, request_id, admin_headers))[0]
    assert photo["zone_label_fr"] == (stored if stored else "Autre")
    assert photo["customer_named"] is bool(stored)


async def test_unknown_zone_is_refused(client, photos_dir):
    request_id, token = await _submit(client)
    response = await _upload(client, request_id, token, zone="ballroom")
    assert response.status_code == 422


async def test_upload_to_a_missing_request_is_404(client, photos_dir):
    ghost = "00000000-0000-4000-8000-000000000000"
    token = photo_store.make_upload_token(ghost, "test-secret")
    assert (await _upload(client, ghost, token)).status_code == 404


# --------------------------------------------------------------------------
# Reading them back
# --------------------------------------------------------------------------

async def test_photo_bytes_need_admin_auth(client, photos_dir, admin_headers):
    """These are pictures inside somebody's home. A URL must not be enough."""
    request_id, token = await _submit(client)
    await _upload(client, request_id, token)
    detail = await client.get(f"/api/admin/requests/{request_id}", headers=admin_headers)
    photo_id = detail.json()["photos"][0]["id"]

    assert (await client.get(f"/api/admin/photos/{photo_id}")).status_code == 401

    authorised = await client.get(f"/api/admin/photos/{photo_id}", headers=admin_headers)
    assert authorised.status_code == 200
    assert authorised.content == PNG_1PX
    assert authorised.headers["content-type"] == "image/png"
    assert "private" in authorised.headers.get("cache-control", "")


async def test_a_row_whose_file_vanished_is_410_not_500(client, photos_dir, admin_headers):
    request_id, token = await _submit(client)
    await _upload(client, request_id, token)
    detail = await client.get(f"/api/admin/requests/{request_id}", headers=admin_headers)
    photo_id = detail.json()["photos"][0]["id"]

    for path in photos_dir.rglob("*"):
        if path.is_file():
            path.unlink()

    response = await client.get(f"/api/admin/photos/{photo_id}", headers=admin_headers)
    assert response.status_code == 410


# --------------------------------------------------------------------------
# The pieces underneath
# --------------------------------------------------------------------------

def test_storage_keys_cannot_escape_the_root(tmp_path):
    """`storage_key` comes out of a database row, and a row is only as
    trustworthy as whatever wrote it."""
    with pytest.raises(photo_store.PhotoRejected):
        photo_store.resolve(str(tmp_path), "../../etc/passwd")


def test_zone_lists_suit_their_audience():
    from app.models.enums import ZONES_BY_AUDIENCE, PhotoZone

    residential = ZONES_BY_AUDIENCE["residential"]
    commercial = ZONES_BY_AUDIENCE["commercial"]
    assert PhotoZone.bedroom in residential and PhotoZone.bedroom not in commercial
    assert PhotoZone.workstations in commercial and PhotoZone.workstations not in residential
    assert PhotoZone.kitchen in residential and PhotoZone.kitchen in commercial
    # `other` is the escape hatch, so it goes last rather than tempting anyone.
    assert residential[-1] is PhotoZone.other and commercial[-1] is PhotoZone.other


async def test_form_config_offers_the_zones(client, photos_dir):
    body = (await client.get("/api/quotes/form-config")).json()
    assert body["photos_enabled"] is True
    assert body["photo_max_count"] == 3
    values = [zone["value"] for zone in body["photo_zones_residential"]]
    assert "bedroom" in values and "workstations" not in values
    assert body["photo_zones_residential"][0]["label_fr"] == "Cuisine"


async def test_form_config_hides_photos_when_storage_is_off(client):
    body = (await client.get("/api/quotes/form-config")).json()
    assert body["photos_enabled"] is False
    assert body["photo_max_count"] == 0
