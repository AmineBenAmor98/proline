"""Initial schema: leads, properties, rate cards, quote requests, photos, quotes.

This was seven migrations while the pricing model was being worked out. Nothing
had ever been deployed, so that chain was a record of the exploration rather than
of anything that had run against real data -- and a new reader's first question
about a repo should not be "why does the extras column change type twice".

Squashed. The *reasoning* that lived in those docstrings is in `README.md` and
`docs/PRICING-V2.md`, which is where it belongs; what is left here are the rules
the database itself keeps. Four of them are worth stating, because each one exists
to stop something the application code otherwise had to remember:

- **One active rate card** (`uq_rate_cards_one_active`). Every price on the site
  comes from `get_active_rate_card`, which takes the first row. Two active cards
  would make the price depend on row order.
- **One quote per request** (`uq_quotes_request_id`). The admin patch reads it
  with `.first()` and updates in place; a second row would duplicate the request
  in the listing.
- **Every foreign key is indexed.** Postgres does not do this for you, and each of
  these columns is the child side of an `ON DELETE CASCADE`: without the index,
  deleting a lead sequentially scans its children to find what to cascade to.
- **`request_status` holds only what a status is.** It briefly also carried
  `priced` and `enriching`: the first was set on arrival whenever the engine
  produced a number, which made it a second copy of `computed_total_cents IS
  NULL` and left the inbox with no unread state; nothing ever set the second.

Note for the models: nullable JSONB columns pass `none_as_null=True`. Without it
SQLAlchemy writes a Python `None` as the JSON literal `null`, and
`computed_breakdown IS NOT NULL` then answers yes for a request nobody priced.
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
REQUEST_STATUS = sa.Enum("new", "quoted", "won", "lost", name="request_status")
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
    op.create_index("ix_properties_lead_id", "properties", ["lead_id"])

    op.create_table(
        "rate_cards",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("version", sa.String(40), nullable=False, unique=True),
        sa.Column("effective_from", sa.Date, nullable=False),
        sa.Column("effective_to", sa.Date),
        sa.Column("is_active", sa.Boolean, server_default=sa.false(), nullable=False),
        # Not a price, so it is the one field edited in place: flipping it cannot
        # change what an already-sent quote recomputes to.
        sa.Column(
            "residential_online_pricing", sa.Boolean, server_default=sa.true(), nullable=False
        ),
        sa.Column("hourly_rate_cents", sa.Integer, nullable=False),
        sa.Column("minimum_visit_cents", sa.Integer, nullable=False),
        sa.Column("travel_cents", sa.Integer, server_default="0", nullable=False),
        sa.Column("grid", postgresql.JSONB, nullable=False, server_default="{}"),
        *_timestamps(),
    )
    # Exactly one card may be active. The publishing path maintains this in a
    # transaction, but a rule the code relies on belongs in the schema.
    op.execute(
        "CREATE UNIQUE INDEX uq_rate_cards_one_active "
        "ON rate_cards ((is_active)) WHERE is_active"
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
        # code -> quantity: {"windows": 6}. A flat extra carries 1; the rate card
        # decides whether the number means anything.
        sa.Column(
            "extras", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        # code -> the chosen option's value: {"premier_menage": "yes"}. Both the
        # card's, so a quote can be reconstructed from the card that priced it.
        sa.Column(
            "modifiers", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
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
    op.create_index("ix_quote_requests_lead_id", "quote_requests", ["lead_id"])
    op.create_index("ix_quote_requests_property_id", "quote_requests", ["property_id"])
    # Also what `list_rate_cards` counts by, instead of parsing every stored
    # breakdown's JSONB to recover a version that is a column in the same row.
    op.create_index("ix_quote_requests_rate_card_id", "quote_requests", ["rate_card_id"])

    op.create_table(
        "quote_photos",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "request_id", UUID, sa.ForeignKey("quote_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("zone", PHOTO_ZONE, nullable=False),
        sa.Column("storage_key", sa.String(400), nullable=False),
        sa.Column("bytes_size", sa.Integer),
        sa.Column("detections", postgresql.JSONB),
        sa.Column("confidence", sa.Integer),
        sa.Column("corrected_by_human", sa.Boolean, server_default=sa.false(), nullable=False),
        *_timestamps(),
    )
    op.create_index("ix_quote_photos_request_id", "quote_photos", ["request_id"])

    op.create_table(
        "quotes",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "request_id", UUID, sa.ForeignKey("quote_requests.id", ondelete="CASCADE"),
            nullable=False,
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
    # Named, rather than left to Postgres's `quotes_request_id_key`: this is the
    # name that shows up in the error when it fires.
    op.create_unique_constraint("uq_quotes_request_id", "quotes", ["request_id"])
    op.create_index("ix_quotes_request_id", "quotes", ["request_id"])
    op.create_index("ix_quotes_rate_card_id", "quotes", ["rate_card_id"])


def downgrade() -> None:
    op.drop_table("quotes")
    op.drop_table("quote_photos")
    op.drop_table("quote_requests")
    op.drop_table("rate_cards")
    op.drop_table("properties")
    op.drop_table("leads")
    for enum in (PHOTO_ZONE, REQUEST_STATUS, FREQUENCY, AUDIENCE, PROPERTY_TYPE):
        enum.drop(op.get_bind(), checkfirst=True)
