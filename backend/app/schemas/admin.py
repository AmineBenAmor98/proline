from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import Audience, Frequency, RequestStatus


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
    zone_label_fr: str
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
