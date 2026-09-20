"""The site is served by the same app as the API. These tests fail loudly if a
page stops being reachable, which is the failure that quietly wastes ad budget."""

import pytest

PAGES = ["/", "/soumission", "/commercial", "/en", "/en/soumission", "/en/commercial", "/admin"]


@pytest.mark.parametrize("path", PAGES)
async def test_page_is_served(client, path):
    response = await client.get(path)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


async def test_static_assets_are_served(client):
    for path in ["/css/app.css", "/js/quote.js", "/js/admin.js"]:
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
