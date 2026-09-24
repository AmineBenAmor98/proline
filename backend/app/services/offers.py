"""Sending a client their offer, from the admin panel.

The email is composed here rather than in the browser so that what is stored is
what was sent. `OfferEmail` keeps the rendered body verbatim: a client asking
six months later what they were quoted deserves the actual text, not today's
template filled with today's price.

Amine writes the message; the price, the property and the contact line are
appended by the code. That split is deliberate. The parts a person should
control -- tone, what is included, when the crew can come -- are typed. The
parts that must not drift from the database are not.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.core.config import Settings
from app.core.logging import logger
from app.models import Lead, Property, QuoteRequest
from app.models.offer_email import OfferEmail
from app.services.mailer import build_message, send


def money(cents: int) -> str:
    """1 2 3 4,56 $ — fr-CA, with the non-breaking spaces French typography
    wants, because a price that wraps across a line break in a quote email
    looks like two numbers."""
    whole, rest = divmod(abs(cents), 100)
    digits = f"{whole:,}".replace(",", " ")
    sign = "−" if cents < 0 else ""
    return f"{sign}{digits},{rest:02d} $"


def property_line(prop: Property) -> str:
    bits: list[str] = []
    if prop.bedrooms is not None:
        bits.append(f"{prop.bedrooms} chambre{'s' if prop.bedrooms > 1 else ''}")
    if prop.bathrooms is not None:
        bits.append(f"{prop.bathrooms} salle{'s' if prop.bathrooms > 1 else ''} de bain")
    if prop.area_sqft:
        bits.append(f"{prop.area_sqft} pi²")
    return " · ".join(bits)


def render(
    settings: Settings,
    *,
    lead: Lead,
    prop: Property,
    request: QuoteRequest,
    message: str,
    total_cents: int,
) -> tuple[str, str]:
    """Returns (subject, text). One rendering, used for both the email and the
    stored record -- two renderings would eventually disagree."""
    subject = "Votre soumission — Proline Cleaning Solutions"

    greeting = f"Bonjour {lead.full_name.split()[0]}," if lead.full_name else "Bonjour,"
    details = property_line(prop)

    lines = [greeting, "", message.strip(), ""]
    if details:
        lines += [f"Propriété : {details}", ""]
    lines += [
        f"Prix : {money(total_cents)}",
        "Taxes en sus.",
        "",
        "Répondez à ce courriel pour confirmer ou poser une question.",
        "",
        "Proline Cleaning Solutions",
        settings.mail_reply_to or settings.mail_from,
    ]
    return subject, "\n".join(lines)


async def send_offer(
    settings: Settings,
    session,
    *,
    lead: Lead,
    prop: Property,
    request: QuoteRequest,
    message: str,
    total_cents: int,
) -> OfferEmail:
    """Send, and record the attempt either way.

    The row is written before the send and updated after, so a process that dies
    mid-send leaves evidence rather than nothing. A client who says they never
    received it is answered from this table, not from memory.
    """
    subject, text = render(
        settings, lead=lead, prop=prop, request=request,
        message=message, total_cents=total_cents,
    )

    record = OfferEmail(
        request_id=request.id,
        to_email=lead.email,
        subject=subject,
        body_text=text,
        total_cents=total_cents,
        status="failed",  # until proven otherwise
    )
    session.add(record)
    await session.flush()

    try:
        await send(
            settings,
            build_message(settings, to=lead.email, subject=subject, text=text),
        )
    except Exception as exc:
        record.error = str(exc)[:2000]
        logger.error(
            "offer.failed", request_id=str(request.id), to=lead.email, error=str(exc)
        )
        raise
    else:
        record.status = "sent"
        record.sent_at = datetime.now(UTC)
        record.error = None
        logger.info("offer.sent", request_id=str(request.id), to=lead.email)

    return record
