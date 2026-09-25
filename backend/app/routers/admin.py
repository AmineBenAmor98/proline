"""The requests half of the admin API: sign in, list, adjust a price, set a status.

The rate card half lives in `app/routers/rate_cards.py` under the same /admin
prefix and the same token.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.security import (
    TOKEN_TTL_SECONDS,
    check_credentials,
    create_token,
    require_admin,
)
from app.db.session import get_session
from app.models import Lead, OfferEmail, Property, Quote, QuoteRequest
from app.models.enums import RequestStatus
from app.schemas.admin import (
    AdminRequestList,
    AdminRequestPatch,
    AdminRequestRow,
    LoginIn,
    LoginOut,
    OfferIn,
    OfferPreview,
    OfferSent,
    RequestedItem,
)
from app.services import offers
from app.services.mailer import MailNotConfigured
from app.services.rate_cards import get_active_rate_card

# Sign-in is public; everything else needs the token it returns.
public_router = APIRouter(prefix="/admin", tags=["admin"])
router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@public_router.post("/login", response_model=LoginOut)
async def login(payload: LoginIn, settings: Settings = Depends(get_settings)) -> LoginOut:
    if not check_credentials(payload.username, payload.password, settings):
        raise HTTPException(status_code=401, detail="identifiants invalides")
    return LoginOut(
        token=create_token(payload.username.strip(), settings),
        username=payload.username.strip(),
        expires_in=TOKEN_TTL_SECONDS,
    )


@router.get("/me")
async def me(username: str = Depends(require_admin)) -> dict[str, str]:
    """Lets the panel check a stored token before showing anything."""
    return {"username": username}


def _extras(request: QuoteRequest, card_extras: dict) -> list[RequestedItem]:
    """The extras asked for, named.

    The breakdown stored on the request is preferred: it holds the exact words
    and quantities the visitor was quoted. A request nobody priced -- every
    commercial one -- falls back to the active card, and finally to the code, so
    an extra retired from the card still reads as something.
    """
    priced = {}
    for line in ((request.computed_breakdown or {}).get("lines") or []):
        code = str(line.get("code", ""))
        if code.startswith("extra:"):
            priced[code[6:]] = line

    out: list[RequestedItem] = []
    for code, quantity in sorted((request.extras or {}).items()):
        line = priced.get(code)
        spec = card_extras.get(code) or {}
        if not isinstance(spec, dict):  # a card written before units existed
            spec = {}
        label = (line or {}).get("label_fr") or spec.get("label_fr") or code
        unit = (line or {}).get("unit_fr") or spec.get("per_fr") or ""
        shown = (line or {}).get("quantity")
        if shown is None and spec.get("unit") == "each":
            shown = quantity
        out.append(RequestedItem(code=code, label=label, quantity=shown, unit=unit))
    return out


def _modifiers(request: QuoteRequest, card_modifiers: dict) -> list[RequestedItem]:
    """The answers, named. Resolved from the active card, because unlike an extra
    a modifier has no line of its own in the breakdown when it is a multiplier --
    those are combined into one. The code and the answer are the request's own."""
    out: list[RequestedItem] = []
    chosen = request.modifiers or {}
    ordered = sorted(
        ((code, spec) for code, spec in (card_modifiers or {}).items() if code in chosen),
        key=lambda pair: (pair[1].get("sort", 100), pair[0]),
    )
    for code, spec in ordered:
        option = next(
            (o for o in spec.get("options", []) if o.get("value") == chosen.get(code)), None
        )
        if option is None or (
            str(option.get("multiplier", "1")) in ("1", "1.0") and not option.get("cents")
        ):
            continue  # the free answer: nothing happened, nothing to report
        name = spec.get("short_fr") or spec.get("label_fr") or code
        out.append(RequestedItem(code=code, label=f"{name} : {option.get('label_fr', '')}"))

    # An answer the active card no longer defines still happened.
    for code, value in sorted(chosen.items()):
        if code not in (card_modifiers or {}):
            out.append(RequestedItem(code=code, label=f"{code} : {value}"))
    return out


