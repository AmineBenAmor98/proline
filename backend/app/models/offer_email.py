import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import TimestampedBase


class OfferEmail(TimestampedBase):
    """One record per offer email, kept forever, never edited.

    Separate from `quotes` rather than more columns on it, because the two answer
    different questions. `quotes` is *the current offer* -- one row per request,
    updated when Amine revises the price. This is *what was actually sent*, and a
    revision does not undo the first email: if a client was told 250 $ on Monday
    and 280 $ on Wednesday, both happened, and "but you quoted me 250" is a
    conversation that has to be answerable months later.

    So the body is stored as it went out, not re-rendered on demand. Re-rendering
    would show today's template and today's price -- an honest-looking answer to
    the wrong question.
    """

    __tablename__ = "offer_emails"

    request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("quote_requests.id", ondelete="CASCADE"), index=True, nullable=False
    )

    to_email: Mapped[str] = mapped_column(String(320), nullable=False)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    total_cents: Mapped[int] = mapped_column(Integer, nullable=False)

    # "sent" or "failed". A failed attempt is kept: a client who says they got
    # nothing is right more often than the logs suggest, and a row saying the
    # provider refused it at 14:02 is the difference between knowing and guessing.
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_id: Mapped[str | None] = mapped_column(String(200))
    error: Mapped[str | None] = mapped_column(Text)

    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
