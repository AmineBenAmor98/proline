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

CENTS = Annotated[int, Field(ge=0, le=2_000_00)]
KEY_RE = re.compile(r"^[1-5]br_[1-4]ba$")


class GridIn(BaseModel):
    """The JSONB half of a rate card."""

    residential_base_cents: dict[str, CENTS] = Field(default_factory=dict)
    residential_area_allowance_sqft: Annotated[int, Field(ge=0, le=20_000)] = 1000
    residential_area_cents_per_100sqft: CENTS = 0
    minutes_per_100sqft: dict[str, Annotated[int, Field(ge=0, le=600)]] = Field(default_factory=dict)
    minutes_per_restroom: Annotated[int, Field(ge=0, le=600)] = 12
    extras_cents: dict[str, CENTS] = Field(default_factory=dict)
    frequency_discount_pct: dict[str, Annotated[Decimal, Field(ge=0, le=60)]] = Field(
        default_factory=dict
    )
    night_access_multiplier: Annotated[Decimal, Field(ge=1, le=3)] = Decimal("1.0")

    @model_validator(mode="after")
    def keys_are_known(self) -> "GridIn":
        bad = [key for key in self.residential_base_cents if not KEY_RE.match(key)]
        if bad:
            raise ValueError(f"unknown residential grid key(s): {', '.join(sorted(bad))}")
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
    def base_prices_clear_the_minimum(self) -> "RateCardIn":
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
                f"base price below the {self.minimum_visit_cents / 100:.2f} $ minimum visit: {listed}"
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
    label: str
    audience: str
    property_type: str
    area_sqft: int | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    restrooms: int | None = None
    services: list[str] = Field(default_factory=list)
    extras: list[str] = Field(default_factory=list)
    frequency: str = "one_time"
    night_access: bool = False


class ScenarioResult(BaseModel):
    label: str
    active_total_cents: int | None
    draft_total_cents: int | None
    draft_lines: list[dict] = Field(default_factory=list)
    error: str | None = None


class PreviewIn(BaseModel):
    card: RateCardIn
    scenarios: list[Scenario] = Field(default_factory=list, max_length=12)


class PreviewOut(BaseModel):
    results: list[ScenarioResult]


class OnlinePricingIn(BaseModel):
    enabled: bool
