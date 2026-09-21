from dataclasses import replace
from decimal import Decimal

import pytest

from app.pricing import PricingInput, RateCardData, price_request
from app.pricing.engine import PricingError
from app.pricing.models import ExtraSpec, ModifierOption, ModifierSpec

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
    extras={
        "fridge": ExtraSpec("flat", 2500, "Intérieur du réfrigérateur", "Inside the fridge"),
        "oven": ExtraSpec("flat", 3000, "Intérieur du four", "Inside the oven"),
        "windows": ExtraSpec("each", 400, "Vitres intérieures", "Interior windows",
                             "par fenêtre", "per window"),
        "baseboards": ExtraSpec("per_100sqft", 1400, "Plinthes", "Baseboards",
                                "par 100 pi²", "per 100 sq ft"),
    },
    frequency_discount_pct={"biweekly": Decimal(10), "weekly": Decimal(15)},
    night_access_multiplier=Decimal("1.15"),
)


def test_every_line_is_written_in_both_languages():
    """The quote page renders the label for its own locale, so an English visitor
    never reads a French line item beside an English price."""
    out = price_request(
        PricingInput(
            audience="residential", property_type="house", bedrooms=3, bathrooms=2,
            area_sqft=2400, extras={"fridge": 1},
        ),
        CARD,
    )
    assert "Intérieur du réfrigérateur" in [line.label_fr for line in out.lines]
    assert "Inside the fridge" in [line.label_en for line in out.lines]
    for line in out.lines:
        assert line.label_fr and line.label_en, line.code
        assert line.label_fr != line.label_en, line.code


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
            extras={"fridge": 1},
        ),
        CARD,
    )
    # 18000 base + 5 blocks * 900 + 2500 fridge = 25000, minus 10 percent
    assert out.subtotal_cents == 25000
    assert out.discount_cents == 2500
    assert out.total_cents == 22500


def test_a_base_price_above_the_minimum_is_left_alone():
    """Named for what it actually checks. It used to be called
    `test_minimum_visit_applies`, on a 140 $ base against a 120 $ minimum: it
    passed just as happily with the floor deleted, which is how the floor bugs
    below reached production green."""
    out = price_request(
        PricingInput(audience="residential", property_type="condo", bedrooms=2, bathrooms=1), CARD
    )
    assert out.total_cents == 14000
    assert out.minimum_adjustment_cents == 0


def test_the_minimum_visit_is_the_last_word():
    """The floor is a promise about what the client pays, so it comes AFTER the
    recurring discount.

    This is the bug it guards: a small weekly job used to be quoted at
    120 $ − 15 % = 102 $, under the very minimum that makes sending a crew worth
    doing. The discount ate through the floor."""
    small = PricingInput(
        audience="commercial", property_type="office", area_sqft=500,
        services=("office_cleaning",), frequency="weekly",
    )
    out = price_request(small, CARD)

    # 500 pi² at 6 min/100 = 30 min = 22,50 $, plus 15 $ travel = 37,50 $ of work.
    assert out.subtotal_cents == 3750
    assert out.discount_cents == 563          # 15 % of the WORK, not of the floor
    assert out.minimum_adjustment_cents == 12000 - (3750 - 563)   # 88,13 $ back up to the floor
    assert out.total_cents == 12000                               # never under the minimum


def test_the_breakdown_adds_up():
    """lines − discount + minimum = total, on every quote. A client reading the
    lines and landing somewhere else is a client on the phone."""
    for data in (
        PricingInput(audience="residential", property_type="house", bedrooms=3, bathrooms=2,
                     area_sqft=2400, frequency="weekly", extras={"windows": 6, "fridge": 1}),
        PricingInput(audience="commercial", property_type="office", area_sqft=500,
                     services=("office_cleaning",), frequency="weekly"),
        PricingInput(audience="commercial", property_type="office", area_sqft=4000, restrooms=4,
                     services=("office_cleaning",), night_access=True),
    ):
        out = price_request(data, CARD)
        assert out.subtotal_cents == sum(line.amount_cents for line in out.lines)
        assert out.total_cents == (
            out.subtotal_cents - out.discount_cents + out.minimum_adjustment_cents
        )
        assert out.total_cents >= CARD.minimum_visit_cents


def test_the_discount_is_taken_on_the_work_not_on_the_floor():
    """The floor used to be applied first, so a 37,50 $ job was discounted as if
    it were a 120 $ one -- a bigger discount, taken off a number the client never
    saw."""
    out = price_request(
        PricingInput(audience="commercial", property_type="office", area_sqft=500,
                     services=("office_cleaning",), frequency="weekly"),
        CARD,
    )
    assert out.discount_cents == 563
    assert out.discount_cents != 1800  # 15 % of the 120 $ minimum


def test_an_area_priced_extra_without_an_area_is_refused():
    """Silently it charged nothing: the visitor ticked the baseboards, paid for
    none of them, and the crew did them for free."""
    with pytest.raises(PricingError, match="priced by area"):
        price_request(
            PricingInput(audience="residential", property_type="house",
                         bedrooms=3, bathrooms=2, extras={"baseboards": 1}),
            CARD,
        )


