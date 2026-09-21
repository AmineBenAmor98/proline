import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import TimestampedBase


class Quote(TimestampedBase):
    """What the client actually received, after human review."""

    __tablename__ = "quotes"

    # Unique: the code assumes one quote per request -- the admin patch reads it
    # with .first() and updates in place, the list outer-joins on it -- so the
    # database says so too, rather than leaving it to whoever writes the next
    # query.
    request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("quote_requests.id", ondelete="CASCADE"), unique=True, index=True
    )
    rate_card_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("rate_cards.id"))

    total_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    pdf_key: Mapped[str | None] = mapped_column(String(400))

    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
