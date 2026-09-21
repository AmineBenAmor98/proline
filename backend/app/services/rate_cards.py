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
from app.pricing.models import ExtraSpec, ModifierOption, ModifierSpec
from app.schemas.rate_card import RateCardIn


def _extras(raw: dict) -> dict[str, ExtraSpec]:
    """Build the extra specs from the card's JSON.

    The `int` branch tolerates a card written before extras had units, when the
    grid held `extras_cents: {code: cents}`. No such card exists any more, but
    the shape is one a hand-edited grid could still arrive in.
    """
    out: dict[str, ExtraSpec] = {}
    for code, value in (raw or {}).items():
        if isinstance(value, int):  # a card written before units existed
            out[code] = ExtraSpec(unit="flat", cents=value, label_fr=code, label_en=code)
            continue
        out[code] = ExtraSpec(
            unit=value.get("unit", "flat"),
            cents=int(value.get("cents", 0)),
            label_fr=value.get("label_fr", code),
            label_en=value.get("label_en", code),
            per_fr=value.get("per_fr", ""),
            per_en=value.get("per_en", ""),
        )
    return out


def _modifiers(raw: dict) -> dict[str, ModifierSpec]:
    out: dict[str, ModifierSpec] = {}
    for code, value in (raw or {}).items():
        out[code] = ModifierSpec(
            label_fr=value.get("label_fr", code),
            label_en=value.get("label_en", code),
            help_fr=value.get("help_fr", ""),
            help_en=value.get("help_en", ""),
            short_fr=value.get("short_fr", ""),
            short_en=value.get("short_en", ""),
            sort=int(value.get("sort", 100)),
            options=tuple(
                ModifierOption(
                    value=option.get("value", ""),
                    label_fr=option.get("label_fr", ""),
                    label_en=option.get("label_en", ""),
                    multiplier=Decimal(str(option.get("multiplier", "1"))),
                    cents=int(option.get("cents", 0)),
                )
                for option in value.get("options", [])
            ),
        )
    return out


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
        extras=_extras(grid.get("extras", {})),
        residential_modifiers=_modifiers(grid.get("residential_modifiers", {})),
        max_residential_multiplier=Decimal(str(grid.get("max_residential_multiplier", "2.5"))),
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
        extras=_extras({code: spec.model_dump() for code, spec in grid.extras.items()}),
        residential_modifiers=_modifiers(
            {
                code: spec.model_dump(mode="json")
                for code, spec in grid.residential_modifiers.items()
            }
        ),
        max_residential_multiplier=grid.max_residential_multiplier,
        frequency_discount_pct=dict(grid.frequency_discount_pct),
        night_access_multiplier=grid.night_access_multiplier,
    )


async def list_rate_cards(session: AsyncSession, limit: int = 50) -> list[tuple[RateCard, int]]:
    """The most recent cards, newest first, with how many requests each priced.

    Bounded: every row carries its whole grid as JSONB and the list grows by one
    every time a price changes, so an unbounded query would quietly turn into a
    megabyte of history on the admin's first paint.
    """
    cards = (
        await session.execute(
            select(RateCard)
            .order_by(RateCard.effective_from.desc(), RateCard.id.desc())
            .limit(limit)
        )
    ).scalars().all()

    # Counted by the foreign key, not by digging the version out of every stored
    # breakdown's JSONB. That grouped on `computed_breakdown->>'rate_card_version'`,
    # which no index can serve, so every load of /admin/tarifs sequentially scanned
    # quote_requests and parsed each document -- to recover a column that was
    # sitting in the same row all along.
    counts = dict(
        (
            await session.execute(
                select(QuoteRequest.rate_card_id, func.count())
                .where(QuoteRequest.computed_total_cents.isnot(None))
                .group_by(QuoteRequest.rate_card_id)
            )
        ).all()
    )
    return [(card, counts.get(card.id, 0)) for card in cards]


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
