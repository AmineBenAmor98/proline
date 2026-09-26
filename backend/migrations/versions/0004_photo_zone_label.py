"""Let the customer name the room themselves when our list has no word for it.

`zone` stays an enum, deliberately: it is what the admin screen groups by and what
any later analysis counts, and free text cannot do either job. This column is the
escape hatch beside it -- set only when zone is `other`, empty otherwise.

Nullable with no default and no backfill, so it adds nothing to existing rows and
needs no table rewrite.
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("quote_photos", sa.Column("zone_label", sa.String(length=60), nullable=True))


def downgrade() -> None:
    op.drop_column("quote_photos", "zone_label")
