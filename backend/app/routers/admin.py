"""The requests half of the admin API: sign in, list, adjust a price, set a status.

The rate card half lives in `app/routers/rate_cards.py` under the same /admin
prefix and the same token.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.logging import logger
from app.core.security import (
    TOKEN_TTL_SECONDS,
    check_credentials,
    create_token,
    require_admin,
)
from app.db.session import get_session
from app.models import Lead, OfferEmail, Property, Quote, QuotePhoto, QuoteRequest
from app.models.enums import (
    AUDIENCE_BY_PROPERTY_TYPE,
    PHOTO_ZONE_LABELS_FR,
    RequestStatus,
)
from app.schemas.admin import (
    AdminCustomerPatch,
    AdminPhoto,
    AdminRequestDetail,
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
from app.services import photos as photo_store
from app.services.mailer import MailNotConfigured
from app.services.rate_cards import get_active_rate_card

# What we serve each stored extension as. Derived from the magic bytes we
# sniffed at upload, never from the name the customer's browser sent -- serving
# a file as a type it is not is how a stored image becomes a stored script.
MEDIA_TYPES = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}

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
    for line in (request.computed_breakdown or {}).get("lines") or []:
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


async def _detail(session: AsyncSession, request_id: UUID) -> AdminRequestDetail:
    """Everything known about one request, for the detail page.

    One call, not five. The page shows photos, contact, property, pricing and
    the offers already sent together, and five round-trips to paint one screen
    is five chances for a partly-rendered page.

    A function rather than only a route, because the customer PATCH below answers
    with the same shape: the page then re-renders itself from one response instead
    of patching its own DOM from what it hopes was saved.
    """
    request, lead, prop = await _request_with_people(session, request_id)

    active = await get_active_rate_card(session)
    grid = (active.grid or {}) if active else {}
    quoted = await session.scalar(select(Quote.total_cents).where(Quote.request_id == request.id))

    photos = (
        (
            await session.execute(
                select(QuotePhoto)
                .where(QuotePhoto.request_id == request.id)
                # Grouped by room, then oldest first, so the same property always
                # reads in the same order however the customer happened to pick.
                .order_by(QuotePhoto.zone, QuotePhoto.created_at)
            )
        )
        .scalars()
        .all()
    )

    offers = (
        (
            await session.execute(
                select(OfferEmail)
                .where(OfferEmail.request_id == request.id)
                .order_by(OfferEmail.created_at.desc())
            )
        )
        .scalars()
        .all()
    )

    row = _row(
        request, lead, prop, quoted, grid.get("extras", {}), grid.get("residential_modifiers", {})
    )

    return AdminRequestDetail(
        **row.model_dump(),
        photos=[
            AdminPhoto(
                id=str(photo.id),
                zone=photo.zone.value,
                # The customer's own word for the room wins over "Autre", which is
                # the entire reason they were asked for one. Kept as they wrote it,
                # escaped where it is rendered.
                zone_label_fr=(
                    photo.zone_label
                    or PHOTO_ZONE_LABELS_FR.get(photo.zone, photo.zone.value)
                ),
                customer_named=bool(photo.zone_label),
                bytes_size=photo.bytes_size,
                created_at=photo.created_at,
            )
            for photo in photos
        ],
        computed_breakdown=request.computed_breakdown,
        consent_given=lead.consent_given,
        utm_source=lead.utm_source,
        utm_medium=lead.utm_medium,
        landing_path=lead.landing_path,
        rate_card_version=active.version if active else None,
        offers=[
            OfferSent(
                id=offer.id,
                to_email=offer.to_email,
                subject=offer.subject,
                total_cents=offer.total_cents,
                status=offer.status,
                sent_at=offer.sent_at,
                error=offer.error,
            )
            for offer in offers
        ],
    )


@router.get("/requests/{request_id}", response_model=AdminRequestDetail)
async def request_detail(
    request_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> AdminRequestDetail:
    return await _detail(session, request_id)


# Which model each editable field lives on. The detail page shows contact, address
# and property side by side as if they were one record; underneath they are three
# tables, and a dict beats three if/elif ladders that drift apart.
_CUSTOMER_FIELDS: dict[str, str] = {
    "full_name": "lead",
    "company": "lead",
    "email": "lead",
    "phone": "lead",
    "preferred_contact": "lead",
    "address_line": "property",
    "city": "property",
    "borough": "property",
    "postal_code": "property",
    "area_sqft": "property",
    "bedrooms": "property",
    "bathrooms": "property",
    "floors": "property",
    "restrooms": "property",
    "locale": "lead",
    "property_type": "property",
    "desired_start": "request",
    "access_notes": "request",
    "frequency": "request",
    "services": "request",
    "night_access": "request",
}

# Columns the database will not accept a NULL in. An emptied text box legitimately
# means "clear this"; an emptied dropdown means the browser sent nothing useful,
# and writing None would be an IntegrityError five lines later with a message
# nobody can act on.
_REQUIRED: frozenset[str] = frozenset({
    "full_name", "locale", "property_type", "frequency", "services", "night_access",
})


@router.patch("/requests/{request_id}/customer", response_model=AdminRequestDetail)
async def update_customer(
    request_id: UUID,
    payload: AdminCustomerPatch,
    session: AsyncSession = Depends(get_session),
) -> AdminRequestDetail:
    """Correct what the customer told us, after they told us something better.

    Half of what arrives on a quote form is a first draft: an area guessed low, a
    phone number with a digit missing, an address left blank and given on the call.
    None of it was editable, so the only fix was a psql session.

    ONLY THE KEYS THAT ARE PRESENT are written. `model_fields_set` is the whole
    mechanism: {"phone": null} clears the phone, a payload without "phone" leaves
    it alone. Sending the full record on every save would mean one card's form
    silently blanking the fields belonging to another.

    What cannot be edited here, and why, is in AdminCustomerPatch's docstring.
    """
    request, lead, prop = await _request_with_people(session, request_id)
    targets = {"lead": lead, "property": prop, "request": request}

    given = payload.model_dump(exclude_unset=True)
    unknown = set(given) - set(_CUSTOMER_FIELDS)
    if unknown:  # pragma: no cover - the schema cannot produce this
        raise HTTPException(status_code=422, detail=f"not editable: {sorted(unknown)}")

    emptied = sorted(f for f in given if f in _REQUIRED and given[f] is None)
    if emptied:
        raise HTTPException(
            status_code=422, detail=f"ces champs ne peuvent pas être vides : {emptied}"
        )

    # THE AUDIENCE IS THE INVARIANT, not the property type. The public form checks
    # the two against each other on the way in and refuses a house filed as
    # commercial; this keeps that true afterwards. Correcting a condo to a triplex
    # is a correction. Turning it into a shop is a different request, priced by a
    # different half of the grid and asked different questions.
    new_type = given.get("property_type")
    if new_type is not None and AUDIENCE_BY_PROPERTY_TYPE[new_type] is not request.audience:
        raise HTTPException(
            status_code=422,
            detail=f"« {new_type.value} » est un type {AUDIENCE_BY_PROPERTY_TYPE[new_type].value}"
                   f" : cette demande est {request.audience.value}.",
        )

    # A REQUEST WITH NEITHER AN EMAIL NOR A PHONE CANNOT BE ANSWERED, which is why
    # the public form refuses one. Checked against the merged result rather than the
    # payload: a patch clearing only the email is fine if a phone number is on file,
    # and the same patch is a dead end if it is not.
    merged_email = given.get("email", lead.email) if "email" in given else lead.email
    merged_phone = given.get("phone", lead.phone) if "phone" in given else lead.phone
    if not merged_email and not merged_phone:
        raise HTTPException(
            status_code=422,
            detail="Gardez au moins un courriel ou un téléphone : sans l'un des deux, "
                   "la demande ne peut plus être répondue.",
        )

    changed: list[str] = []
    for field, value in given.items():
        target = targets[_CUSTOMER_FIELDS[field]]
        if getattr(target, field) != value:
            setattr(target, field, value)
            changed.append(field)

    if changed:
        await session.commit()
        # Field NAMES only. The values are a customer's address and telephone
        # number, and logs are read by more people and kept longer than rows.
        logger.info("admin.customer.updated", request_id=str(request_id), fields=changed)

    return await _detail(session, request_id)


@router.get("/photos/{photo_id}")
async def photo_bytes(
    photo_id: UUID,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> FileResponse:
    """The image itself, behind admin auth.

    Not served as a static directory, and that is the point: these are photos of
    the inside of a customer's home. A static mount would make every one of them
    readable by anyone who learns the path, forever, with no way to revoke it.
    Going through a route means the session check happens on every single fetch.
    """
    if not settings.photos_dir:
        raise HTTPException(status_code=503, detail="photo storage is not configured")

    photo = await session.get(QuotePhoto, photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="photo not found")

    try:
        path = photo_store.resolve(settings.photos_dir, photo.storage_key)
    except photo_store.PhotoRejected:
        raise HTTPException(status_code=404, detail="photo not found") from None
    if not path.is_file():
        # The row outlived the file: a restore that missed the volume, or the
        # retention sweep. Say so rather than throwing a 500 at the admin.
        raise HTTPException(status_code=410, detail="photo file is gone")

    return FileResponse(
        path,
        media_type=MEDIA_TYPES.get(path.suffix.lstrip("."), "application/octet-stream"),
        # Not for a CDN to hold and not for a shared proxy: private.
        headers={"Cache-Control": "private, max-age=3600"},
    )


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
        (await session.execute(select(Quote).where(Quote.request_id == request.id)))
        .scalars()
        .first()
    )

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
        request,
        lead,
        prop,
        quote.total_cents if quote else None,
        grid.get("extras", {}),
        grid.get("residential_modifiers", {}),
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
    request, lead, prop = await _request_with_people(session, request_id)
    # `request` is passed, not dropped: the reference, the frequency and the
    # period the price covers all come off it, and a preview rendered without it
    # would be a different email from the one that gets sent.
    subject, text = offers.render(
        settings,
        lead=lead,
        prop=prop,
        message=payload.message,
        total_cents=payload.total_cents,
        request=request,
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
            settings,
            session,
            lead=lead,
            prop=prop,
            request=request,
            message=payload.message,
            total_cents=payload.total_cents,
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
        (await session.execute(select(Quote).where(Quote.request_id == request.id)))
        .scalars()
        .first()
    )
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
        id=record.id,
        to_email=record.to_email,
        subject=record.subject,
        total_cents=record.total_cents,
        status=record.status,
        sent_at=record.sent_at,
        error=record.error,
    )


@router.get("/requests/{request_id}/offers", response_model=list[OfferSent])
async def list_offers(
    request_id: UUID,
    session: AsyncSession = Depends(get_session),
    username: str = Depends(require_admin),
) -> list[OfferSent]:
    """Everything sent for this request, newest first — including failures."""
    rows = (
        (
            await session.execute(
                select(OfferEmail)
                .where(OfferEmail.request_id == request_id)
                .order_by(OfferEmail.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [
        OfferSent(
            id=r.id,
            to_email=r.to_email,
            subject=r.subject,
            total_cents=r.total_cents,
            status=r.status,
            sent_at=r.sent_at,
            error=r.error,
        )
        for r in rows
    ]
