"""Add the online-pricing switch to rate cards.

Unlike every other column here this one IS edited in place: it is not a price, so
flipping it cannot change what an already-sent quote recomputes to. It exists so a
wrong grid can be taken off the public site in one click, without inventing a
version that nobody priced anything with.
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "rate_cards",
        sa.Column(
            "residential_online_pricing",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    op.drop_column("rate_cards", "residential_online_pricing")
