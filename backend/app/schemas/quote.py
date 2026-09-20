"""Pydantic is the single source of truth: the frontend types are generated from these."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.models.enums import (
    AUDIENCE_BY_PROPERTY_TYPE,
    Audience,
    Frequency,
    PropertyType,
    RequestStatus,
)


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
    def one_channel_required(self) -> "ContactIn":
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
    services: list[str] = Field(default_factory=list, max_length=12)
    frequency: Frequency = Frequency.one_time
    extras: list[str] = Field(default_factory=list, max_length=12)
    desired_start: date | None = None
    access_notes: str | None = Field(default=None, max_length=2000)
    night_access: bool = False
    contact: ContactIn
    attribution: Attribution = Field(default_factory=Attribution)
    # Honeypot: real visitors never fill this.
    website: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def audience_matches_property_type(self) -> "QuoteRequestIn":
        """A house is never a commercial request. Reject the contradiction rather
        than storing a row nobody can price."""
        expected = AUDIENCE_BY_PROPERTY_TYPE[self.property.property_type]
        if self.audience is not expected:
            raise ValueError(
                f"property type '{self.property.property_type.value}' is "
                f"{expected.value}, not {self.audience.value}"
            )
        return self


class PriceLine(BaseModel):
    code: str
    label_fr: str
    label_en: str
    amount_cents: int


class PriceOut(BaseModel):
    lines: list[PriceLine]
    subtotal_cents: int
    discount_cents: int
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


class PriceDraftIn(BaseModel):
    """Same shape as a submission minus contact: prices without saving anything."""

    audience: Audience
    property: PropertyIn
    services: list[str] = Field(default_factory=list, max_length=12)
    frequency: Frequency = Frequency.one_time
    extras: list[str] = Field(default_factory=list, max_length=12)
    night_access: bool = False

    @model_validator(mode="after")
    def audience_matches_property_type(self) -> "PriceDraftIn":
        expected = AUDIENCE_BY_PROPERTY_TYPE[self.property.property_type]
        if self.audience is not expected:
            raise ValueError(
                f"property type '{self.property.property_type.value}' is "
                f"{expected.value}, not {self.audience.value}"
            )
        return self
