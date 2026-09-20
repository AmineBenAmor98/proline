from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RateCard
from app.pricing import RateCardData


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
