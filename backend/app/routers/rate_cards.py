"""The rate card screen's API.

Four reads and two writes. Publishing inserts a new version; the only thing edited
in place is the online-pricing switch, which is not a price. Preview prices a draft
against the engine without saving anything, so a change can be checked before
anyone is quoted with it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_admin
from app.db.session import get_session
from app.models import RateCard
from app.pricing import PricingInput, price_request
from app.pricing.engine import PricingError
from app.schemas.rate_card import (
    OnlinePricingIn,
    PreviewIn,
    PreviewOut,
    RateCardIn,
    RateCardList,
    RateCardOut,
    Scenario,
    ScenarioResult,
)
from app.services.rate_cards import (
    draft_to_pricing_data,
    get_active_rate_card,
    list_rate_cards,
    publish_rate_card,
    set_online_pricing,
    to_pricing_data,
)

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


def _out(card: RateCard, priced: int = 0) -> RateCardOut:
    return RateCardOut(
        version=card.version,
        effective_from=card.effective_from,
        effective_to=card.effective_to,
        is_active=card.is_active,
        residential_online_pricing=card.residential_online_pricing,
        hourly_rate_cents=card.hourly_rate_cents,
        minimum_visit_cents=card.minimum_visit_cents,
        travel_cents=card.travel_cents,
        grid=card.grid or {},
        priced_requests=priced,
    )


@router.get("/rate-card", response_model=RateCardOut)
async def read_active(session: AsyncSession = Depends(get_session)) -> RateCardOut:
    card = await get_active_rate_card(session)
    if card is None:
        raise HTTPException(status_code=404, detail="no active rate card")
    return _out(card)


@router.get("/rate-cards", response_model=RateCardList)
async def read_history(session: AsyncSession = Depends(get_session)) -> RateCardList:
    rows = await list_rate_cards(session)
    return RateCardList(items=[_out(card, priced) for card, priced in rows])


def _score(scenario: Scenario, card_data) -> tuple[int | None, list[dict], str | None]:
    try:
        breakdown = price_request(
            PricingInput(
                audience=scenario.audience,
                property_type=scenario.property_type,
                area_sqft=scenario.area_sqft,
                bedrooms=scenario.bedrooms,
                bathrooms=scenario.bathrooms,
                restrooms=scenario.restrooms,
                services=tuple(scenario.services),
                extras=tuple(scenario.extras),
                frequency=scenario.frequency,
                night_access=scenario.night_access,
            ),
            card_data,
        )
    except PricingError as error:
        return None, [], str(error)
    return breakdown.total_cents, breakdown.as_dict()["lines"], None


@router.post("/rate-card/preview", response_model=PreviewOut)
async def preview(
    payload: PreviewIn, session: AsyncSession = Depends(get_session)
) -> PreviewOut:
    """Price each scenario twice: once with the live card, once with the draft.

    Writes nothing. This is the check that catches a decimal slip before it is
    quoted to a visitor.
    """
    active = await get_active_rate_card(session)
    active_data = to_pricing_data(active) if active else None
    draft_data = draft_to_pricing_data(payload.card)

    results = []
    for scenario in payload.scenarios:
        draft_total, draft_lines, error = _score(scenario, draft_data)
        active_total = _score(scenario, active_data)[0] if active_data else None
        results.append(
            ScenarioResult(
                label=scenario.label,
                active_total_cents=active_total,
                draft_total_cents=draft_total,
                draft_lines=draft_lines,
                error=error,
            )
        )
    return PreviewOut(results=results)


@router.post("/rate-card", response_model=RateCardOut, status_code=201)
async def publish(
    payload: RateCardIn, session: AsyncSession = Depends(get_session)
) -> RateCardOut:
    card = await publish_rate_card(session, payload)
    return _out(card)


@router.patch("/rate-card/online-pricing", response_model=RateCardOut)
async def toggle_online_pricing(
    payload: OnlinePricingIn, session: AsyncSession = Depends(get_session)
) -> RateCardOut:
    card = await set_online_pricing(session, payload.enabled)
    if card is None:
        raise HTTPException(status_code=404, detail="no active rate card")
    return _out(card)
