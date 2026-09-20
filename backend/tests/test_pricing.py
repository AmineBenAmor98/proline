from decimal import Decimal

import pytest

from app.pricing import PricingInput, RateCardData, price_request
from app.pricing.engine import PricingError

CARD = RateCardData(
    version="test-2026-01",
    hourly_rate_cents=4500,
    minimum_visit_cents=12000,
    travel_cents=1500,
    residential_base_cents={"3br_2ba": 18000, "2br_1ba": 14000},
    residential_area_cents_per_100sqft=900,
    residential_area_allowance_sqft=1000,
    minutes_per_100sqft={"office_cleaning": 6, "common_areas": 4},
    minutes_per_restroom=12,
    extras_cents={"fridge": 2500, "oven": 3000},
    frequency_discount_pct={"biweekly": Decimal(10), "weekly": Decimal(15)},
    night_access_multiplier=Decimal("1.15"),
)


def test_residential_extras_carry_a_written_french_label():
    out = price_request(
        PricingInput(
            audience="residential", property_type="house", bedrooms=3, bathrooms=2,
            extras=("fridge",),
        ),
        CARD,
    )
    labels = [line.label_fr for line in out.lines]
    assert "Intérieur du réfrigérateur" in labels


def test_residential_reports_no_invented_minutes():
    out = price_request(
        PricingInput(audience="residential", property_type="house", bedrooms=3, bathrooms=2), CARD
    )
    assert out.estimated_minutes is None


def test_residential_base_price():
    out = price_request(
        PricingInput(audience="residential", property_type="house", bedrooms=3, bathrooms=2), CARD
    )
    assert out.total_cents == 18000
    assert out.is_firm is True


def test_residential_area_surcharge_and_discount():
    out = price_request(
        PricingInput(
            audience="residential",
            property_type="house",
            bedrooms=3,
            bathrooms=2,
            area_sqft=1450,
            frequency="biweekly",
            extras=("fridge",),
        ),
        CARD,
    )
    # 18000 base + 5 blocks * 900 + 2500 fridge = 25000, minus 10 percent
    assert out.subtotal_cents == 25000
    assert out.discount_cents == 2500
    assert out.total_cents == 22500


def test_minimum_visit_applies():
    out = price_request(
        PricingInput(audience="residential", property_type="condo", bedrooms=2, bathrooms=1), CARD
    )
    assert out.total_cents == 14000


def test_commercial_uses_minutes_and_rate():
    out = price_request(
        PricingInput(
            audience="commercial",
            property_type="office",
            area_sqft=2000,
            restrooms=3,
            services=("office_cleaning",),
        ),
        CARD,
    )
    # 20 blocks * 6 min + 3 * 12 = 156 min -> 2.6h * 4500 = 11700, + 1500 travel
    assert out.estimated_minutes == 156
    assert out.total_cents == 13200
    assert out.is_firm is False


def test_commercial_night_access_costs_more():
    # Area large enough that the minimum-visit floor does not mask the difference.
    day = price_request(
        PricingInput(audience="commercial", property_type="office", area_sqft=8000,
                     services=("office_cleaning",)),
        CARD,
    )
    night = price_request(
        PricingInput(audience="commercial", property_type="office", area_sqft=8000,
                     services=("office_cleaning",), night_access=True),
        CARD,
    )
    assert night.total_cents > day.total_cents


def test_missing_rooms_is_an_error_not_a_guess():
    with pytest.raises(PricingError):
        price_request(PricingInput(audience="residential", property_type="house"), CARD)
