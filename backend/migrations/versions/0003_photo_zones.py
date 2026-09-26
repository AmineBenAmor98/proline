"""Widen photo_zone to cover residential as well as commercial properties.

The original enum was commercial only -- workstations, restrooms, hallways,
common_areas, kitchen, other -- because photos were first imagined as a
commercial feature. They are offered on both forms now, so a residential
customer needs somewhere to put a bathroom or a basement.

WHY DROP AND RECREATE RATHER THAN `ALTER TYPE ... ADD VALUE`. Adding values is
the usual advice and is wrong here for two reasons. Postgres will not let a
newly added enum value be USED in the same transaction that added it, and
Alembic wraps each migration in one -- so an append-only migration cannot also
backfill or constrain anything, and the failure is a runtime error in whichever
later statement touches it. And appending leaves the values in creation order,
so `workstations, restrooms, ..., other, bathroom, bedroom` -- every ORDER BY
zone for the rest of the project's life reads in the order somebody happened to
add them. Recreating costs nothing while the table is empty, and it will not be
empty again.

If this ever runs against a table WITH rows, the USING cast below maps every
existing value to itself (all six survive into the new type), so it is safe --
but check that before assuming it.
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

OLD = ("workstations", "restrooms", "hallways", "common_areas", "kitchen", "other")
NEW = (
    "workstations",
    "restrooms",
    "hallways",
    "common_areas",
    "bathroom",
    "bedroom",
    "living_area",
    "basement",
    "garage",
    "kitchen",
    "entrance",
    "exterior",
    "other",
)


def _swap(values: tuple[str, ...]) -> None:
    """Replace photo_zone with a type holding exactly `values`.

    The column is moved to the new type with an explicit USING cast through
    text; without it Postgres refuses the type change outright.
    """
    new = sa.Enum(*values, name="photo_zone_new")
    new.create(op.get_bind(), checkfirst=False)
    op.execute(
        "ALTER TABLE quote_photos "
        "ALTER COLUMN zone TYPE photo_zone_new USING zone::text::photo_zone_new"
    )
    op.execute("DROP TYPE photo_zone")
    op.execute("ALTER TYPE photo_zone_new RENAME TO photo_zone")


def upgrade() -> None:
    _swap(NEW)


def downgrade() -> None:
    # Rows carrying a residential zone cannot survive this -- there is nothing
    # to map them to. Fail loudly rather than silently rewriting someone's data
    # to `other`, which would look like it worked.
    zones = ", ".join(f"'{z}'" for z in NEW if z not in OLD)
    op.execute(
        "DO $$ BEGIN "
        f"IF EXISTS (SELECT 1 FROM quote_photos WHERE zone::text IN ({zones})) THEN "
        "RAISE EXCEPTION 'photos use residential zones; downgrading would lose them'; "
        "END IF; END $$;"
    )
    _swap(OLD)
