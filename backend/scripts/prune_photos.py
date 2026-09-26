"""Delete customer photos past their retention period.

    python -m scripts.prune_photos            # delete what is due
    python -m scripts.prune_photos --dry-run  # say what would go, delete nothing

These are pictures of the inside of somebody's home. The form promises they are
kept for a year and then deleted, and a promise nothing enforces is just a
sentence on a page -- so this exists, and the compose file runs it daily.

ORDER MATTERS: the file goes first, then the row. The other way round leaves
files on disk with nothing pointing at them, which is the one state nothing will
ever clean up because nothing knows they are there. A row whose file is already
gone is harmless by comparison -- the admin endpoint answers 410 for it, and the
next run tidies the row.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import sys

from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import logger
from app.db.session import SessionLocal
from app.models import QuotePhoto
from app.services import photos as photo_store


async def prune(*, dry_run: bool = False) -> int:
    settings = get_settings()
    if not settings.photos_dir:
        print("PHOTOS_DIR is not set; nothing to prune.")
        return 0

    cutoff = dt.datetime.now(dt.UTC) - dt.timedelta(days=settings.photo_retention_days)
    removed = 0

    async with SessionLocal() as session:
        due = (
            await session.execute(select(QuotePhoto).where(QuotePhoto.created_at < cutoff))
        ).scalars().all()

        for photo in due:
            if dry_run:
                print(f"would delete {photo.storage_key} ({photo.created_at:%Y-%m-%d})")
                removed += 1
                continue
            try:
                path = photo_store.resolve(settings.photos_dir, photo.storage_key)
                path.unlink(missing_ok=True)
            except photo_store.PhotoRejected:
                # A key that will not resolve cannot be deleted from disk, but the
                # row must still go -- leaving it means retrying this forever.
                logger.warning("photo.prune.bad_key", storage_key=photo.storage_key)
            await session.delete(photo)
            removed += 1

        if not dry_run:
            await session.commit()

    # Empty dated folders left behind by the above, so the tree does not grow a
    # directory per month forever.
    if not dry_run and removed:
        root = photo_store.resolve(settings.photos_dir, "")
        for folder in sorted(root.rglob("*"), reverse=True):
            if folder.is_dir() and not any(folder.iterdir()):
                folder.rmdir()

    logger.info(
        "photo.prune", removed=removed, retention_days=settings.photo_retention_days,
        dry_run=dry_run,
    )
    print(f"{'would delete' if dry_run else 'deleted'} {removed} photo(s) older than "
          f"{settings.photo_retention_days} days")
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report only, delete nothing")
    args = parser.parse_args()
    asyncio.run(prune(dry_run=args.dry_run))
    return 0


if __name__ == "__main__":
    sys.exit(main())
