"""One process serves the API and the site.

Routes are registered in three layers, in this order:
  /healthz and /api/*   the API
  /<page>               a clean URL per HTML file in frontend/
  /                     everything else as static files
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.core.logging import configure_logging, logger
from app.routers import admin, health, quotes, rate_cards

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.environment)
    logger.info("api.start", environment=settings.environment)
    yield


app = FastAPI(
    title="Proline Cleaning Solutions",
    version="0.1.0",
    lifespan=lifespan,
    description="Quote capture, pricing and admin for Proline Cleaning Solutions, Montreal.",
)

@app.middleware("http")
async def cache_headers(request: Request, call_next):
    """What browsers may keep, and for how long.

    CODE AND MARKUP MUST NEVER DISAGREE. This used to give /js/ and /css/
    `max-age=3600`, and that hour was long enough to break a deploy: the HTML was
    `no-cache` and updated immediately, the JavaScript did not, so for up to an
    hour after every deploy a browser ran new markup against old code. It cost a
    real debugging session -- an admin page showing a renamed column header and
    the previous version's buttons, which looks like a deploy that half-worked
    and is nothing of the sort.

    So scripts and styles are `no-cache`, which does NOT mean "do not cache": the
    browser still stores them and still sends If-None-Match, and an unchanged
    file comes back as a 304 with no body. The cost is one conditional request
    per asset per page load. The benefit is that what a visitor runs always
    matches what they were served, which is worth far more than those requests.

    Images keep a real cache. They are the bytes worth saving, they are not
    versioned against anything, and a stale one is cosmetic rather than broken.
    """
    response = await call_next(request)
    path = request.url.path
    if path.startswith(("/css/", "/js/")):
        response.headers["Cache-Control"] = "no-cache"
    elif path.startswith("/img/"):
        response.headers["Cache-Control"] = (
            "no-cache" if settings.environment == "local" else "public, max-age=604800"
        )
    elif path.endswith(".html") or response.headers.get("content-type", "").startswith("text/html"):
        response.headers["Cache-Control"] = "no-cache"
    return response


app.include_router(health.router)
app.include_router(quotes.router, prefix="/api")
app.include_router(admin.public_router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(rate_cards.router, prefix="/api")


FRONTEND_DIR = Path(
    settings.frontend_dir
    or os.environ.get("FRONTEND_DIR")
    or Path(__file__).resolve().parent.parent.parent / "frontend"
)


def _register_page(url_path: str, file_path: Path) -> None:
    app.get(url_path, response_class=FileResponse, include_in_schema=False)(
        lambda p=file_path: FileResponse(p)
    )


if FRONTEND_DIR.is_dir():
    # A clean URL per page: /soumission -> frontend/soumission.html
    for page in FRONTEND_DIR.glob("*.html"):
        if page.stem != "index":
            _register_page(f"/{page.stem}", page)

    # English tree: /en/soumission -> frontend/en/soumission.html
    en_dir = FRONTEND_DIR / "en"
    if en_dir.is_dir():
        for page in en_dir.glob("*.html"):
            url = "/en" if page.stem == "index" else f"/en/{page.stem}"
            _register_page(url, page)

    # The admin screens, gated by the token their API calls carry. Globbed the
    # same way as the pages above rather than named one by one: the previous
    # version listed two explicitly, so the third screen added was a 404 with
    # nothing anywhere to explain why.
    admin_dir = FRONTEND_DIR / "admin"
    if admin_dir.is_dir():
        for page in admin_dir.glob("*.html"):
            url = "/admin" if page.stem == "index" else f"/admin/{page.stem}"
            _register_page(url, page)

    # Mounted last so it never shadows the routes above.
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
else:  # pragma: no cover - only in an API-only deployment
    logger.warning("frontend.missing", directory=str(FRONTEND_DIR))
