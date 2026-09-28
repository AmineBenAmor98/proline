"""The site is served by the same app as the API. These tests fail loudly if a
page stops being reachable, which is the failure that quietly wastes ad budget."""

import json
import pathlib
import re

import pytest

PAGES = [
    "/", "/soumission", "/commercial",
    "/en", "/en/soumission", "/en/commercial",
    "/confidentialite", "/conditions", "/en/privacy", "/en/terms",
    "/admin", "/admin/tarifs", "/admin/demande",
]

FRONTEND = pathlib.Path(__file__).resolve().parent.parent.parent / "frontend"


@pytest.mark.parametrize("path", PAGES)
async def test_page_is_served(client, path):
    response = await client.get(path)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


async def test_static_assets_are_served(client):
    for path in [
        "/css/app.css", "/js/quote.js",
        "/js/admin-common.js", "/js/admin.js", "/js/rates.js",
        "/js/photos.js", "/js/demande.js", "/js/home.js",
    ]:
        response = await client.get(path)
        assert response.status_code == 200, path


async def test_health(client):
    response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_quote_form_posts_to_the_real_endpoint(client):
    page = (await client.get("/soumission")).text
    assert 'src="/js/quote.js"' in page
    script = (await client.get("/js/quote.js")).text
    assert "/api/quotes/price" in script
    assert "/api/quotes" in script


async def test_admin_pages_are_not_indexed_and_carry_no_data(client):
    """The sign-in form is injected by admin-common.js, so it is not in the served
    HTML. What must hold is that neither admin page is indexable and neither ships
    a customer's details to an unauthenticated reader."""
    for path in ("/admin", "/admin/tarifs"):
        page = (await client.get(path)).text
        assert "noindex" in page, path
        assert "/js/admin-common.js" in page, path
        assert "@" not in page.split("<body")[1], path


async def test_french_and_english_pages_cross_link(client):
    fr = (await client.get("/")).text
    en = (await client.get("/en")).text
    assert 'href="/en"' in fr
    assert 'href="/"' in en


def test_the_english_tree_is_in_sync_and_carries_no_french():
    """`frontend/build_en.py` is the only thing keeping the two language trees
    together, and it used to fail quietly.

    Four defects shipped because a short map entry replaced the tail of a longer
    one before the longer one ran: a "Back à l'accueil" button on the English
    success page, a half-French meta description on the English home page, a
    "Floor stripping and waxing de planchers" service name in the structured
    data, and two French alt texts on the hero images. The map is applied longest
    source first now, and this is the guard.

    It also fails when someone edits a French page and forgets to rebuild, which
    is the other half of the drift.
    """
    import importlib.util
    from pathlib import Path

    from app.main import FRONTEND_DIR

    root = Path(FRONTEND_DIR)
    spec = importlib.util.spec_from_file_location("build_en", root / "build_en.py")
    build_en = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build_en)

    for name in build_en.PAGES:
        english = build_en.translate((root / name).read_text(encoding="utf-8"))

        left = build_en.leftovers(english)
        assert not left, f"French left in en/{name}: {', '.join(left)}"

        committed = (root / "en" / name).read_text(encoding="utf-8")
        assert english == committed, (
            f"en/{name} is stale -- run `python frontend/build_en.py`"
        )

    dead = [src for src, _ in build_en.TEXT if src not in build_en.USED]
    assert not dead, f"map entries matching nothing: {dead}"


# --------------------------------------------------------------------------
# Nothing on a public page may be a placeholder or a dead link
# --------------------------------------------------------------------------

PUBLIC = ["/", "/commercial", "/soumission",
          "/en", "/en/commercial", "/en/soumission",
          "/confidentialite", "/conditions", "/en/privacy", "/en/terms"]

# `[PRIX] $`, `[NOMBRE] avis Google`, `[Confidentialité]`, a mailto whose text was
# the address wrapped in brackets -- all of them reached the live site. A human
# reading the page is supposed to catch this and did not, four times over.
PLACEHOLDER = re.compile(r"\[[A-Za-z\u00c0-\u00ff@][^\]\n]{2,}\]")


@pytest.mark.parametrize("path", PUBLIC)
async def test_no_placeholder_survives(client, path):
    page = (await client.get(path)).text
    # The JSON-LD block is legitimately full of brackets.
    page = re.sub(r"<script[^>]*application/ld\+json.*?</script>", "", page, flags=re.S)
    found = PLACEHOLDER.findall(page)
    assert not found, f"{path} still shows {found}"


