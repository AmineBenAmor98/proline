"""Request and response shapes for the public quote flow.

These are the contract the API enforces.

Extras need no code to add one: they live on the rate card with their own labels
and unit, the form reads them from `GET /api/quotes/form-config`, and the engine
prices whatever is there. Services are not there yet -- adding a service code
still means `app/models/enums.py`, the grid's `minutes_per_100sqft`, the label
table in `frontend/js/admin-common.js` and the checkboxes in
`frontend/soumission.html`.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.models.enums import (
    AUDIENCE_BY_PROPERTY_TYPE,
    Audience,
    Frequency,
    PropertyType,
    RequestStatus,
    ServiceCode,
)
from app.schemas.rate_card import CODE_RE

# code -> quantity. The codes are the rate card's, so they take the same shape
# here: `POST /api/quotes` is public and unauthenticated, and without this an
# anonymous caller could write arbitrary strings into the database and onto the
# operator's screen. The engine already ignores codes the card does not know;
# this stops them being stored at all.
ExtrasIn = Annotated[
    dict[Annotated[str, Field(pattern=CODE_RE.pattern)], Annotated[int, Field(ge=0, le=500)]],
    Field(default_factory=dict, max_length=40),
]


# code -> the chosen option's value, both drawn from the card. Bounded the same
# way extras are, and for the same reason: `POST /api/quotes` is public.
ModifiersIn = Annotated[
    dict[
        Annotated[str, Field(pattern=CODE_RE.pattern)],
        Annotated[str, Field(pattern=CODE_RE.pattern)],
    ],
    Field(default_factory=dict, max_length=20),
]


class PropertyIn(BaseModel):
    property_type: PropertyType
    area_sqft: Annotated[int, Field(ge=100, le=1_000_000)] | None = None
    bedrooms: Annotated[int, Field(ge=0, le=20)] | None = None
    bathrooms: Annotated[int, Field(ge=0, le=20)] | None = None
    floors: Annotated[int, Field(ge=1, le=100)] | None = None
    restrooms: Annotated[int, Field(ge=0, le=200)] | None = None
    address_line: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=120)
    borough: str | None = Field(default=None, max_length=120)
    postal_code: str | None = Field(default=None, max_length=12)


class ContactIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=160)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    company: str | None = Field(default=None, max_length=160)
    locale: str = Field(default="fr", pattern="^(fr|en)$")
    preferred_contact: str | None = Field(default=None, pattern="^(email|phone)$")
    consent_given: bool = False

    @model_validator(mode="after")
    def one_channel_required(self) -> ContactIn:
        if not self.email and not self.phone:
            raise ValueError("an email address or a phone number is required")
        return self


class Attribution(BaseModel):
    utm_source: str | None = None
    utm_medium: str | None = None
    utm_campaign: str | None = None
    utm_term: str | None = None
    gclid: str | None = None
    landing_path: str | None = None


class QuoteRequestIn(BaseModel):
    audience: Audience
    property: PropertyIn
    services: list[ServiceCode] = Field(default_factory=list, max_length=12)
    frequency: Frequency = Frequency.one_time
    # A flat extra is present with any quantity; the rate card decides whether
    # the number means anything.
    extras: ExtrasIn = Field(default_factory=dict)
    modifiers: ModifiersIn = Field(default_factory=dict)
    desired_start: date | None = None
    access_notes: str | None = Field(default=None, max_length=2000)
    night_access: bool = False
    contact: ContactIn
    attribution: Attribution = Field(default_factory=Attribution)
    # Honeypot: real visitors never fill this.
    website: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def audience_matches_property_type(self) -> QuoteRequestIn:
        """A house is never a commercial request. Reject the contradiction rather
        than storing a row nobody can price."""
        expected = AUDIENCE_BY_PROPERTY_TYPE[self.property.property_type]
        if self.audience is not expected:
            raise ValueError(
                f"property type '{self.property.property_type.value}' is "
                f"{expected.value}, not {self.audience.value}"
            )
        return self


class ExtraOffer(BaseModel):
    """One extra, as the quote form should render it."""

    code: str
    unit: str
    label_fr: str
    label_en: str
    per_fr: str
    per_en: str
    cents: int


class ModifierOptionOut(BaseModel):
    value: str
    label_fr: str
    label_en: str


class ModifierOffer(BaseModel):
    """One question the form should ask, as the card defines it.

    The prices are deliberately absent: a visitor picking "très sale" does not
    need to be told it multiplies by 1.45, and the running total already shows
    what it did. The rate grid stays on the server.
    """

    code: str
    label_fr: str
    label_en: str
    help_fr: str
    help_en: str
    options: list[ModifierOptionOut]


class PhotoZoneOffer(BaseModel):
    """One option in the per-photo room selector, already in both languages.

    Defined up here, above FormConfig, because Pydantic resolves a model's
    annotations when the class is built -- a name defined further down the file
    is not there yet, `from __future__ import annotations` or not.
    """

    value: str
    label_fr: str
    label_en: str


class FormConfig(BaseModel):
    """What the active rate card can price, and therefore what the form may ask.

    The form reads this instead of hard-coding a list of extras, and asks only
    about the room combinations the card has a price for. An input nothing can
    use is an input we do not collect -- and one we collect for a person rather
    than for the engine (`floors`, the address, the desired start) is shown to
    that person in /admin, not buried in a column nobody reads.
    """

    rate_card_version: str
    residential_online_pricing: bool
    extras: list[ExtraOffer]
    modifiers: list[ModifierOffer]
    # The bedroom/bathroom combinations the card actually has a price for, as
    # "3br_2ba". This used to be a bedrooms_max and a bathrooms_max, which is a
    # different and untrue statement: a card priced for 5br_3ba and 1br_1ba would
    # advertise fifteen combinations and price two of them. Nothing read those
    # two fields, so the form offered every combination and sent seven of them
    # into "a person will call you" after promising a price.
    residential_cells: list[str]
    # Photos. The form asks whether to show the control at all rather than
    # deciding for itself, so switching PHOTOS_DIR off in .env takes the input
    # off the page too -- one switch, not two places to remember.
    photos_enabled: bool = False
    photo_max_count: int = 0
    # Only the zones that make sense for the audience being asked. One enum in
    # the database, two lists on the forms: a triplex has no workstations.
    photo_zones_residential: list[PhotoZoneOffer] = []
    photo_zones_commercial: list[PhotoZoneOffer] = []


class PriceLine(BaseModel):
    code: str
    label_fr: str
    label_en: str
    amount_cents: int
    # Set for anything billed by quantity, so the breakdown can read
    # "Vitres intérieures  x 6 par fenêtre" instead of an unexplained 24 $.
    quantity: int | None = None
    unit_fr: str = ""
    unit_en: str = ""


class PriceOut(BaseModel):
    lines: list[PriceLine]
    # The lines added up. `total = subtotal - discount + minimum_adjustment`.
    subtotal_cents: int
    discount_cents: int
    minimum_adjustment_cents: int = 0
    total_cents: int
    estimated_minutes: int | None
    is_firm: bool
    rate_card_version: str


class QuoteRequestOut(BaseModel):
    id: str
    status: RequestStatus
    audience: Audience
    # Present for residential; null for commercial, which is quoted within 24h.
    price: PriceOut | None = None
    message_fr: str
    message_en: str
    # Authorises uploading photos to THIS request, for an hour. Null when photo
    # storage is switched off, and null for a honeypot submission -- which gets
    # a cheerful 201 and no way to write anything to disk.
    photo_upload_token: str | None = None


class PhotoOut(BaseModel):
    """A stored photo, as the admin sees it. Never the bytes -- those come from
    the authenticated photo endpoint, one request each."""

    id: str
    zone: str
    zone_label_fr: str
    bytes_size: int | None = None
    created_at: datetime


class PriceDraftIn(BaseModel):
    """Same shape as a submission minus contact: prices without saving anything."""

    audience: Audience
    property: PropertyIn
    services: list[ServiceCode] = Field(default_factory=list, max_length=12)
    frequency: Frequency = Frequency.one_time
    extras: ExtrasIn = Field(default_factory=dict)
    modifiers: ModifiersIn = Field(default_factory=dict)
    night_access: bool = False

    @model_validator(mode="after")
    def audience_matches_property_type(self) -> PriceDraftIn:
        expected = AUDIENCE_BY_PROPERTY_TYPE[self.property.property_type]
        if self.audience is not expected:
            raise ValueError(
                f"property type '{self.property.property_type.value}' is "
                f"{expected.value}, not {self.audience.value}"
            )
        return self