def test_a_commercial_request_with_no_service_is_not_guessed():
    """It used to fall back to office cleaning, so a warehouse came back priced
    as an office with no line saying so."""
    with pytest.raises(PricingError, match="no service"):
        price_request(
            PricingInput(audience="commercial", property_type="industrial", area_sqft=8000),
            CARD,
        )


def test_restrooms_alone_are_a_job():
    """A contract that is only restrooms is real work. The minutes check used to
    run before they were counted, so it was refused.

    `floor_stripping_waxing` is deliberately a service this card has no rate for:
    the per-area minutes come to zero and the restrooms are all there is."""
    out = price_request(
        PricingInput(audience="commercial", property_type="building", area_sqft=3000,
                     restrooms=6, services=("floor_stripping_waxing",)),
        CARD,
    )
    # 6 restrooms x 12 min = 72 min at 45 $/h = 54 $, plus 15 $ travel.
    assert out.estimated_minutes == 72
    assert out.subtotal_cents == 5400 + 1500


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


def test_a_countable_extra_multiplies_by_the_quantity():
    """The bug this whole change exists for: a flat price meant 40 $ for the
    windows whether the home had four of them or forty."""
    six = price_request(
        PricingInput(audience="residential", property_type="condo", bedrooms=3,
                     bathrooms=2, extras={"windows": 6}),
        CARD,
    )
    sixty = price_request(
        PricingInput(audience="residential", property_type="condo", bedrooms=3,
                     bathrooms=2, extras={"windows": 60}),
        CARD,
    )
    line_six = next(line for line in six.lines if line.code == "extra:windows")
    line_sixty = next(line for line in sixty.lines if line.code == "extra:windows")
    assert line_six.amount_cents == 6 * 400
    assert line_sixty.amount_cents == 60 * 400
    assert line_six.quantity == 6
    assert line_six.unit_fr == "par fenêtre"


def test_a_flat_extra_ignores_the_quantity():
    once = price_request(
        PricingInput(audience="residential", property_type="condo", bedrooms=3,
                     bathrooms=2, extras={"oven": 1}),
        CARD,
    )
    many = price_request(
        PricingInput(audience="residential", property_type="condo", bedrooms=3,
                     bathrooms=2, extras={"oven": 9}),
        CARD,
    )
    assert once.total_cents == many.total_cents
    line = next(line for line in once.lines if line.code == "extra:oven")
    assert line.quantity is None, "a flat extra should not advertise a quantity"


def test_a_per_area_extra_is_derived_from_the_area_not_the_visitor():
    out = price_request(
        PricingInput(audience="residential", property_type="condo", bedrooms=3,
                     bathrooms=2, area_sqft=1450, extras={"baseboards": 999}),
        CARD,
    )
    line = next(line for line in out.lines if line.code == "extra:baseboards")
    assert line.quantity == 15, "1450 sq ft is 15 blocks of 100, rounded up"
    assert line.amount_cents == 15 * 1400


def test_a_quantity_of_zero_bills_nothing():
    out = price_request(
        PricingInput(audience="residential", property_type="condo", bedrooms=3,
                     bathrooms=2, extras={"windows": 0}),
        CARD,
    )
    assert not [line for line in out.lines if line.code.startswith("extra:")]


def test_an_extra_the_card_does_not_price_is_ignored():
    out = price_request(
        PricingInput(audience="residential", property_type="condo", bedrooms=3,
                     bathrooms=2, extras={"helicopter_pad": 3}),
        CARD,
    )
    assert not [line for line in out.lines if line.code.startswith("extra:")]


def test_a_home_bigger_than_the_grid_is_not_squeezed_into_it():
    """It used to clamp to 5 bedrooms, so an eight-bedroom house was quoted at
    the five-bedroom price. That is not a discount, it is the wrong job."""
    with pytest.raises(PricingError, match="outside the grid"):
        price_request(
            PricingInput(audience="residential", property_type="house",
                         bedrooms=8, bathrooms=4, area_sqft=5200),
            CARD,
        )


def test_a_studio_is_quoted_by_a_person():
    """`bedrooms` accepts 0, the grid starts at 1. Rather than reading 0 as 1,
    say we cannot price it -- which the form already renders as "chiffré à la
    main" rather than as an error."""
    with pytest.raises(PricingError, match="outside the grid"):
        price_request(
            PricingInput(audience="residential", property_type="condo",
                         bedrooms=0, bathrooms=1, area_sqft=480),
            CARD,
        )


# A card with modifiers, kept apart from CARD so the other tests stay unaffected.
MOD_CARD = replace(
    CARD,
    max_residential_multiplier=Decimal("2.5"),
    residential_modifiers={
        "premier_menage": ModifierSpec(
            label_fr="Est-ce un premier ménage ?", label_en="Is this a first clean?",
            short_fr="Premier ménage", short_en="First clean",
            options=(
                ModifierOption("no", "Non", "No"),
                ModifierOption("yes", "Oui", "Yes", multiplier=Decimal("1.4")),
            ),
        ),
        "etat": ModifierSpec(
            label_fr="État du logement", label_en="Condition",
            short_fr="État", short_en="Condition",
            options=(
                ModifierOption("normal", "Normal", "Normal"),
                ModifierOption("tres_sale", "Très sale", "Very dirty",
                               multiplier=Decimal("1.45")),
            ),
        ),
        "animaux": ModifierSpec(
            label_fr="Animaux", label_en="Pets", short_fr="Animaux", short_en="Pets",
            options=(
                ModifierOption("none", "Aucun", "None"),
                ModifierOption("one", "Un", "One", cents=1000),
            ),
        ),
    },
)

