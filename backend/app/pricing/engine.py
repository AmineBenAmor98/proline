"""The pricing engine: pure functions, integers in cents, no I/O.

Residential is a flat grid by bedrooms and bathrooms, adjusted for area, plus extras
and a recurring discount. Commercial estimates minutes of work and multiplies by the
hourly rate. Both return a breakdown a human can read out to a client.
"""

from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal

from app.pricing.models import Breakdown, LineItem, PricingInput, RateCardData


class PricingError(ValueError):
    """Raised when the inputs cannot produce a defensible price."""


# Every line the client reads is written in both languages here. The quote page
# renders the one matching its locale, so an English visitor never sees a French
# line item next to an English price.
EXTRA_LABELS = {
    "fridge": ("Intérieur du réfrigérateur", "Inside the fridge"),
    "oven": ("Intérieur du four", "Inside the oven"),
    "windows": ("Vitres intérieures", "Interior windows"),
    "garage": ("Garage", "Garage"),
    "carpets": ("Shampooing de tapis", "Carpet shampoo"),
}


def _cents(value: Decimal | float | int) -> int:
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _residential_key(bedrooms: int, bathrooms: int) -> str:
    return f"{min(bedrooms, 5)}br_{min(bathrooms, 4)}ba"


def _price_residential(data: PricingInput, card: RateCardData) -> tuple[list[LineItem], int | None]:
    if data.bedrooms is None or data.bathrooms is None:
        raise PricingError("residential pricing needs bedrooms and bathrooms")

    key = _residential_key(data.bedrooms, data.bathrooms)
    base = card.residential_base_cents.get(key)
    if base is None:
        raise PricingError(f"no residential base price for {key}")

    lines = [
        LineItem(
            "base",
            f"Ménage de base ({data.bedrooms} ch., {data.bathrooms} sdb)",
            f"Standard clean ({data.bedrooms} bed, {data.bathrooms} bath)",
            base,
        )
    ]

    area = data.area_sqft or 0
    extra_area = max(0, area - card.residential_area_allowance_sqft)
    if extra_area and card.residential_area_cents_per_100sqft:
        blocks = math.ceil(extra_area / 100)
        amount = blocks * card.residential_area_cents_per_100sqft
        lines.append(
            LineItem(
                "area",
                f"Superficie supplémentaire ({extra_area} pi²)",
                f"Additional area ({extra_area} sq ft)",
                amount,
            )
        )

    # No minutes for residential: the price is a flat grid, not a time estimate,
    # and dividing the price by the hourly rate would invent a number.
    return lines, None


def _price_commercial(data: PricingInput, card: RateCardData) -> tuple[list[LineItem], int]:
    if not data.area_sqft:
        raise PricingError("commercial pricing needs an area")

    minutes = Decimal(0)
    blocks = Decimal(data.area_sqft) / 100

    for service in data.services or ("office_cleaning",):
        per_block = card.minutes_per_100sqft.get(service)
        if per_block is None:
            continue
        minutes += blocks * per_block

    if minutes == 0:
        raise PricingError("no priced service matched this request")

    restrooms = data.restrooms or 0
    minutes += restrooms * card.minutes_per_restroom

    if data.night_access:
        minutes *= card.night_access_multiplier

    labour = Decimal(minutes) / 60 * card.hourly_rate_cents
    lines = [LineItem("labour", "Main-d'œuvre estimée", "Estimated labour", _cents(labour))]
    if card.travel_cents:
        lines.append(LineItem("travel", "Déplacement", "Travel", card.travel_cents))

    return lines, _cents(minutes)


def price_request(data: PricingInput, card: RateCardData) -> Breakdown:
    if data.audience == "residential":
        lines, minutes = _price_residential(data, card)
    else:
        lines, minutes = _price_commercial(data, card)

    for extra in data.extras:
        amount = card.extras_cents.get(extra)
        if amount:
            fallback = extra.replace("_", " ").capitalize()
            label_fr, label_en = EXTRA_LABELS.get(extra, (fallback, fallback))
            lines.append(LineItem(f"extra:{extra}", label_fr, label_en, amount))

    subtotal = sum(item.amount_cents for item in lines)
    subtotal = max(subtotal, card.minimum_visit_cents)

    pct = card.frequency_discount_pct.get(data.frequency, Decimal(0))
    discount = _cents(Decimal(subtotal) * pct / 100) if pct else 0

    return Breakdown(
        lines=tuple(lines),
        subtotal_cents=subtotal,
        discount_cents=discount,
        total_cents=subtotal - discount,
        estimated_minutes=minutes,
        # Residential standard homes get a firm price; commercial is always reviewed.
        is_firm=data.audience == "residential",
        rate_card_version=card.version,
    )
