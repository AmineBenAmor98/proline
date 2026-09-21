"""Publish a starting rate card so the calculator returns numbers today.

EVERY VALUE HERE IS A PLACEHOLDER. Replace them with Proline's real figures,
taken from current customers: what they pay, and how long the job really takes --
or, once the app is running, edit them in /admin/tarifs instead of here.

Run:  python -m scripts.seed_rate_card
"""

import asyncio
from datetime import date

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import RateCard

VERSION = "placeholder-2026-09"

GRID = {
    # Residential flat base by bedrooms and bathrooms, in cents.
    "residential_base_cents": {
        "1br_1ba": 12000,
        "2br_1ba": 14000,
        "2br_2ba": 16000,
        "3br_1ba": 16500,
        "3br_2ba": 18500,
        "4br_2ba": 21000,
        "4br_3ba": 23500,
        "5br_3ba": 26000,
    },
    "residential_area_allowance_sqft": 1000,
    "residential_area_cents_per_100sqft": 900,
    # Commercial: minutes of work per 100 sq ft, per service.
    "minutes_per_100sqft": {
        "office_cleaning": 6,
        "common_areas": 4,
        "post_construction": 14,
        "end_of_lease": 10,
        "floor_stripping_waxing": 18,
        "carpets": 8,
    },
    "minutes_per_restroom": 12,
    "extras_cents": {"fridge": 2500, "oven": 3000, "windows": 4000},
    "frequency_discount_pct": {"biweekly": 10, "weekly": 15, "monthly": 5},
    "night_access_multiplier": "1.15",
}


async def main() -> None:
    """Publish the placeholder grid as a new active version.

    Like the admin screen, this never edits a card in place: `computed_breakdown`
    on every stored request records the version that priced it, so rewriting a
    card would make an already-sent quote impossible to reconstruct. Re-running
    this is a no-op once the card is active.
    """
    async with SessionLocal() as session:
        existing = (
            await session.execute(select(RateCard).where(RateCard.version == VERSION))
        ).scalars().first()
        if existing is not None:
            print(
                f"rate card {VERSION} already exists"
                + (" and is active" if existing.is_active else " (superseded)")
                + "; edit prices in /admin/tarifs"
            )
            return

        # Exactly one card is active at a time: close whatever is open first.
        for card in (
            await session.execute(select(RateCard).where(RateCard.is_active.is_(True)))
        ).scalars().all():
            card.is_active = False
            card.effective_to = date.today()

        session.add(
            RateCard(
                version=VERSION,
                effective_from=date.today(),
                is_active=True,
                hourly_rate_cents=4500,
                minimum_visit_cents=12000,
                travel_cents=1500,
                grid=GRID,
            )
        )
        await session.commit()
        print(f"published rate card {VERSION}")


if __name__ == "__main__":
    asyncio.run(main())
