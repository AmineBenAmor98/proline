import datetime as dt

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.logging import logger
from app.db.session import get_session
from app.models.enums import (
    PHOTO_ZONE_LABELS_EN,
    PHOTO_ZONE_LABELS_FR,
    ZONES_BY_AUDIENCE,
    Audience,
    PhotoZone,
)
from app.models.quote_photo import QuotePhoto
from app.models.quote_request import QuoteRequest
from app.schemas.quote import (
    ExtraOffer,
    FormConfig,
    ModifierOffer,
    ModifierOptionOut,
    PhotoZoneOffer,
    PriceDraftIn,
    PriceOut,
    QuoteRequestIn,
    QuoteRequestOut,
)
from app.services import photos as photo_store
from app.services.notifications import notify_new_request
from app.services.quotes import compute_price, create_quote_request
from app.services.rate_cards import get_active_rate_card

router = APIRouter(prefix="/quotes", tags=["quotes"])

THANKS_FR_FIRM = "Votre prix est confirmé. Nous vous contactons pour fixer la date."
THANKS_FR_REVIEW = "Merci. Votre soumission écrite vous parvient sous 24 h."
THANKS_EN_FIRM = "Your price is confirmed. We will contact you to schedule."
THANKS_EN_REVIEW = "Thank you. Your written quote will arrive within 24 hours."


