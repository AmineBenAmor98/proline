"""Pure data for the pricing engine. No SQLAlchemy, no FastAPI, no I/O."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True)
class LineItem:
    code: str
    label_fr: str
    amount_cents: int


@dataclass(frozen=True)
class Breakdown:
    lines: tuple[LineItem, ...]
    subtotal_cents: int
    discount_cents: int
    total_cents: int
    estimated_minutes: int | None
    is_firm: bool
    rate_card_version: str

    def as_dict(self) -> dict:
        return {
            "lines": [
                {"code": item.code, "label_fr": item.label_fr, "amount_cents": item.amount_cents}
                for item in self.lines
            ],
            "subtotal_cents": self.subtotal_cents,
            "discount_cents": self.discount_cents,
            "total_cents": self.total_cents,
            "estimated_minutes": self.estimated_minutes,
            "is_firm": self.is_firm,
            "rate_card_version": self.rate_card_version,
        }


@dataclass(frozen=True)
class PricingInput:
    audience: str
    property_type: str
    area_sqft: int | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    floors: int | None = None
    restrooms: int | None = None
    frequency: str = "one_time"
    services: tuple[str, ...] = ()
    extras: tuple[str, ...] = ()
    night_access: bool = False


@dataclass(frozen=True)
class RateCardData:
    """Mirror of the rate_cards row, so the engine never touches the database."""

    version: str
    hourly_rate_cents: int
    minimum_visit_cents: int
    travel_cents: int = 0
    # Residential flat base by (bedrooms, bathrooms), cents.
    residential_base_cents: dict[str, int] = field(default_factory=dict)
    # Cents per 100 sqft above the base allowance.
    residential_area_cents_per_100sqft: int = 0
    residential_area_allowance_sqft: int = 1000
    # Minutes of work per unit, commercial.
    minutes_per_100sqft: dict[str, int] = field(default_factory=dict)
    minutes_per_restroom: int = 12
    extras_cents: dict[str, int] = field(default_factory=dict)
    frequency_discount_pct: dict[str, Decimal] = field(default_factory=dict)
    night_access_multiplier: Decimal = Decimal("1.0")
