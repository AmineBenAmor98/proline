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
    """In local dev an edited stylesheet must win over the browser cache; in
    production static assets are cached for an hour."""
    response = await call_next(request)
    path = request.url.path
    if path.startswith(("/css/", "/js/", "/img/")):
        response.headers["Cache-Control"] = (
            "no-cache" if settings.environment == "local" else "public, max-age=3600"
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