@router.post("", response_model=QuoteRequestOut, status_code=status.HTTP_201_CREATED)
async def submit_quote_request(
    payload: QuoteRequestIn,
    background: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> QuoteRequestOut:
    if payload.website:
        # Honeypot filled: a bot. Answer 201 so it learns nothing, save nothing.
        logger.info("quote.honeypot")
        return QuoteRequestOut(
            id="00000000-0000-0000-0000-000000000000",
            status="new",
            audience=payload.audience,
            price=None,
            message_fr=THANKS_FR_REVIEW,
            message_en=THANKS_EN_REVIEW,
        )

    if not payload.contact.consent_given:
        raise HTTPException(status_code=422, detail="consent is required to answer the request")

    request, breakdown = await create_quote_request(session, payload)

    summary = (
        f"{payload.audience.value} · {payload.property.property_type.value} · "
        f"{payload.property.area_sqft or '?'} pi² · {payload.frequency.value} · "
        f"{payload.contact.full_name} · {payload.contact.phone or payload.contact.email}"
    )
    background.add_task(notify_new_request, settings, request_id=str(request.id), summary=summary)

    show_price = breakdown is not None and payload.audience == Audience.residential
    return QuoteRequestOut(
        id=str(request.id),
        status=request.status,
        audience=request.audience,
        price=PriceOut(**breakdown.as_dict()) if show_price else None,
        message_fr=THANKS_FR_FIRM if show_price else THANKS_FR_REVIEW,
        message_en=THANKS_EN_FIRM if show_price else THANKS_EN_REVIEW,
        # Handed out only now, once the lead is committed. The browser uploads
        # photos against it AFTER this response lands, so a failed or abandoned
        # upload costs the photos and never the lead.
        photo_upload_token=(
            photo_store.make_upload_token(str(request.id), settings.secret_key)
            if settings.photos_dir
            else None
        ),
    )


@router.post("/{request_id}/photos", status_code=status.HTTP_201_CREATED)
async def upload_photo(
    request_id: str,
    token: str = Form(...),
    zone: str = Form(...),
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    """Attach one photo to an existing request.

    One photo per call rather than a batch: a batch is all-or-nothing over a
    connection that may not survive it, and four photos where the third failed
    is a better outcome than nothing. It also means the browser can show real
    progress instead of a spinner.

    Deliberately NOT behind admin auth -- the customer is anonymous. The signed
    token is what stands in for a session: it names one request, it expires, and
    it cannot be forged without SECRET_KEY.
    """
    if not settings.photos_dir:
        raise HTTPException(status_code=503, detail="L'envoi de photos est désactivé.")

    try:
        photo_store.check_upload_token(token, request_id, settings.secret_key)
    except photo_store.PhotoRejected as exc:
        # 403, not 404: the token is the thing that failed, and saying so lets
        # the browser stop retrying instead of hammering a lost cause.
        raise HTTPException(status_code=403, detail=str(exc)) from None

    try:
        zone_value = PhotoZone(zone)
    except ValueError:
        raise HTTPException(status_code=422, detail="Pièce inconnue.") from None

    request = await session.get(QuoteRequest, request_id)
    if request is None:
        raise HTTPException(status_code=404, detail="Demande introuvable.")

    existing = await session.scalar(
        select(func.count(QuotePhoto.id)).where(QuotePhoto.request_id == request.id)
    )
    if (existing or 0) >= settings.photo_max_count:
        raise HTTPException(
            status_code=409,
            detail=f"Maximum {settings.photo_max_count} photos par demande.",
        )

    # Read with a cap rather than trusting Content-Length, which is whatever the
    # client wrote in the header. One byte over tells us it is over without
    # holding the whole thing.
    data = await file.read(settings.photo_max_bytes + 1)
    if len(data) > settings.photo_max_bytes:
        mb = settings.photo_max_bytes // (1024 * 1024)
        raise HTTPException(status_code=413, detail=f"Photo trop lourde (max {mb} Mo).")
    if not data:
        raise HTTPException(status_code=422, detail="Fichier vide.")

    try:
        extension = photo_store.sniff_extension(data[:16])
        key = photo_store.storage_key(extension, today=dt.date.today().strftime("%Y/%m"))
        photo_store.write(settings.photos_dir, key, data)
    except photo_store.PhotoRejected as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None

    session.add(
        QuotePhoto(
            request_id=request.id,
            zone=zone_value,
            storage_key=key,
            bytes_size=len(data),
        )
    )
    await session.commit()
    logger.info("photo.stored", request_id=str(request.id), zone=zone_value.value, bytes=len(data))
    return {"status": "stored", "zone": zone_value.value}


def _zone_offers(audience: str) -> list[PhotoZoneOffer]:
    return [
        PhotoZoneOffer(
            value=zone.value,
            label_fr=PHOTO_ZONE_LABELS_FR[zone],
            label_en=PHOTO_ZONE_LABELS_EN[zone],
        )
        for zone in ZONES_BY_AUDIENCE[audience]
    ]


@router.get("/form-config", response_model=FormConfig)
async def form_config(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> FormConfig:
    """What the quote form may ask, derived from the active rate card.

    Public on purpose: it contains prices the visitor is about to be shown
    anyway, and nothing about how they are combined.
    """
    card = await get_active_rate_card(session)
    if card is None:
        raise HTTPException(status_code=503, detail="no active rate card")

    grid = card.grid or {}
    offers = []
    for code, spec in sorted((grid.get("extras") or {}).items()):
        if isinstance(spec, int):  # a card written before units existed
            spec = {"unit": "flat", "cents": spec, "label_fr": code, "label_en": code}
        if not spec.get("cents"):
            continue
        offers.append(
            ExtraOffer(
                code=code,
                unit=spec.get("unit", "flat"),
                label_fr=spec.get("label_fr", code),
                label_en=spec.get("label_en", code),
                per_fr=spec.get("per_fr", ""),
                per_en=spec.get("per_en", ""),
                cents=int(spec["cents"]),
            )
        )

    # Only the questions the card can actually price. A modifier whose every
    # answer is free is not asked, for the same reason an extra with no price is
    # not offered: the form asks only what the active card can price.
    questions = []
    modifiers_raw = (grid.get("residential_modifiers") or {}).items()
    for code, spec in sorted(modifiers_raw, key=lambda pair: (pair[1].get("sort", 100), pair[0])):
        options = spec.get("options") or []
        prices_anything = any(
            str(option.get("multiplier", "1")) not in ("1", "1.0") or option.get("cents")
            for option in options
        )
        if len(options) < 2 or not prices_anything:
            continue
        questions.append(
            ModifierOffer(
                code=code,
                label_fr=spec.get("label_fr", code),
                label_en=spec.get("label_en", code),
                help_fr=spec.get("help_fr", ""),
                help_en=spec.get("help_en", ""),
                options=[
                    ModifierOptionOut(
                        value=option.get("value", ""),
                        label_fr=option.get("label_fr", ""),
                        label_en=option.get("label_en", ""),
                    )
                    for option in options
                ],
            )
        )

    return FormConfig(
        rate_card_version=card.version,
        residential_online_pricing=card.residential_online_pricing,
        extras=offers,
        modifiers=questions,
        residential_cells=sorted(
            code for code, cents in (grid.get("residential_base_cents") or {}).items() if cents
        ),
        photos_enabled=bool(settings.photos_dir),
        photo_max_count=settings.photo_max_count if settings.photos_dir else 0,
        photo_zones_residential=_zone_offers("residential"),
        photo_zones_commercial=_zone_offers("commercial"),
    )


@router.post("/price", response_model=PriceOut)
async def price_draft(
    payload: PriceDraftIn,
    session: AsyncSession = Depends(get_session),
) -> PriceOut:
    """Live calculator. The rate grid never leaves the server."""
    # Checked first. Pricing a commercial draft and then refusing to return it
    # did a database read and a full pricing pass for nothing, and a commercial
    # draft that happened not to price came back 409 instead of 403 -- the wrong
    # reason, because the real one is that we never show this number.
    if payload.audience != Audience.residential:
        raise HTTPException(status_code=403, detail="commercial requests are quoted by a human")
    breakdown, _ = await compute_price(session, payload)
    if breakdown is None:
        raise HTTPException(status_code=409, detail="no price available for this request yet")
    return PriceOut(**breakdown.as_dict())
