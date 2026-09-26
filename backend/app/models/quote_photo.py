import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import TimestampedBase
from app.models.enums import PhotoZone


class QuotePhoto(TimestampedBase):
    """Detections are what the model returned, never a price. Corrections are recorded
    so the prompt can be tuned against real mistakes."""

    __tablename__ = "quote_photos"

    request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("quote_requests.id", ondelete="CASCADE")
    )
    zone: Mapped[PhotoZone] = mapped_column(Enum(PhotoZone, name="photo_zone"), nullable=False)

    # What the customer called the room, when our list had no word for it.
    #
    # Only ever set alongside zone == other, and it is the reason `other` is worth
    # offering at all: "Autre" on a photo tells whoever writes the quote nothing,
    # while "salle de lavage au sous-sol" tells them what they are looking at. Free
    # text from an anonymous caller, so it is bounded and stripped on the way in
    # (see the upload endpoint) and escaped on the way out.
    zone_label: Mapped[str | None] = mapped_column(String(60))

    storage_key: Mapped[str] = mapped_column(String(400), nullable=False)
    bytes_size: Mapped[int | None] = mapped_column(Integer)

    # See quote_request.computed_breakdown: a Python None has to reach SQL as NULL.
    detections: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    confidence: Mapped[int | None] = mapped_column(Integer)  # 0-100
    corrected_by_human: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    request: Mapped["QuoteRequest"] = relationship(back_populates="photos")  # noqa: F821
