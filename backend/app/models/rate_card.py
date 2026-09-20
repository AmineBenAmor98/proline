from datetime import date

from sqlalchemy import Boolean, Date, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import TimestampedBase


class RateCard(TimestampedBase):
    """Versioned pricing grid. Never edited in place: a price change creates a new row,
    so a quote sent last spring still recomputes to the number the client received."""

    __tablename__ = "rate_cards"

    version: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # All money in cents, CAD.
    hourly_rate_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    minimum_visit_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    travel_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # grid: residential base prices, task minutes, surface multipliers, extras, discounts.
    grid: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
