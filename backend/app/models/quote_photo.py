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
    storage_key: Mapped[str] = mapped_column(String(400), nullable=False)
    bytes_size: Mapped[int | None] = mapped_column(Integer)

    detections: Mapped[dict | None] = mapped_column(JSONB)
    confidence: Mapped[int | None] = mapped_column(Integer)  # 0-100
    corrected_by_human: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    request: Mapped["QuoteRequest"] = relationship(back_populates="photos")  # noqa: F821