def _row(
    request: QuoteRequest,
    lead: Lead,
    prop: Property,
    quoted: int | None,
    card_extras: dict | None = None,
    card_modifiers: dict | None = None,
) -> AdminRequestRow:
    return AdminRequestRow(
        id=str(request.id),
        created_at=request.created_at,
        status=request.status,
        audience=request.audience,
        frequency=request.frequency,
        full_name=lead.full_name,
        company=lead.company,
        email=lead.email,
        phone=lead.phone,
        locale=lead.locale,
        property_type=prop.property_type.value,
        area_sqft=prop.area_sqft,
        bedrooms=prop.bedrooms,
        bathrooms=prop.bathrooms,
        restrooms=prop.restrooms,
        floors=prop.floors,
        address_line=prop.address_line,
        postal_code=prop.postal_code,
        city=prop.city,
        borough=prop.borough,
        access_notes=request.access_notes,
        desired_start=request.desired_start,
        preferred_contact=lead.preferred_contact,
        night_access=request.night_access,
        services=list(request.services or []),
        extras=_extras(request, card_extras or {}),
        modifiers=_modifiers(request, card_modifiers or {}),
        computed_total_cents=request.computed_total_cents,
        quoted_total_cents=quoted,
        utm_campaign=lead.utm_campaign,
        gclid=lead.gclid,
    )


