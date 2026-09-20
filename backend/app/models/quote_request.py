import uuid
from datetime import date

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import TimestampedBase
from app.models.enums import Audience, Frequency, RequestStatus


class QuoteRequest(TimestampedBase):
    __tablename__ = "quote_requests"

    lead_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"))
    property_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("properties.id", ondelete="CASCADE"))

    audience: Mapped[Audience] = mapped_column(Enum(Audience, name="audience"), nullable=False)
    services: Mapped[list[str]] = mapped_column(ARRAY(String(40)), nullable=False, default=list)
    frequency: Mapped[Frequency] = mapped_column(Enum(Frequency, name="frequency"), nullable=False)
    extras: Mapped[list[str]] = mapped_column(ARRAY(String(40)), nullable=False, default=list)
    desired_start: Mapped[date | None]
    access_notes: Mapped[str | None] = mapped_column(Text)
    night_access: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    status: Mapped[RequestStatus] = mapped_column(
        Enum(RequestStatus, name="request_status"), default=RequestStatus.new, nullable=False
    )

    # Computed suggestion. Shown to residential visitors, internal for commercial.
    rate_card_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("rate_cards.id"))
    computed_total_cents: Mapped[int | None] = mapped_column(Integer)
    computed_breakdown: Mapped[dict | None] = mapped_column(JSONB)

    lead: Mapped["Lead"] = relationship(back_populates="requests")  # noqa: F821
    photos: Mapped[list["QuotePhoto"]] = relationship(back_populates="request")  # noqa: F821
