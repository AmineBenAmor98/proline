"""Seed a rate card so the calculator returns numbers today.

EVERY VALUE HERE IS A PLACEHOLDER. Replace them with Proline's real figures,
taken from current customers: what they pay, and how long the job really takes.
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
    async with SessionLocal() as session:
        existing = (
            await session.execute(select(RateCard).where(RateCard.version == VERSION))
        ).scalars().first()
        if existing:
            existing.grid = GRID
            existing.is_active = True
            print(f"updated rate card {VERSION}")
        else:
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
            print(f"created rate card {VERSION}")
        await session.commit()


if __name__ == "__main__":
    asyncio.run(main())
