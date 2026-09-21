"""Business operations for quote requests. Routers stay thin; this is where the work is."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Lead, Property, QuoteRequest
from app.models.enums import Audience, RequestStatus
from app.pricing import Breakdown, PricingInput, price_request
from app.pricing.engine import PricingError
from app.schemas.quote import PriceDraftIn, QuoteRequestIn
from app.services.rate_cards import get_active_rate_card, to_pricing_data


def _pricing_input(payload: QuoteRequestIn | PriceDraftIn) -> PricingInput:
    prop = payload.property
    return PricingInput(
        audience=payload.audience.value,
        property_type=prop.property_type.value,
        area_sqft=prop.area_sqft,
        bedrooms=prop.bedrooms,
        bathrooms=prop.bathrooms,
        floors=prop.floors,
        restrooms=prop.restrooms,
        frequency=payload.frequency.value,
        services=tuple(code.value for code in payload.services),
        extras=dict(payload.extras),
        modifiers=dict(payload.modifiers),
        night_access=payload.night_access,
    )


async def compute_price(
    session: AsyncSession, payload: QuoteRequestIn | PriceDraftIn
) -> tuple[Breakdown | None, str | None]:
    """Returns (breakdown, rate_card_id). Never raises on a missing grid: a request
    without a price is still a lead, and a human prices it.

    Two things deliberately produce no price for a residential request: the admin
    has switched online pricing off, or the grid has no cell for that bedroom and
    bathroom count. Both mean "we have not decided this price", and inventing one
    is worse than saying a person will call.
    """
    card = await get_active_rate_card(session)
    if card is None:
        return None, None
    if payload.audience == Audience.residential and not card.residential_online_pricing:
        return None, str(card.id)
    try:
        breakdown = price_request(_pricing_input(payload), to_pricing_data(card))
    except PricingError:
        return None, str(card.id)
    return breakdown, str(card.id)


async def create_quote_request(
    session: AsyncSession, payload: QuoteRequestIn
) -> tuple[QuoteRequest, Breakdown | None]:
    """One transaction: lead, property and request commit together or not at all."""
    contact = payload.contact
    lead = Lead(
        full_name=contact.full_name,
        email=contact.email,
        phone=contact.phone,
        company=contact.company,
        locale=contact.locale,
        preferred_contact=contact.preferred_contact,
        consent_given=contact.consent_given,
        utm_source=payload.attribution.utm_source,
        utm_medium=payload.attribution.utm_medium,
        utm_campaign=payload.attribution.utm_campaign,
        utm_term=payload.attribution.utm_term,
        gclid=payload.attribution.gclid,
        landing_path=payload.attribution.landing_path,
    )
    session.add(lead)
    await session.flush()

    prop = payload.property
    property_row = Property(
        lead_id=lead.id,
        property_type=prop.property_type,
        area_sqft=prop.area_sqft,
        bedrooms=prop.bedrooms,
        bathrooms=prop.bathrooms,
        restrooms=prop.restrooms,
        floors=prop.floors,
        address_line=prop.address_line,
        city=prop.city,
        borough=prop.borough,
        postal_code=prop.postal_code,
    )
    session.add(property_row)
    await session.flush()

    breakdown, rate_card_id = await compute_price(session, payload)

    request = QuoteRequest(
        lead_id=lead.id,
        property_id=property_row.id,
        audience=payload.audience,
        services=payload.services,
        frequency=payload.frequency,
        extras=payload.extras,
        modifiers=payload.modifiers,
        desired_start=payload.desired_start,
        access_notes=payload.access_notes,
        night_access=payload.night_access,
        # Always `new`, priced or not. Whether the calculator produced a number
        # is `computed_total_cents`, one line below, and the admin shows it as
        # the number. A status is about what a person still owes the client.
        status=RequestStatus.new,
        rate_card_id=rate_card_id,
        computed_total_cents=breakdown.total_cents if breakdown else None,
        computed_breakdown=breakdown.as_dict() if breakdown else None,
    )
    session.add(request)
    await session.commit()
    await session.refresh(request)
    return request, breakdown