@pytest.mark.parametrize("path", PUBLIC)
async def test_every_internal_link_resolves(client, path):
    """A link to a page that does not exist, or to an anchor no element carries.

    The footer pointed "Décapage et cirage" at `/#services` and the English side
    pointed at a French anchor id. Both render perfectly and both go nowhere near
    what they name.
    """
    page = (await client.get(path)).text
    broken = []
    for href in set(re.findall(r'href="([^"]+)"', page)):
        if href.startswith(("http", "mailto:", "tel:", "#")) and not href.startswith("#"):
            continue
        if href.startswith("#"):
            target, url = href[1:], path
        else:
            url, _, target = href.partition("#")
            url = url or path
        if url.startswith(("http", "mailto:", "tel:")):
            continue
        response = await client.get(url)
        if response.status_code != 200:
            broken.append(f"{href} -> {response.status_code}")
            continue
        if target and f'id="{target}"' not in response.text:
            broken.append(f"{href} -> no element with id={target}")
    assert not broken, f"{path}: {broken}"


async def test_the_home_page_example_is_a_payload_the_api_accepts(client):
    """The preview panel prices a real home through /api/quotes/price.

    A typo in that payload would not break the page -- the fetch would simply fail
    and the panel would keep its no-number wording forever, which looks exactly
    like "no rate card yet". This is the only thing that would notice.
    """
    script = (FRONTEND / "js" / "home.js").read_text()
    body = re.search(r"var EXAMPLE = (\{.*?\n  \});", script, re.S)
    assert body, "EXAMPLE went missing from home.js"
    payload = json.loads(re.sub(r"(\w+):", r'"\1":', body.group(1)).replace("'", '"'))

    response = await client.post("/api/quotes/price", json=payload)
    # 200 with a card that prices it, 409 with one that does not. 403 would mean
    # the example stopped being residential and 422 that it stopped being valid --
    # both are permanent silent failures of the panel.
    assert response.status_code in (200, 409), response.text


async def test_the_preview_chips_and_the_priced_example_agree(client):
    """A panel captioned "1 100 pi2" that prices 1,400 is worse than no panel."""
    script = (FRONTEND / "js" / "home.js").read_text()
    assert '"area_sqft": 1100' in script or "area_sqft: 1100" in script
    for page, chip in [("/", "1\u202f100 pi²"), ("/en", "1,100 sq ft")]:
        text = (await client.get(page)).text
        assert chip in text or chip.replace("\u202f", " ") in text, (page, chip)


def test_the_admin_stylesheet_does_not_reach_into_the_public_site():
    """`.card` was defined twice in one stylesheet -- once for the marketing pages
    and again, hundreds of lines later, for the admin. The admin copy won the
    specificity tie by source order and quietly re-padded every card on the public
    site.

    Scoping it fixed that and broke something else: `.card-action`, a bare single
    class, then lost the tie to `.admin-body .card` and the decision box rendered
    as pale text on white. Both failures are invisible to every other test here,
    so the rule is checked directly: the admin's card rules are scoped, and
    anything overriding them carries the same two classes.
    """
    css = (FRONTEND / "css" / "app.css").read_text()
    assert "\n.admin-body .card {" in css, "the admin card rule must stay scoped"
    assert "\n.card {" in css, "the public site keeps its own unscoped .card"
    assert "\n.card-action {" not in css, (
        ".card-action must be .admin-body .card-action, or .admin-body .card outranks it"
    )


def test_the_admin_label_tables_match_the_enums():
    """admin-common.js keeps client-side copies of the enums -- labels, and which
    property types belong to which audience. A copy that drifts from the original
    shows the operator a dropdown whose options the API then refuses, which reads
    as a broken save rather than as a stale table.
    """
    import json as _json

    from app.models.enums import (
        AUDIENCE_BY_PROPERTY_TYPE,
        Frequency,
        PropertyType,
        RequestStatus,
        ServiceCode,
    )

    js = (FRONTEND / "js" / "admin-common.js").read_text()

    def table(name: str) -> dict:
        """The object literal assigned to `var <name> = {...};`."""
        start = js.index(f"var {name} = {{") + len(f"var {name} = ")
        depth, i = 0, start
        while True:
            if js[i] == "{":
                depth += 1
            elif js[i] == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        body = js[start:i + 1]
        # JS object literal -> JSON: quote the bare keys.
        return _json.loads(re.sub(r"(\w+):", r'"\1":', body).replace("'", '"'))

    def array(name: str) -> list:
        start = js.index(f"var {name} = [") + len(f"var {name} = ")
        end = js.index("]", start) + 1
        return _json.loads(js[start:end].replace("'", '"'))

    assert set(table("PROPERTY_LABELS")) == {p.value for p in PropertyType}
    assert set(table("FREQUENCY_LABELS")) == {f.value for f in Frequency}
    assert set(table("SERVICE_LABELS")) == {s.value for s in ServiceCode}
    assert set(array("FREQUENCY_ORDER")) == {f.value for f in Frequency}
    assert set(array("STATUS_ORDER")) == {s.value for s in RequestStatus}

    by_audience = table("PROPERTY_TYPES_BY_AUDIENCE")
    expected: dict[str, set[str]] = {}
    for kind, audience in AUDIENCE_BY_PROPERTY_TYPE.items():
        expected.setdefault(audience.value, set()).add(kind.value)
    assert {k: set(v) for k, v in by_audience.items()} == expected
