"""The pricing engine: pure functions, integers in cents, no I/O.

Residential is a flat grid by bedrooms and bathrooms, adjusted for area, plus extras
and a recurring discount. Commercial estimates minutes of work and multiplies by the
hourly rate. Both return a breakdown a human can read out to a client.
"""

from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal

from app.pricing.models import Breakdown, LineItem, ModifierSpec, PricingInput, RateCardData


class PricingError(ValueError):
    """Raised when the inputs cannot produce a defensible price."""


def _cents(value: Decimal | float | int) -> int:
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


# The grid the card is allowed to hold (app/schemas/rate_card.py's KEY_RE).
MAX_BEDROOMS = 5
MAX_BATHROOMS = 4


def _residential_key(bedrooms: int, bathrooms: int) -> str:
    return f"{bedrooms}br_{bathrooms}ba"


def _price_residential(data: PricingInput, card: RateCardData) -> tuple[list[LineItem], int | None]:
    if data.bedrooms is None or data.bathrooms is None:
        raise PricingError("residential pricing needs bedrooms and bathrooms")

    # This used to clamp: min(bedrooms, 5). An eight-bedroom house was quoted
    # online at the five-bedroom price, which is not a discount, it is a job
    # priced for a different house. Out of the grid means out of the online
    # calculator -- exactly like a combination the card has no cell for.
    if not (1 <= data.bedrooms <= MAX_BEDROOMS and 1 <= data.bathrooms <= MAX_BATHROOMS):
        raise PricingError(
            f"{data.bedrooms} bedrooms / {data.bathrooms} bathrooms is outside the grid"
        )

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

    if not data.services:
        # This used to fall back to office_cleaning. A warehouse with nothing
        # ticked then came back priced as an office, with no line saying so. An
        # estimate nobody asked for is worse than none: commercial is quoted by a
        # person anyway, and a blank number tells them to ask what the job is.
        raise PricingError("no service selected")

    minutes = Decimal(0)
    blocks = Decimal(data.area_sqft) / 100

    for service in data.services:
        per_block = card.minutes_per_100sqft.get(service)
        if per_block is None:
            continue
        minutes += blocks * per_block

    # Restrooms count before the check: a common-area contract that is only
    # restrooms is a real job, and refusing to price it because no per-area
    # service matched would be arithmetic getting in the way of a quote.
    restrooms = data.restrooms or 0
    minutes += restrooms * card.minutes_per_restroom

    if minutes == 0:
        raise PricingError("no priced service matched this request")

    if data.night_access:
        minutes *= card.night_access_multiplier

    labour = Decimal(minutes) / 60 * card.hourly_rate_cents
    lines = [LineItem("labour", "Main-d'œuvre estimée", "Estimated labour", _cents(labour))]
    if card.travel_cents:
        lines.append(LineItem("travel", "Déplacement", "Travel", card.travel_cents))

    return lines, _cents(minutes)


