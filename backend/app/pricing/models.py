"""Pure data for the pricing engine. No SQLAlchemy, no FastAPI, no I/O."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True)
class ExtraSpec:
    """An extra, priced by its unit.

    `unit` decides where the quantity comes from, and nothing else:
      flat          the quantity is always 1
      each          the visitor says how many (windows, rooms, cabinets, loads)
      per_100sqft   derived from the area, rounded up

    The labels live here, on the rate card, so the engine and the quote form read
    the same words and a new extra needs no code in either.
    """

    unit: str
    cents: int
    label_fr: str
    label_en: str
    per_fr: str = ""
    per_en: str = ""

    def quantity(self, asked: int | None, area_sqft: int | None) -> int:
        if self.unit == "flat":
            return 1
        if self.unit == "per_100sqft":
            return math.ceil((area_sqft or 0) / 100)
        return max(0, asked or 0)


@dataclass(frozen=True)
class ModifierOption:
    """One answer to a modifier's question, and what it does to the price."""

    value: str
    label_fr: str
    label_en: str
    # Multiplies the work (base + rooms + area). 1 means this answer is free.
    multiplier: Decimal = Decimal("1")
    # Added after the multiplying, so two of them do not compound each other.
    cents: int = 0

    @property
    def is_neutral(self) -> bool:
        return self.multiplier == 1 and self.cents == 0


@dataclass(frozen=True)
class ModifierSpec:
    """A question about the job, whose answer changes the price.

    Every modifier is the same shape -- a question with options -- because the
    alternative is a type per question (`boolean`, `choice`, `count`) and a branch
    per type in the engine, the form and the admin. "Premier ménage ?" is a
    question with two options; "état du logement" is one with three. One shape
    means a sixth modifier costs no code anywhere, which is the rule extras
    already follow.
    """

    # The question, as the form asks it: "Est-ce un premier ménage ?"
    label_fr: str
    label_en: str
    options: tuple[ModifierOption, ...] = ()
    help_fr: str = ""
    help_en: str = ""
    # What it is called on a quote line: "Premier ménage". A question mark does
    # not belong on an invoice, and the answer alone ("Oui") says nothing -- the
    # surcharge line reads "Premier ménage : Oui".
    short_fr: str = ""
    short_en: str = ""
    # Where this question sits in the questionnaire. Explicit because JSONB does
    # NOT preserve key order -- Postgres stores an object's keys sorted by length
    # then bytewise -- so "the order the admin wrote them in" does not survive a
    # round trip, and the order questions are asked in is an editorial decision,
    # not an accident of how they happen to be spelled.
    sort: int = 100

    def line_fr(self, option: ModifierOption) -> str:
        return f"{self.short_fr or self.label_fr} : {option.label_fr}"

    def line_en(self, option: ModifierOption) -> str:
        return f"{self.short_en or self.label_en}: {option.label_en}"

    def option(self, value: str | None) -> ModifierOption | None:
        for candidate in self.options:
            if candidate.value == value:
                return candidate
        return None

    @property
    def prices_anything(self) -> bool:
        """A question whose every answer is free is not asked.

        Same rule as an extra with no price: the form offers only what the card
        can price, so a modifier shipped neutral stays invisible until a real
        number is entered.
        """
        return any(not option.is_neutral for option in self.options)


@dataclass(frozen=True)
class LineItem:
    code: str
    label_fr: str
    label_en: str
    amount_cents: int
    # Set for anything billed by quantity, so the breakdown can say "x 6".
    quantity: int | None = None
    unit_fr: str = ""
    unit_en: str = ""


@dataclass(frozen=True)
class Breakdown:
    lines: tuple[LineItem, ...]
    # The work itself: the lines added up, before the discount and before the
    # minimum. It is the sum of `lines`, always, so the breakdown closes.
    subtotal_cents: int
    discount_cents: int
    # What the minimum visit added back, when the discounted price fell under it.
    # Zero on almost every quote.
    minimum_adjustment_cents: int
    total_cents: int
    estimated_minutes: int | None
    is_firm: bool
    rate_card_version: str

    def as_dict(self) -> dict:
        return {
            "lines": [
                {
                    "code": item.code,
                    "label_fr": item.label_fr,
                    "label_en": item.label_en,
                    "amount_cents": item.amount_cents,
                    "quantity": item.quantity,
                    "unit_fr": item.unit_fr,
                    "unit_en": item.unit_en,
                }
                for item in self.lines
            ],
            "subtotal_cents": self.subtotal_cents,
            "discount_cents": self.discount_cents,
            "minimum_adjustment_cents": self.minimum_adjustment_cents,
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
    # code -> the chosen option's value. An unknown code or value is ignored,
    # exactly like an extra the card has never heard of.
    modifiers: dict[str, str] = field(default_factory=dict)
    # code -> quantity. A flat extra is present with any quantity.
    extras: dict[str, int] = field(default_factory=dict)
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
    extras: dict[str, ExtraSpec] = field(default_factory=dict)
    residential_modifiers: dict[str, ModifierSpec] = field(default_factory=dict)
    # Modifiers compound, and compounding runs away: a first clean on a cluttered
    # home with pets could reach 2.7x on its own. The product is clamped here and
    # the breakdown says when the clamp bit.
    max_residential_multiplier: Decimal = Decimal("2.5")
    frequency_discount_pct: dict[str, Decimal] = field(default_factory=dict)
    night_access_multiplier: Decimal = Decimal("1.0")
