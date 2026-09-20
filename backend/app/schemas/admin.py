from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.models.enums import Audience, Frequency, RequestStatus


class LoginIn(BaseModel):
    username: str
    password: str


class LoginOut(BaseModel):
    token: str
    username: str
    expires_in: int


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
    city: str | None
    borough: str | None
    access_notes: str | None
    computed_total_cents: int | None
    quoted_total_cents: int | None
    utm_campaign: str | None
    gclid: str | None


class AdminRequestList(BaseModel):
    items: list[AdminRequestRow]
    total: int
    counts_by_status: dict[str, int]


class AdminRequestPatch(BaseModel):
    status: RequestStatus | None = None
    quoted_total_cents: int | None = None
    notes: str | None = None
