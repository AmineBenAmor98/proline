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


async def test_admin_page_is_not_indexed(client):
    page = (await client.get("/admin")).text
    assert "noindex" in page


async def test_french_and_english_pages_cross_link(client):
    fr = (await client.get("/")).text
    en = (await client.get("/en")).text
    assert 'href="/en"' in fr
    assert 'href="/"' in en