PLAIN = PricingInput(
    audience="residential", property_type="house",
    bedrooms=3, bathrooms=2, area_sqft=2400,
)


def test_a_modifier_nobody_answered_changes_nothing():
    """Everything ships neutral: a card can carry modifiers for weeks before a
    visitor is ever asked, and the price must not move."""
    assert price_request(PLAIN, MOD_CARD).total_cents == price_request(PLAIN, CARD).total_cents


def test_the_free_answer_is_free():
    answered = replace(PLAIN, modifiers={"premier_menage": "no", "etat": "normal"})
    assert price_request(answered, MOD_CARD).total_cents == price_request(PLAIN, CARD).total_cents


def test_a_multiplier_scales_the_work_and_says_why():
    work = price_request(PLAIN, CARD).subtotal_cents
    out = price_request(replace(PLAIN, modifiers={"premier_menage": "yes"}), MOD_CARD)

    line = next(item for item in out.lines if item.code == "modifiers")
    assert line.amount_cents == round(work * Decimal("1.4")) - work
    assert line.label_fr == "Majoration — Premier ménage : Oui"
    assert line.unit_fr == "× 1.4"
    assert out.subtotal_cents == sum(item.amount_cents for item in out.lines)


def test_multipliers_compound():
    work = price_request(PLAIN, CARD).subtotal_cents
    out = price_request(
        replace(PLAIN, modifiers={"premier_menage": "yes", "etat": "tres_sale"}), MOD_CARD
    )
    line = next(item for item in out.lines if item.code == "modifiers")
    # 1.4 x 1.45, not 1.4 + 0.45: a first clean of a filthy home is both at once.
    assert line.amount_cents == round(work * Decimal("1.4") * Decimal("1.45")) - work


def test_the_cap_bites_and_the_line_says_so():
    """Uncapped compounding runs away. The ceiling is the card's, and when it
    applies the client can see that it did."""
    capped_card = replace(MOD_CARD, max_residential_multiplier=Decimal("1.6"))
    work = price_request(PLAIN, CARD).subtotal_cents
    out = price_request(
        replace(PLAIN, modifiers={"premier_menage": "yes", "etat": "tres_sale"}), capped_card
    )
    line = next(item for item in out.lines if item.code == "modifiers")
    assert line.amount_cents == round(work * Decimal("1.6")) - work
    assert "plafonné" in line.label_fr
    assert "capped" in line.label_en


def test_an_amount_is_added_after_the_multiplying_and_never_compounds():
    """Two additive answers must not multiply each other, and a multiplier must
    not inflate them: 10 $ for a pet is 10 $ whatever else is true of the job."""
    plain = price_request(replace(PLAIN, modifiers={"animaux": "one"}), MOD_CARD)
    with_mult = price_request(
        replace(PLAIN, modifiers={"animaux": "one", "premier_menage": "yes"}), MOD_CARD
    )
    pet_plain = next(i for i in plain.lines if i.code == "modifier:animaux")
    pet_mult = next(i for i in with_mult.lines if i.code == "modifier:animaux")
    assert pet_plain.amount_cents == pet_mult.amount_cents == 1000
    assert pet_plain.label_fr == "Animaux : Un"


def test_modifiers_do_not_touch_extras():
    """Decision 2 of the plan: a per-unit extra already scales with its quantity,
    so multiplying it again double-counts."""
    extras = {"windows": 6}
    without = price_request(replace(PLAIN, extras=extras), MOD_CARD)
    with_mod = price_request(
        replace(PLAIN, extras=extras, modifiers={"premier_menage": "yes"}), MOD_CARD
    )
    line_a = next(i for i in without.lines if i.code == "extra:windows")
    line_b = next(i for i in with_mod.lines if i.code == "extra:windows")
    assert line_a.amount_cents == line_b.amount_cents


def test_an_unknown_modifier_or_answer_is_ignored():
    """A stale page, or a tampered payload, must not be able to invent a price."""
    out = price_request(
        replace(PLAIN, modifiers={"premier_menage": "peut_etre", "inconnu": "yes"}), MOD_CARD
    )
    assert out.total_cents == price_request(PLAIN, CARD).total_cents


def test_a_commercial_request_is_not_modified():
    """The modifiers are residential: they describe a home."""
    commercial = PricingInput(
        audience="commercial", property_type="office", area_sqft=2000,
        services=("office_cleaning",), modifiers={"premier_menage": "yes"},
    )
    assert not [i for i in price_request(commercial, MOD_CARD).lines if i.code == "modifiers"]
