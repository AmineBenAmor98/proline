"""Storing the photos a customer attaches to a quote request.

THE SHAPE, AND WHY. Photos never ride on the request that creates the lead.
`POST /api/quotes` saves the lead and hands back a short-lived upload token; the
browser then posts each photo separately against that token. A customer on a
slow phone connection whose upload dies has still submitted their request --
which is the whole point, because a lead we never captured is worth nothing and
an accurate quote for a customer who gave up is worth less.

WHAT IS STORED. The bytes go on disk under PHOTOS_DIR and the row keeps the
relative path in `storage_key` -- never the image itself in Postgres. That keeps
the database small enough to restore quickly, and it is what makes moving to S3
later a copy plus a config change rather than a schema change.

WHAT IS NOT DONE HERE. The image is never decoded server-side. Decoding is what
makes a decompression bomb dangerous, and we have no reason to: the browser
resizes before uploading, the size cap bounds what arrives, and the only thing
that ever renders these is the admin's own browser. So this module sniffs magic
bytes, counts bytes, and writes the file. No Pillow, no resizing, no thumbnails.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
import uuid
from pathlib import Path

# Magic bytes, checked instead of trusting the declared Content-Type -- which is
# whatever the client felt like sending. Keys are the extension we store under.
_SIGNATURES: tuple[tuple[str, bytes, int], ...] = (
    ("jpg", b"\xff\xd8\xff", 0),
    ("png", b"\x89PNG\r\n\x1a\n", 0),
    ("webp", b"WEBP", 8),  # bytes 0-3 are "RIFF", 4-7 the length
)

TOKEN_TTL_SECONDS = 60 * 60  # an hour: long enough for a slow upload, short
# enough that a token leaking out of a browser history is not a standing invitation.


class PhotoRejected(Exception):
    """The upload is not something we will store. The message is shown to the customer."""


def _sign(message: str, secret: str) -> str:
    digest = hmac.new(secret.encode(), message.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def make_upload_token(request_id: str, secret: str, *, now: float | None = None) -> str:
    """A token that authorises uploading photos to ONE request, for one hour.

    Without this the upload endpoint is an open POST that writes files to disk
    for anybody who can guess a UUID -- and a uuid7 request id is not secret, it
    travels in the response body. Signed with SECRET_KEY, so it needs no storage
    and no cleanup: the expiry is inside the token.
    """
    expires = int((now if now is not None else time.time()) + TOKEN_TTL_SECONDS)
    message = f"{request_id}.{expires}"
    return f"{message}.{_sign(message, secret)}"


def check_upload_token(
    token: str, request_id: str, secret: str, *, now: float | None = None
) -> None:
    """Raise PhotoRejected unless `token` authorises uploads to `request_id`."""
    try:
        token_id, expires_raw, signature = token.split(".")
        expires = int(expires_raw)
    except (ValueError, AttributeError):
        raise PhotoRejected("Lien d'envoi invalide.") from None

    expected = _sign(f"{token_id}.{expires_raw}", secret)
    # compare_digest, not ==, so the comparison does not leak the signature one
    # character at a time through how long it takes to fail.
    if not hmac.compare_digest(expected, signature):
        raise PhotoRejected("Lien d'envoi invalide.")
    if not hmac.compare_digest(token_id, str(request_id)):
        raise PhotoRejected("Lien d'envoi invalide.")
    if (now if now is not None else time.time()) > expires:
        raise PhotoRejected("Lien d'envoi expiré. Répondez au courriel avec vos photos.")


def sniff_extension(head: bytes) -> str:
    """The file's real type from its first bytes, or raise.

    A .jpg that is not a JPEG is either a confused customer or someone probing,
    and neither is a reason to keep the file.
    """
    for extension, magic, offset in _SIGNATURES:
        if head[offset : offset + len(magic)] == magic:
            return extension
    raise PhotoRejected("Formats acceptés : JPEG, PNG ou WebP.")


def storage_key(extension: str, *, today: str) -> str:
    """Where this photo lives, relative to PHOTOS_DIR.

    Dated folders because a flat directory of tens of thousands of files is
    miserable to back up, list or reason about; a random name because the
    original filename is the customer's and can contain anything at all.
    """
    return f"{today}/{uuid.uuid4().hex}{secrets.token_hex(4)}.{extension}"


def resolve(photos_dir: str, key: str) -> Path:
    """The absolute path for a storage key, refusing anything that escapes the root.

    `key` comes out of the database, and a row is only as trustworthy as
    whatever wrote it. A key of `../../etc/passwd` must not resolve, today or
    after some future import script writes rows we did not.
    """
    root = Path(photos_dir).resolve()
    target = (root / key).resolve()
    if not target.is_relative_to(root):
        raise PhotoRejected("Chemin de fichier invalide.")
    return target


def write(photos_dir: str, key: str, data: bytes) -> Path:
    path = resolve(photos_dir, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path
