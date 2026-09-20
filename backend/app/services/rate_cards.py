"""Reading and publishing rate cards.

A price change is an INSERT, never an UPDATE: `computed_breakdown` on every stored
request records the `rate_card_version` that produced it, so editing a card in place
would make an already-sent quote impossible to reconstruct. The one exception is
`residential_online_pricing`, which is not a price.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import QuoteRequest, RateCard
from app.pricing import RateCardData
from app.schemas.rate_card import RateCardIn


def to_pricing_data(card: RateCard) -> RateCardData:
    grid = card.grid or {}
    return RateCardData(
        version=card.version,
        hourly_rate_cents=card.hourly_rate_cents,
        minimum_visit_cents=card.minimum_visit_cents,
        travel_cents=card.travel_cents,
        residential_base_cents=grid.get("residential_base_cents", {}),
        residential_area_cents_per_100sqft=grid.get("residential_area_cents_per_100sqft", 0),
        residential_area_allowance_sqft=grid.get("residential_area_allowance_sqft", 1000),
        minutes_per_100sqft=grid.get("minutes_per_100sqft", {}),
        minutes_per_restroom=grid.get("minutes_per_restroom", 12),
        extras_cents=grid.get("extras_cents", {}),
        frequency_discount_pct={
            key: Decimal(str(value))
            for key, value in (grid.get("frequency_discount_pct") or {}).items()
        },
        night_access_multiplier=Decimal(str(grid.get("night_access_multiplier", "1.0"))),
    )


async def get_active_rate_card(session: AsyncSession) -> RateCard | None:
    result = await session.execute(
        select(RateCard).where(RateCard.is_active.is_(True)).order_by(RateCard.effective_from.desc())
    )
    return result.scalars().first()


def draft_to_pricing_data(payload: RateCardIn, version: str = "draft") -> RateCardData:
    """The same conversion as `to_pricing_data`, for a card that is not saved.

    Preview prices a draft without writing anything, so the admin can see what a
    change does before anyone is quoted with it.
    """
    grid = payload.grid
    return RateCardData(
        version=version,
        hourly_rate_cents=payload.hourly_rate_cents,
        minimum_visit_cents=payload.minimum_visit_cents,
        travel_cents=payload.travel_cents,
        residential_base_cents=dict(grid.residential_base_cents),
        residential_area_cents_per_100sqft=grid.residential_area_cents_per_100sqft,
        residential_area_allowance_sqft=grid.residential_area_allowance_sqft,
        minutes_per_100sqft=dict(grid.minutes_per_100sqft),
        minutes_per_restroom=grid.minutes_per_restroom,
        extras_cents=dict(grid.extras_cents),
        frequency_discount_pct=dict(grid.frequency_discount_pct),
        night_access_multiplier=grid.night_access_multiplier,
    )


async def list_rate_cards(session: AsyncSession) -> list[tuple[RateCard, int]]:
    """Every card, newest first, with how many requests each one priced."""
    cards = (
        await session.execute(select(RateCard).order_by(RateCard.effective_from.desc(), RateCard.id.desc()))
    ).scalars().all()

    version_column = QuoteRequest.computed_breakdown["rate_card_version"].astext
    counts = dict(
        (
            await session.execute(
                select(version_column, func.count())
                .where(QuoteRequest.computed_breakdown.isnot(None))
                .group_by(version_column)
            )
        ).all()
    )
    return [(card, counts.get(card.version, 0)) for card in cards]


async def _next_version(session: AsyncSession, today: date) -> str:
    """One card per day is the normal case; a second on the same day gets a suffix."""
    taken = set(
        (
            await session.execute(
                select(RateCard.version).where(RateCard.version.like(f"{today.isoformat()}%"))
            )
        ).scalars().all()
    )
    if today.isoformat() not in taken:
        return today.isoformat()
    for suffix in range(2, 100):
        candidate = f"{today.isoformat()}-{suffix}"
        if candidate not in taken:
            return candidate
    raise ValueError("too many rate cards published today")


async def publish_rate_card(
    session: AsyncSession, payload: RateCardIn, today: date | None = None
) -> RateCard:
    """Close the active card and open a new one, in a single transaction."""
    today = today or date.today()
    current = await get_active_rate_card(session)

    card = RateCard(
        version=await _next_version(session, today),
        effective_from=today,
        is_active=True,
        # The switch carries over: publishing a new grid is not a reason to start
        # quoting again if the admin had deliberately stopped.
        residential_online_pricing=current.residential_online_pricing if current else True,
        hourly_rate_cents=payload.hourly_rate_cents,
        minimum_visit_cents=payload.minimum_visit_cents,
        travel_cents=payload.travel_cents,
        grid=payload.grid.model_dump(mode="json"),
    )
    if current is not None:
        current.is_active = False
        current.effective_to = today
    session.add(card)
    await session.commit()
    await session.refresh(card)
    return card


async def set_online_pricing(session: AsyncSession, enabled: bool) -> RateCard | None:
    """Edited in place on purpose: this is not a price, so it cannot change what an
    already-sent quote recomputes to, and a new version nobody priced with would be
    noise in the history."""
    card = await get_active_rate_card(session)
    if card is None:
        return None
    card.residential_online_pricing = enabled
    await session.commit()
    await session.refresh(card)
    return card