def _apply_modifiers(
    data: PricingInput, card: RateCardData, work_cents: int
) -> list[LineItem]:
    """The answers about the job, turned into lines.

    Two kinds, and the difference is deliberate. A multiplier scales the work,
    because a first clean on a cluttered home is the same rooms taking longer.
    An amount is added after the multiplying, because two additions should not
    compound each other -- and neither kind touches the extras, whose per-unit
    prices already scale with their own quantity.

    Multipliers compound with each other, under the card's cap.
    """
    if data.audience != "residential" or not card.residential_modifiers:
        return []

    multiplier = Decimal(1)
    reasons_fr: list[str] = []
    reasons_en: list[str] = []
    added: list[LineItem] = []

    # The card's order, not the answers' or the codes': a quote reads in the
    # order the questions were asked. See ModifierSpec.sort.
    ordered: list[tuple[str, ModifierSpec]] = sorted(
        card.residential_modifiers.items(), key=lambda pair: (pair[1].sort, pair[0])
    )
    for code, spec in ordered:
        option = spec.option(data.modifiers.get(code))
        if option is None or option.is_neutral:
            continue
        if option.multiplier != 1:
            multiplier *= option.multiplier
            reasons_fr.append(spec.line_fr(option))
            reasons_en.append(spec.line_en(option))
        if option.cents:
            added.append(
                LineItem(
                    f"modifier:{code}",
                    spec.line_fr(option),
                    spec.line_en(option),
                    option.cents,
                )
            )

    lines: list[LineItem] = []
    capped = min(multiplier, card.max_residential_multiplier)
    if capped != 1:
        amount = _cents(Decimal(work_cents) * capped) - work_cents
        limited = capped < multiplier
        shown = capped.quantize(Decimal("0.01")).normalize()
        note_fr = " (plafonné)" if limited else ""
        note_en = " (capped)" if limited else ""
        lines.append(
            LineItem(
                "modifiers",
                "Majoration — " + " · ".join(reasons_fr) + note_fr,
                "Surcharge — " + " · ".join(reasons_en) + note_en,
                amount,
                quantity=None,
                # Two decimals: the arithmetic keeps full precision, but
                # "x 2.3345" on a quote is a number nobody asked to see.
                unit_fr=f"× {shown}",
                unit_en=f"× {shown}",
            )
        )
    lines.extend(added)
    return lines


def price_request(data: PricingInput, card: RateCardData) -> Breakdown:
    if data.audience == "residential":
        lines, minutes = _price_residential(data, card)
    else:
        lines, minutes = _price_commercial(data, card)

    # After the work, before the extras: a modifier describes how hard the rooms
    # are, so it scales the rooms and nothing else.
    lines.extend(_apply_modifiers(data, card, sum(item.amount_cents for item in lines)))

    # Extras come after the work itself and before the discount. An extra the
    # card has no price for is skipped rather than guessed -- that is the same
    # rule the form follows, since it only offers what the card can price.
    for code, asked in sorted(data.extras.items()):
        spec = card.extras.get(code)
        if spec is None:
            continue
        if spec.unit == "per_100sqft" and not data.area_sqft:
            # Priced by area, and we have none. Silently charging zero meant the
            # visitor ticked the baseboards, paid nothing for them, and the crew
            # did them for free. Say we cannot price it and let a person quote.
            raise PricingError(f"'{code}' is priced by area, and this request gives none")
        quantity = spec.quantity(asked, data.area_sqft)
        if quantity <= 0:
            continue
        lines.append(
            LineItem(
                f"extra:{code}",
                spec.label_fr,
                spec.label_en,
                spec.cents * quantity,
                quantity=None if spec.unit == "flat" else quantity,
                unit_fr=spec.per_fr,
                unit_en=spec.per_en,
            )
        )

    # Order matters, and it used to be wrong. The minimum was applied to the
    # subtotal and the discount taken off afterwards, so a weekly client on a
    # 120 $ minimum was quoted 102 $ -- the discount ate straight through the
    # floor that exists to make dispatching a crew worth it, and the discount was
    # computed on the floor rather than on the work, inflating it too.
    #
    # The floor is the LAST thing that happens, because it is a promise about the
    # price the client pays, not about the arithmetic behind it.
    subtotal = sum(item.amount_cents for item in lines)

    pct = card.frequency_discount_pct.get(data.frequency, Decimal(0))
    discount = _cents(Decimal(subtotal) * pct / 100) if pct else 0

    # Reported as its own number rather than folded into the total: a client
    # reading lines − discount and landing somewhere else is a client on the
    # phone asking why.
    minimum_adjustment = max(0, card.minimum_visit_cents - (subtotal - discount))

    return Breakdown(
        lines=tuple(lines),
        subtotal_cents=subtotal,
        discount_cents=discount,
        minimum_adjustment_cents=minimum_adjustment,
        total_cents=subtotal - discount + minimum_adjustment,
        estimated_minutes=minutes,
        # Residential standard homes get a firm price; commercial is always reviewed.
        is_firm=data.audience == "residential",
        rate_card_version=card.version,
    )
