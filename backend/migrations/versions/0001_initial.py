"""initial schema: leads, properties, rate cards, quote requests, photos, quotes

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

PROPERTY_TYPE = sa.Enum(
    "house", "condo", "apartment", "office", "retail", "building", "industrial", "construction",
    name="property_type",
)
AUDIENCE = sa.Enum("residential", "commercial", name="audience")
FREQUENCY = sa.Enum("one_time", "weekly", "biweekly", "monthly", "to_discuss", name="frequency")
REQUEST_STATUS = sa.Enum(
    "new", "enriching", "priced", "quoted", "won", "lost", name="request_status"
)
PHOTO_ZONE = sa.Enum(
    "workstations", "restrooms", "hallways", "common_areas", "kitchen", "other", name="photo_zone"
)

UUID = postgresql.UUID(as_uuid=True)
TS = sa.DateTime(timezone=True)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "leads",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("full_name", sa.String(160), nullable=False),
        sa.Column("email", sa.String(255)),
        sa.Column("phone", sa.String(40)),
        sa.Column("company", sa.String(160)),
        sa.Column("locale", sa.String(5), server_default="fr", nullable=False),
        sa.Column("preferred_contact", sa.String(10)),
        sa.Column("consent_given", sa.Boolean, server_default=sa.false(), nullable=False),
        sa.Column("utm_source", sa.String(120)),
        sa.Column("utm_medium", sa.String(120)),
        sa.Column("utm_campaign", sa.String(160)),
        sa.Column("utm_term", sa.String(160)),
        sa.Column("gclid", sa.String(255)),
        sa.Column("landing_path", sa.String(255)),
        *_timestamps(),
    )
    op.create_index("ix_leads_created_at", "leads", ["created_at"])
    op.create_index("ix_leads_gclid", "leads", ["gclid"])

    op.create_table(
        "properties",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("lead_id", UUID, sa.ForeignKey("leads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("property_type", PROPERTY_TYPE, nullable=False),
        sa.Column("area_sqft", sa.Integer),
        sa.Column("bedrooms", sa.Integer),
        sa.Column("bathrooms", sa.Integer),
        sa.Column("restrooms", sa.Integer),
        sa.Column("floors", sa.Integer),
        sa.Column("address_line", sa.String(255)),
        sa.Column("city", sa.String(120)),
        sa.Column("borough", sa.String(120)),
        sa.Column("postal_code", sa.String(12)),
        *_timestamps(),
    )

    op.create_table(
        "rate_cards",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("version", sa.String(40), nullable=False, unique=True),
        sa.Column("effective_from", sa.Date, nullable=False),
        sa.Column("effective_to", sa.Date),
        sa.Column("is_active", sa.Boolean, server_default=sa.false(), nullable=False),
        sa.Column("hourly_rate_cents", sa.Integer, nullable=False),
        sa.Column("minimum_visit_cents", sa.Integer, nullable=False),
        sa.Column("travel_cents", sa.Integer, server_default="0", nullable=False),
        sa.Column("grid", postgresql.JSONB, nullable=False, server_default="{}"),
        *_timestamps(),
    )

    op.create_table(
        "quote_requests",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("lead_id", UUID, sa.ForeignKey("leads.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "property_id", UUID, sa.ForeignKey("properties.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("audience", AUDIENCE, nullable=False),
        sa.Column("services", postgresql.ARRAY(sa.String(40)), nullable=False, server_default="{}"),
        sa.Column("frequency", FREQUENCY, nullable=False),
        sa.Column("extras", postgresql.ARRAY(sa.String(40)), nullable=False, server_default="{}"),
        sa.Column("desired_start", sa.Date),
        sa.Column("access_notes", sa.Text),
        sa.Column("night_access", sa.Boolean, server_default=sa.false(), nullable=False),
        sa.Column("status", REQUEST_STATUS, nullable=False, server_default="new"),
        sa.Column("rate_card_id", UUID, sa.ForeignKey("rate_cards.id")),
        sa.Column("computed_total_cents", sa.Integer),
        sa.Column("computed_breakdown", postgresql.JSONB),
        *_timestamps(),
    )
    op.create_index("ix_quote_requests_status", "quote_requests", ["status"])
    op.create_index("ix_quote_requests_created_at", "quote_requests", ["created_at"])

    op.create_table(
        "quote_photos",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "request_id", UUID, sa.ForeignKey("quote_requests.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("zone", PHOTO_ZONE, nullable=False),
        sa.Column("storage_key", sa.String(400), nullable=False),
        sa.Column("bytes_size", sa.Integer),
        sa.Column("detections", postgresql.JSONB),
        sa.Column("confidence", sa.Integer),
        sa.Column("corrected_by_human", sa.Boolean, server_default=sa.false(), nullable=False),
        *_timestamps(),
    )

    op.create_table(
        "quotes",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "request_id", UUID, sa.ForeignKey("quote_requests.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("rate_card_id", UUID, sa.ForeignKey("rate_cards.id")),
        sa.Column("total_cents", sa.Integer, nullable=False),
        sa.Column("notes", sa.Text),
        sa.Column("pdf_key", sa.String(400)),
        sa.Column("sent_at", TS),
        sa.Column("viewed_at", TS),
        sa.Column("accepted_at", TS),
        *_timestamps(),
    )


def downgrade() -> None:
    op.drop_table("quotes")
    op.drop_table("quote_photos")
    op.drop_table("quote_requests")
    op.drop_table("rate_cards")
    op.drop_table("properties")
    op.drop_table("leads")
    for enum in (PHOTO_ZONE, REQUEST_STATUS, FREQUENCY, AUDIENCE, PROPERTY_TYPE):
        enum.drop(op.get_bind(), checkfirst=True)
