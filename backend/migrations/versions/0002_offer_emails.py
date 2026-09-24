"""Record every offer email as it was sent.

Not more columns on `quotes`, which holds *the current offer* -- one row per
request, rewritten when the price is revised. This is an append-only log of what
a client was actually told, because a revision does not un-send the first email
and "you quoted me 250 $" has to be answerable from the database rather than
from memory.

Failed attempts are rows too. A client insisting they received nothing is right
more often than the absence of a log suggests, and a row saying the provider
refused it at 14:02 settles it.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "offer_emails",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "request_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("quote_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("to_email", sa.String(320), nullable=False),
        sa.Column("subject", sa.String(300), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("total_cents", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("provider_id", sa.String(200)),
        sa.Column("error", sa.Text()),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    # The child side of an ON DELETE CASCADE, and the column every read filters
    # on. Postgres does not index foreign keys for you.
    op.create_index("ix_offer_emails_request_id", "offer_emails", ["request_id"])


def downgrade() -> None:
    op.drop_index("ix_offer_emails_request_id", table_name="offer_emails")
    op.drop_table("offer_emails")
