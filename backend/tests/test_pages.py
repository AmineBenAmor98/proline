"""The site is served by the same app as the API. These tests fail loudly if a
page stops being reachable, which is the failure that quietly wastes ad budget."""

import pytest

PAGES = [
    "/", "/soumission", "/commercial",
    "/en", "/en/soumission", "/en/commercial",
    "/admin", "/admin/tarifs",
]


@pytest.mark.parametrize("path", PAGES)
async def test_page_is_served(client, path):
    response = await client.get(path)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


async def test_static_assets_are_served(client):
    for path in [
        "/css/app.css", "/js/quote.js",
        "/js/admin-common.js", "/js/admin.js", "/js/rates.js",
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
