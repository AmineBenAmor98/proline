from __future__ import annotations

from datetime import date, datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.enums import Audience, Frequency, PropertyType, RequestStatus, ServiceCode


class LoginIn(BaseModel):
    username: str
    password: str


class LoginOut(BaseModel):
    token: str
    username: str
    expires_in: int


class RequestedItem(BaseModel):
    """One thing the visitor asked for, ready to read.

    The label is resolved server-side because that is where the rate card lives:
    a priced request keeps the wording of the card that priced it, which may not
    be the wording the active card uses today.
    """

    code: str
    label: str
    quantity: int | None = None
    unit: str = ""


class AdminRequestRow(BaseModel):
    id: str
    created_at: datetime
    status: RequestStatus
    audience: Audience
    frequency: Frequency
    full_name: str
    company: str | None
    email: str | None
    phone: str | None
    locale: str
    property_type: str
    area_sqft: int | None
    bedrooms: int | None
    bathrooms: int | None
    restrooms: int | None
    # Not priced by anything, and that is fine: a three-storey office is a
    # different job, and the person writing the quote needs to know. Collected
    # and shown beats collected and buried, which is what it was.
    floors: int | None
    address_line: str | None
    postal_code: str | None
    city: str | None
    borough: str | None
    access_notes: str | None
    desired_start: date | None
    preferred_contact: str | None
    night_access: bool
    # What was actually asked for. Without these the person doing the job reads a
    # total and has no idea it covers forty windows.
    services: list[str]
    extras: list[RequestedItem]
    # The answers that changed the price: "Premier ménage : Oui". Without them a
    # 459 $ quote and a 221 $ one look like the same job.
    modifiers: list[RequestedItem]
    computed_total_cents: int | None
    quoted_total_cents: int | None
    utm_campaign: str | None
    gclid: str | None


class AdminPhoto(BaseModel):
    """One customer photo. The bytes come from GET /admin/photos/{id}, which is
    behind the same auth as everything else here -- these are pictures of the
    inside of somebody's home and must never be servable by URL alone."""

    id: str
    zone: str
    # The room as it should be shown: our label for it, or the customer's own word
    # when they picked "Autre" and typed one.
    zone_label_fr: str
    # Whether that name came from the customer rather than our list. The screen
    # marks it, so nobody reads a typed-in room as one of our categories.
    customer_named: bool = False
    bytes_size: int | None
    created_at: datetime


class AdminRequestDetail(AdminRequestRow):
    """Everything the detail page shows.

    Inherits the list row rather than restating thirty fields: the two would
    drift, and the first sign of it would be a field that quietly shows in the
    table and not on the page it links to. Only what the list has no room for
    is added here.
    """

    photos: list[AdminPhoto] = []
    computed_breakdown: dict | None = None
    consent_given: bool = False
    utm_source: str | None = None
    utm_medium: str | None = None
    landing_path: str | None = None
    rate_card_version: str | None = None
    offers: list[OfferSent] = []


class AdminRequestList(BaseModel):
    items: list[AdminRequestRow]
    total: int
    counts_by_status: dict[str, int]


class AdminRequestPatch(BaseModel):
    status: RequestStatus | None = None
    quoted_total_cents: int | None = None
    notes: str | None = None