@router.get("/requests", response_model=AdminRequestList)
async def list_requests(
    status_filter: RequestStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> AdminRequestList:
    stmt = (
        select(QuoteRequest, Lead, Property, Quote.total_cents)
        .join(Lead, Lead.id == QuoteRequest.lead_id)
        .join(Property, Property.id == QuoteRequest.property_id)
        .outerjoin(Quote, Quote.request_id == QuoteRequest.id)
        .order_by(QuoteRequest.created_at.desc())
        .limit(limit)
    )
    if status_filter:
        stmt = stmt.where(QuoteRequest.status == status_filter)

    rows = (await session.execute(stmt)).all()

    counts = dict(
        (
            await session.execute(
                select(QuoteRequest.status, func.count()).group_by(QuoteRequest.status)
            )
        ).all()
    )
    total = sum(counts.values())

    # One card read for the whole page, so naming an extra costs no query per row.
    active = await get_active_rate_card(session)
    grid = (active.grid or {}) if active else {}
    card_extras = grid.get("extras", {})
    card_modifiers = grid.get("residential_modifiers", {})

    return AdminRequestList(
        items=[
            _row(request, lead, prop, quoted, card_extras, card_modifiers)
            for request, lead, prop, quoted in rows
        ],
        total=total,
        counts_by_status={status.value: count for status, count in counts.items()},
    )


async def _request_with_people(session: AsyncSession, request_id: UUID):
    """The request with the lead and property it belongs to, or a 404.

    Every route below needs all three, and each of them 404s the same way, so
    the join lives here once. Three copies is how one of them ends up returning
    a 500 on a deleted request.
    """
    found = (
        await session.execute(
            select(QuoteRequest, Lead, Property)
            .join(Lead, Lead.id == QuoteRequest.lead_id)
            .join(Property, Property.id == QuoteRequest.property_id)
            .where(QuoteRequest.id == request_id)
        )
    ).first()
    if found is None:
        raise HTTPException(status_code=404, detail="request not found")
    return found


@router.patch("/requests/{request_id}", response_model=AdminRequestRow)
async def update_request(
    # Typed as a UUID so a malformed id is a 422 from FastAPI. As a plain str it
    # reached asyncpg's UUID codec and came back as an unhandled 500.
    request_id: UUID,
    payload: AdminRequestPatch,
    session: AsyncSession = Depends(get_session),
) -> AdminRequestRow:
    request, lead, prop = await _request_with_people(session, request_id)

    if payload.status:
        request.status = payload.status

    quote = (
        await session.execute(select(Quote).where(Quote.request_id == request.id))
    ).scalars().first()

    # Notes used to be read only inside the price branch, so
    # PATCH {"notes": "rappelle lundi"} answered 200 and wrote nothing.
    if payload.quoted_total_cents is not None or payload.notes is not None:
        if quote is None:
            quote = Quote(
                request_id=request.id,
                rate_card_id=request.rate_card_id,
                total_cents=payload.quoted_total_cents or 0,
                notes=payload.notes,
            )
            session.add(quote)
        else:
            if payload.quoted_total_cents is not None:
                quote.total_cents = payload.quoted_total_cents
            if payload.notes is not None:
                quote.notes = payload.notes

    # Sending a price is what moves a request out of the inbox. Only from `new`:
    # correcting the number on a request already won must not walk it backwards.
    if payload.quoted_total_cents is not None and request.status is RequestStatus.new:
        request.status = RequestStatus.quoted

    await session.commit()
    await session.refresh(request)

    active = await get_active_rate_card(session)
    grid = (active.grid or {}) if active else {}
    return _row(
        request, lead, prop, quote.total_cents if quote else None,
        grid.get("extras", {}), grid.get("residential_modifiers", {}),
    )


@router.post("/requests/{request_id}/offer/preview", response_model=OfferPreview)
async def preview_offer(
    request_id: UUID,
    payload: OfferIn,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    username: str = Depends(require_admin),
) -> OfferPreview:
    """Render without sending.

    Separate from the send on purpose. An offer email is irreversible and goes
    to a stranger deciding whether to trust this company with their keys, so the
    exact text is shown first -- rendered by the same function that will send
    it, not by a lookalike in the browser that can drift from it.
    """
    _request, lead, prop = await _request_with_people(session, request_id)
    subject, text = offers.render(
        settings, lead=lead, prop=prop,
        message=payload.message, total_cents=payload.total_cents,
    )
    return OfferPreview(subject=subject, text=text, to_email=lead.email)


@router.post("/requests/{request_id}/offer", response_model=OfferSent)
async def send_offer(
    request_id: UUID,
    payload: OfferIn,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    username: str = Depends(require_admin),
) -> OfferSent:
    """Send the offer, record it, and move the request out of the inbox."""
    request, lead, prop = await _request_with_people(session, request_id)

    if not lead.email:
        raise HTTPException(
            status_code=422,
            detail="cette demande n'a pas d'adresse courriel : répondez par téléphone",
        )

    try:
        record = await offers.send_offer(
            settings, session,
            lead=lead, prop=prop, request=request,
            message=payload.message, total_cents=payload.total_cents,
        )
    except MailNotConfigured:
        # The failed OfferEmail row is rolled back with the request: nothing was
        # attempted, so recording an attempt would be a lie.
        await session.rollback()
        raise HTTPException(
            status_code=503,
            detail="L'envoi de courriels n'est pas configuré (SMTP_HOST). "
                   "Aucun courriel n'a été envoyé.",
        ) from None
    except Exception as exc:
        # The provider refused it. The row IS kept -- that attempt happened and
        # is worth having -- so this commits before answering.
        await session.commit()
        raise HTTPException(
            status_code=502,
            detail=f"Le fournisseur a refusé l'envoi : {exc}. Rien n'a été livré.",
        ) from None

    # The price that was actually promised, on the quote row the rest of the
    # admin reads.
    quote = (
        await session.execute(select(Quote).where(Quote.request_id == request.id))
    ).scalars().first()
    if quote is None:
        quote = Quote(
            request_id=request.id,
            rate_card_id=request.rate_card_id,
            total_cents=payload.total_cents,
        )
        session.add(quote)
    else:
        quote.total_cents = payload.total_cents
    quote.sent_at = record.sent_at

    # Same rule as setting a price by hand: only out of `new`, so re-sending to
    # a client already won does not walk the status backwards.
    if request.status is RequestStatus.new:
        request.status = RequestStatus.quoted

    await session.commit()
    return OfferSent(
        id=record.id, to_email=record.to_email, subject=record.subject,
        total_cents=record.total_cents, status=record.status,
        sent_at=record.sent_at, error=record.error,
    )


@router.get("/requests/{request_id}/offers", response_model=list[OfferSent])
async def list_offers(
    request_id: UUID,
    session: AsyncSession = Depends(get_session),
    username: str = Depends(require_admin),
) -> list[OfferSent]:
    """Everything sent for this request, newest first — including failures."""
    rows = (
        await session.execute(
            select(OfferEmail)
            .where(OfferEmail.request_id == request_id)
            .order_by(OfferEmail.created_at.desc())
        )
    ).scalars().all()
    return [
        OfferSent(
            id=r.id, to_email=r.to_email, subject=r.subject,
            total_cents=r.total_cents, status=r.status,
            sent_at=r.sent_at, error=r.error,
        )
        for r in rows
    ]
