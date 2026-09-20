import uuid

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import TimestampedBase


class Lead(TimestampedBase):
    """A person who submitted something. Attribution is captured once and never overwritten."""

    __tablename__ = "leads"

    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(40))
    company: Mapped[str | None] = mapped_column(String(160))
    locale: Mapped[str] = mapped_column(String(5), default="fr", nullable=False)
    preferred_contact: Mapped[str | None] = mapped_column(String(10))
    consent_given: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    utm_source: Mapped[str | None] = mapped_column(String(120))
    utm_medium: Mapped[str | None] = mapped_column(String(120))
    utm_campaign: Mapped[str | None] = mapped_column(String(160))
    utm_term: Mapped[str | None] = mapped_column(String(160))
    gclid: Mapped[str | None] = mapped_column(String(255))
    landing_path: Mapped[str | None] = mapped_column(String(255))

    properties: Mapped[list["Property"]] = relationship(back_populates="lead")  # noqa: F821
    requests: Mapped[list["QuoteRequest"]] = relationship(back_populates="lead")  # noqa: F821

    id: Mapped[uuid.UUID]
