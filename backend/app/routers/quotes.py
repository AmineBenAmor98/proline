from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.logging import logger
from app.db.session import get_session
from app.models.enums import Audience
from app.schemas.quote import PriceDraftIn, PriceOut, QuoteRequestIn, QuoteRequestOut
from app.services.notifications import notify_new_request
from app.services.quotes import compute_price, create_quote_request

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
    )


@router.post("/price", response_model=PriceOut)
async def price_draft(
    payload: PriceDraftIn,
    session: AsyncSession = Depends(get_session),
) -> PriceOut:
    """Live calculator. The rate grid never leaves the server."""
    breakdown, _ = await compute_price(session, payload)
    if breakdown is None:
        raise HTTPException(status_code=409, detail="no price available for this request yet")
    if payload.audience != Audience.residential:
        raise HTTPException(status_code=403, detail="commercial requests are quoted by a human")
    return PriceOut(**breakdown.as_dict())
