"""Shapes for the admin rate card screen.

Money crosses the wire in cents, as everywhere else. The bounds below are not
opinions about what Proline should charge: they are there so a decimal slip
(18500 typed where 1850 was meant) is refused by the server rather than quoted
to the next visitor.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field, model_validator

from app.models.enums import (
    AUDIENCE_BY_PROPERTY_TYPE,
    Audience,
    Frequency,
    PropertyType,
    ServiceCode,
)

CENTS = Annotated[int, Field(ge=0, le=2_000_00)]
KEY_RE = re.compile(r"^[1-5]br_[1-4]ba$")
# An extra code is a stable key: it is what a stored request and the quote form
# agree on, so it stays lower-case ASCII whatever the extra is called today.
CODE_RE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")


UNITS = ("flat", "each", "per_100sqft")


class ExtraIn(BaseModel):
    """One extra on the rate card.

    `unit` is the whole point: it says what the price is per, so six windows and
    sixty windows stop costing the same. The labels live here too, which is why
    neither the engine nor the quote form carries a copy of them any more.
    """

    unit: str = Field(default="flat", pattern=f"^({'|'.join(UNITS)})$")
    cents: CENTS = 0
    label_fr: str = Field(min_length=1, max_length=80)
    label_en: str = Field(min_length=1, max_length=80)
    per_fr: str = Field(default="", max_length=40)
    per_en: str = Field(default="", max_length=40)

    @model_validator(mode="after")
    def a_countable_extra_says_what_it_counts(self) -> ExtraIn:
        """Anything not flat multiplies, and a multiplied line has to say by what.

        The breakdown reads "Vitres intérieures × 6 par fenêtre"; without the last
        two words it reads "× 6" and the client has to guess.
        """
        if self.unit != "flat" and not (self.per_fr and self.per_en):
            raise ValueError(
                f"an extra billed '{self.unit}' needs a unit label in both languages "
                "(for example 'par fenêtre' / 'per window')"
            )
        if self.unit == "flat" and (self.per_fr or self.per_en):
            raise ValueError("a flat extra is not billed per anything; clear the unit label")
        return self


class ModifierOptionIn(BaseModel):
    """One answer, and what it does to the price."""

    value: Annotated[str, Field(pattern=CODE_RE.pattern)]
    label_fr: str = Field(min_length=1, max_length=80)
    label_en: str = Field(min_length=1, max_length=80)
    # 0.5 to 3: a modifier that halves a price or triples it is already extreme;
    # anything outside is a decimal slip, which is what these bounds are for.
    multiplier: Annotated[Decimal, Field(ge="0.5", le=3)] = Decimal("1")
    cents: CENTS = 0


class ModifierIn(BaseModel):
    """A question about the job whose answer changes the price."""

    label_fr: str = Field(min_length=1, max_length=80)
    label_en: str = Field(min_length=1, max_length=80)
    help_fr: str = Field(default="", max_length=200)
    help_en: str = Field(default="", max_length=200)
    # What the quote line calls it. Falls back to the question when empty.
    short_fr: str = Field(default="", max_length=40)
    short_en: str = Field(default="", max_length=40)
    # Position in the questionnaire; JSONB does not keep key order.
    sort: Annotated[int, Field(ge=0, le=999)] = 100
    options: list[ModifierOptionIn] = Field(min_length=2, max_length=8)

    @model_validator(mode="after")
    def options_are_distinct_and_one_is_free(self) -> ModifierIn:
        values = [option.value for option in self.options]
        if len(set(values)) != len(values):
            raise ValueError("two options share a value")
        # Every question needs an answer that costs nothing, or there is no way
        # to say "none of this applies" and the modifier becomes a tax.
        if not any(option.multiplier == 1 and option.cents == 0 for option in self.options):
            raise ValueError(
                "one option has to be free (multiplier 1, 0 $), so a visitor can "
                "answer that it does not apply"
            )
        return self


class GridIn(BaseModel):
    """The JSONB half of a rate card."""

    residential_base_cents: dict[str, CENTS] = Field(default_factory=dict)
    residential_area_allowance_sqft: Annotated[int, Field(ge=0, le=20_000)] = 1000
    residential_area_cents_per_100sqft: CENTS = 0
    minutes_per_100sqft: dict[str, Annotated[int, Field(ge=0, le=600)]] = Field(
        default_factory=dict
    )
    minutes_per_restroom: Annotated[int, Field(ge=0, le=600)] = 12
    extras: dict[str, ExtraIn] = Field(default_factory=dict)
    residential_modifiers: dict[str, ModifierIn] = Field(default_factory=dict)
    max_residential_multiplier: Annotated[Decimal, Field(ge=1, le=5)] = Decimal("2.5")
    frequency_discount_pct: dict[str, Annotated[Decimal, Field(ge=0, le=60)]] = Field(
        default_factory=dict
    )
    night_access_multiplier: Annotated[Decimal, Field(ge=1, le=3)] = Decimal("1.0")

    @model_validator(mode="after")
    def keys_are_known(self) -> GridIn:
        bad = [key for key in self.residential_base_cents if not KEY_RE.match(key)]
        if bad:
            raise ValueError(f"unknown residential grid key(s): {', '.join(sorted(bad))}")
        bad = [key for key in self.extras if not CODE_RE.match(key)]
        if bad:
            raise ValueError(f"unknown extra code(s): {', '.join(sorted(bad))}")
        bad = [key for key in self.residential_modifiers if not CODE_RE.match(key)]
        if bad:
            raise ValueError(f"unknown modifier code(s): {', '.join(sorted(bad))}")
        allowed_freq = {"weekly", "biweekly", "monthly", "one_time", "to_discuss"}
        bad = set(self.frequency_discount_pct) - allowed_freq
        if bad:
            raise ValueError(f"unknown frequency: {', '.join(sorted(bad))}")
        return self


class RateCardIn(BaseModel):
    """A draft about to be published as a new version."""

    hourly_rate_cents: Annotated[int, Field(ge=1000, le=50_000)]
    minimum_visit_cents: Annotated[int, Field(ge=0, le=200_000)]
    travel_cents: Annotated[int, Field(ge=0, le=50_000)]
    grid: GridIn

    @model_validator(mode="after")
    def base_prices_clear_the_minimum(self) -> RateCardIn:
        """A base price under the minimum visit is not wrong, but it is almost
        always a typo: the minimum would silently swallow it."""
        low = {
            key: cents
            for key, cents in self.grid.residential_base_cents.items()
            if cents < self.minimum_visit_cents
        }
        if low:
            listed = ", ".join(f"{key} ({cents / 100:.2f} $)" for key, cents in sorted(low.items()))
            raise ValueError(
                f"base price below the {self.minimum_visit_cents / 100:.2f} $ "
                f"minimum visit: {listed}"
            )
        return self


class RateCardOut(BaseModel):
    version: str
    effective_from: date
    effective_to: date | None
    is_active: bool
    residential_online_pricing: bool
    hourly_rate_cents: int
    minimum_visit_cents: int
    travel_cents: int
    grid: dict
    priced_requests: int = 0


class RateCardList(BaseModel):
    items: list[RateCardOut]


class Scenario(BaseModel):
    """A test case the admin prices a draft against.

    `audience` and `property_type` were bare strings with no cross-check, and the
    engine treats anything that is not "residential" as commercial -- so a typo
    in a saved scenario silently priced a house on the commercial minute grid and
    the admin compared two wrong numbers with confidence.
    """

    label: str
    audience: Audience
    property_type: PropertyType
    area_sqft: int | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    restrooms: int | None = None
    services: list[ServiceCode] = Field(default_factory=list, max_length=12)
    # code -> quantity, the same shape a visitor's request sends. A preview that
    # could only say "windows: yes" would never catch a per-unit decimal slip.
    extras: dict[
        Annotated[str, Field(pattern=CODE_RE.pattern)], Annotated[int, Field(ge=0, le=500)]
    ] = Field(default_factory=dict, max_length=40)
    # The answers, so a scenario can exercise a modifier. Without these, changing
    # a multiplier moved no number in the tester -- the one screen whose job is
    # catching that before a visitor sees it.
    modifiers: dict[
        Annotated[str, Field(pattern=CODE_RE.pattern)],
        Annotated[str, Field(pattern=CODE_RE.pattern)],
    ] = Field(default_factory=dict, max_length=20)
    frequency: Frequency = Frequency.one_time
    night_access: bool = False

    @model_validator(mode="after")
    def audience_matches_property_type(self) -> Scenario:
        expected = AUDIENCE_BY_PROPERTY_TYPE[self.property_type]
        if self.audience is not expected:
            raise ValueError(
                f"scenario '{self.label}': a {self.property_type.value} is "
                f"{expected.value}, not {self.audience.value}"
            )
        return self


class ScenarioResult(BaseModel):
    label: str
    active_total_cents: int | None
    draft_total_cents: int | None
    draft_lines: list[dict] = Field(default_factory=list)
    # The tester listed only the lines, so a scenario with a recurring discount
    # showed four numbers summing to 285,00 $ under a total of 256,50 $ and
    # nothing accounting for the difference. Whoever is about to publish a price
    # has to be able to add the panel up.
    draft_subtotal_cents: int | None = None
    draft_discount_cents: int = 0
    draft_minimum_adjustment_cents: int = 0
    error: str | None = None


class PreviewIn(BaseModel):
    card: RateCardIn
    scenarios: list[Scenario] = Field(default_factory=list, max_length=12)


class PreviewOut(BaseModel):
    results: list[ScenarioResult]


class OnlinePricingIn(BaseModel):
    enabled: bool