class AdminCustomerPatch(BaseModel):
    """What Amine may correct after talking to the customer.

    THE FORM IS A FIRST DRAFT. A visitor types "1200" when the place is 2100, gives
    a phone number with a digit missing, or leaves the address out entirely and says
    it on the phone. Until now all of that was frozen the moment they pressed send,
    and the only way to fix a typo in an email address was a database client.

    WHAT IS DELIBERATELY NOT HERE:
      * audience -- residential and commercial are priced by different halves of
        the grid and asked different questions. A shop that came in as a condo is
        not a typo to fix, it is a request to submit again. `property_type` IS
        editable, but only among the types belonging to the audience the request
        already has, so the invariant the public form enforces still holds.
      * consent_given -- a record of what the customer agreed to. Ours to honour,
        not to edit.
      * the attribution fields -- captured once on arrival. A campaign you can
        rewrite afterwards is a campaign report you cannot trust.
      * computed_breakdown -- what the visitor was actually shown at submission.
        Editing the area does not rewrite history; the price to send is its own
        field and always was.
      * extras and modifiers -- they are what the stored breakdown was computed
        FROM. Changing them without recomputing would leave a price whose own
        itemisation contradicts it, and recomputing would overwrite the record of
        what the visitor was quoted. Both are worse than leaving them alone: put
        the change in the message, or in the price you send.

    Every field is optional AND absence means "leave it alone", which is not the
    same as null. The endpoint reads `model_fields_set`, so a payload of
    {"phone": null} clears the phone and a payload without "phone" does not touch
    it. Bounds match PropertyIn and ContactIn -- the same data, so the same limits.
    """

    full_name: Annotated[str, Field(min_length=2, max_length=160)] | None = None
    company: Annotated[str, Field(max_length=160)] | None = None
    email: EmailStr | None = None
    phone: Annotated[str, Field(max_length=40)] | None = None
    preferred_contact: Annotated[str, Field(pattern="^(email|phone)$")] | None = None

    address_line: Annotated[str, Field(max_length=255)] | None = None
    city: Annotated[str, Field(max_length=120)] | None = None
    borough: Annotated[str, Field(max_length=120)] | None = None
    postal_code: Annotated[str, Field(max_length=12)] | None = None

    area_sqft: Annotated[int, Field(ge=100, le=1_000_000)] | None = None
    bedrooms: Annotated[int, Field(ge=0, le=20)] | None = None
    bathrooms: Annotated[int, Field(ge=0, le=20)] | None = None
    floors: Annotated[int, Field(ge=1, le=100)] | None = None
    restrooms: Annotated[int, Field(ge=0, le=200)] | None = None

    # What was asked for. `frequency` earns its place twice over: it decides the
    # recurring discount and it is the period printed on the quote email, so a
    # customer moving from weekly to monthly changes both and could be corrected
    # nowhere.
    property_type: PropertyType | None = None
    frequency: Frequency | None = None
    services: Annotated[list[ServiceCode], Field(max_length=12)] | None = None
    night_access: bool | None = None

    # Which language their quote is written in. The email follows it, so after
    # "actually, could you send that in English?" this is the switch.
    locale: Annotated[str, Field(pattern="^(fr|en)$")] | None = None

    desired_start: date | None = None
    access_notes: Annotated[str, Field(max_length=2000)] | None = None

    @field_validator(
        "full_name", "company", "email", "phone", "preferred_contact",
        "address_line", "city", "borough", "postal_code", "access_notes",
        "area_sqft", "bedrooms", "bathrooms", "floors", "restrooms", "desired_start",
        "property_type", "frequency", "locale",
        mode="before",
    )
    @classmethod
    def blank_is_null(cls, value: object) -> object:
        """An emptied input clears the field rather than failing validation.

        A browser form has no way to send "absent" for a text box the operator just
        emptied -- it sends "". Without this, clearing the company name is a 422 on
        min_length, and clearing an email address is a 422 from EmailStr. Absence is
        still expressed by leaving the key out of the JSON entirely, which is what
        the frontend does for fields the open card does not show.
        """
        if isinstance(value, str) and not value.strip():
            return None
        return value.strip() if isinstance(value, str) else value


class OfferIn(BaseModel):
    """What Amine types before sending an offer.

    The price is sent explicitly rather than read from the quote row: the number
    on screen is the one he decided to honour, and reading it back from the
    database would let a stale tab send a different figure than the one he was
    looking at.
    """

    # 4000 characters is a long email and a short essay; the cap is here so a
    # paste accident cannot become a 2 MB row.
    message: str = Field(min_length=1, max_length=4000)
    total_cents: int = Field(ge=0, le=10_000_000)


class OfferPreview(BaseModel):
    subject: str
    text: str
    to_email: str


class OfferSent(BaseModel):
    id: UUID
    to_email: str
    subject: str
    total_cents: int
    status: str
    sent_at: datetime | None
    error: str | None


# AdminRequestDetail names OfferSent in an annotation before OfferSent exists,
# so Pydantic cannot resolve it when the class is built. Rebuilding here, once
# both are defined, is the supported way round that -- and it beats reordering
# the file around a forward reference that reads perfectly well where it is.
AdminRequestDetail.model_rebuild()
