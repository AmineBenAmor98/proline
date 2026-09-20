"""Admin API. Until sprint 4 this is a list, a detail patch, and nothing else:
Amine needs to see requests and adjust a price, not a CRM."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.security import TOKEN_TTL_SECONDS, check_credentials, create_token, require_admin
from app.db.session import get_session
from app.models import Lead, Property, Quote, QuoteRequest
from app.models.enums import RequestStatus
from app.schemas.admin import (
    AdminRequestList,
    AdminRequestPatch,
    AdminRequestRow,
    LoginIn,
    LoginOut,
)

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


def _row(request: QuoteRequest, lead: Lead, prop: Property, quoted: int | None) -> AdminRequestRow:
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
        city=prop.city,
        borough=prop.borough,
        access_notes=request.access_notes,
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

    return AdminRequestList(
        items=[_row(request, lead, prop, quoted) for request, lead, prop, quoted in rows],
        total=total,
        counts_by_status={status.value: count for status, count in counts.items()},
    )


@router.patch("/requests/{request_id}", response_model=AdminRequestRow)
async def update_request(
    request_id: str,
    payload: AdminRequestPatch,
    session: AsyncSession = Depends(get_session),
) -> AdminRequestRow:
    result = await session.execute(
        select(QuoteRequest, Lead, Property)
        .join(Lead, Lead.id == QuoteRequest.lead_id)
        .join(Property, Property.id == QuoteRequest.property_id)
        .where(QuoteRequest.id == request_id)
    )
    found = result.first()
    if found is None:
        raise HTTPException(status_code=404, detail="request not found")
    request, lead, prop = found

    if payload.status:
        request.status = payload.status

    quoted_total = None
    if payload.quoted_total_cents is not None:
        quote = (
            await session.execute(select(Quote).where(Quote.request_id == request.id))
        ).scalars().first()
        if quote is None:
            quote = Quote(
                request_id=request.id,
                rate_card_id=request.rate_card_id,
                total_cents=payload.quoted_total_cents,
                notes=payload.notes,
            )
            session.add(quote)
        else:
            quote.total_cents = payload.quoted_total_cents
            if payload.notes is not None:
                quote.notes = payload.notes
        quoted_total = payload.quoted_total_cents
        if request.status == RequestStatus.new or request.status == RequestStatus.priced:
            request.status = RequestStatus.quoted

    await session.commit()
    await session.refresh(request)
    return _row(request, lead, prop, quoted_total)
