"""Sending a client their offer, from the admin panel.

The email is composed here rather than in the browser so that what is stored is
what was sent. `OfferEmail` keeps the rendered body verbatim: a client asking
six months later what they were quoted deserves the actual text, not today's
template filled with today's price.

Amine writes the message; the price, the property and the contact line are
appended by the code. That split is deliberate. The parts a person should
control -- tone, what is included, when the crew can come -- are typed. The
parts that must not drift from the database are not.

WHAT THIS EMAIL HAS TO CARRY, and for a long time did not:

  * THE PERIOD. Every price in this system is per visit. A bare "Prix :
    2 694,50 $" on a quote for a job that recurs every two weeks reads as the
    price of the whole arrangement, and the client who reads it that way is not
    being careless -- nothing on the page said otherwise. This was the single
    most expensive omission here: the misunderstanding surfaces on the first
    invoice, after the work.
  * A REFERENCE. The confirmation page gives the visitor one and the admin
    screen shows one; the email had none, so a reply three weeks later could
    not be matched to a request without searching by name.
  * THE CLIENT'S LANGUAGE. `Lead.locale` records whether they filled the French
    or the English form. It was ignored, so an anglophone who used /en received
    their quote in French.
  * A TELEPHONE NUMBER. It is on every page of the site. Someone ready to accept
    had a reply button and nothing else.
  * AN EXPIRY. A price with no end date is a price offered forever.

The plain-text part remains the record of what was sent. The HTML part is an
alternative for clients that render it -- see `mailer.build_message`.
"""

from __future__ import annotations

import datetime as dt
import pathlib
from datetime import UTC, datetime
from functools import lru_cache
from html import escape

from app.core.config import Settings
from app.core.logging import logger
from app.models import Lead, Property, QuoteRequest
from app.models.offer_email import OfferEmail
from app.services.mailer import build_message, send

# French typography, and THE TWO SPACES ARE NOT THE SAME CHARACTER. Thousands
# take a narrow no-break space and the gap before the dollar sign a regular
# no-break one, which is what fr-CA uses and what `Intl.NumberFormat` emits in
# the browser -- so the email and the website agree down to the codepoint.
# Either way they are unbreakable: an ordinary space lets a price wrap across
# two lines, "2 694," at the end of one and "50 $" at the start of the next.
NARROW_NBSP = "\u202f"
NBSP = "\u00a0"


def money(cents: int) -> str:
    """1 234,56 $ -- fr-CA, with the non-breaking spaces French typography wants."""
    whole, rest = divmod(abs(cents), 100)
    digits = f"{whole:,}".replace(",", NARROW_NBSP)
    sign = "−" if cents < 0 else ""
    return f"{sign}{digits},{rest:02d}{NBSP}$"


def money_en(cents: int) -> str:
    whole, rest = divmod(abs(cents), 100)
    sign = "-" if cents < 0 else ""
    return f"{sign}${whole:,}.{rest:02d}"


def _int(value: int) -> str:
    """12000 -> 12 000, with the same separator the price uses.

    The price was grouped and the area was not, in the same email, three lines
    apart: "Prix : 2 694,50 $" above "12000 pi\u00b2".
    """
    return f"{value:,}".replace(",", NARROW_NBSP)


FREQUENCY = {
    "fr": {
        "one_time": "une seule fois",
        "weekly": "chaque semaine",
        "biweekly": "aux deux semaines",
        "monthly": "chaque mois",
        "to_discuss": "fréquence à déterminer",
    },
    "en": {
        "one_time": "one time",
        "weekly": "every week",
        "biweekly": "every two weeks",
        "monthly": "every month",
        "to_discuss": "frequency to be agreed",
    },
}

# What the price covers, in words, on the line beside the number.
PERIOD = {
    "fr": {"one": "pour la visite", "recurring": "par visite"},
    "en": {"one": "for the visit", "recurring": "per visit"},
}

T = {
    "fr": {
        "subject": "Votre soumission {ref} — {business}",
        "tagline": "Entretien ménager · Grand Montréal",
        "greeting": "Bonjour {name},",
        "greeting_plain": "Bonjour,",
        "reference": "Référence",
        "property": "Propriété",
        "frequency": "Fréquence",
        "start": "Début souhaité",
        "price": "Prix",
        "taxes": "Taxes en sus.",
        "valid": "Cette offre est valide {days} jours, jusqu'au {date}.",
        "included_head": "Compris dans ce prix",
        "included": [
            "Produits et équipement fournis",
            "Personnel en uniforme, assuré et cautionné",
            "Satisfaction garantie : on revient reprendre sans frais",
            "Annulation gratuite jusqu'à 24 h avant la visite",
        ],
        "accept": "Pour accepter, répondez simplement à ce courriel. Une question sur "
                  "le prix ou la date ? Répondez aussi, ou appelez-nous.",
        "terms": "Conditions de service",
        "bedrooms": ("chambre", "chambres"),
        "bathrooms": ("salle de bain", "salles de bain"),
        "restrooms": ("sanitaire", "sanitaires"),
        "floors": ("étage", "étages"),
        "area": "{n} pi²",
    },
    "en": {
        "subject": "Your quote {ref} — {business}",
        "tagline": "Cleaning services · Greater Montreal",
        "greeting": "Hello {name},",
        "greeting_plain": "Hello,",
        "reference": "Reference",
        "property": "Property",
        "frequency": "Frequency",
        "start": "Preferred start",
        "price": "Price",
        "taxes": "Taxes extra.",
        "valid": "This quote is valid for {days} days, until {date}.",
        "included_head": "Included in this price",
        "included": [
            "Products and equipment supplied",
            "Staff in uniform, insured and bonded",
            "Satisfaction guaranteed: we come back and redo it at no charge",
            "Free cancellation up to 24 hours before the visit",
        ],
        "accept": "To accept, simply reply to this email. A question about the price "
                  "or the date? Reply as well, or give us a call.",
        "terms": "Terms of service",
        "bedrooms": ("bedroom", "bedrooms"),
        "bathrooms": ("bathroom", "bathrooms"),
        "restrooms": ("washroom", "washrooms"),
        "floors": ("floor", "floors"),
        "area": "{n} sq ft",
    },
}


MONTHS = {
    "fr": ("janvier", "février", "mars", "avril", "mai", "juin", "juillet",
           "août", "septembre", "octobre", "novembre", "décembre"),
    "en": ("January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"),
}


def long_date(value: dt.date, locale: str) -> str:
    """12 octobre 2026, not 2026-10-12.

    ISO is unambiguous and nobody reads a quote that way. It also invites the
    North American misreading of the reverse -- and a start date read a month
    early is a crew at a locked door.
    """
    month = MONTHS[locale][value.month - 1]
    return (f"{value.day} {month} {value.year}" if locale == "fr"
            else f"{month} {value.day}, {value.year}")


def bare_address(value: str) -> str:
    """contact@x.ca out of "Proline Cleaning Solutions <contact@x.ca>".

    The footer printed the whole From header directly beneath the business name,
    so the name appeared twice in three lines with an angle bracket between.
    """
    if "<" in value and ">" in value:
        return value[value.index("<") + 1:value.index(">")].strip()
    return value.strip()


def locale_of(lead: Lead) -> str:
    return "en" if (lead.locale or "fr").lower().startswith("en") else "fr"


def _count(n: int, words: tuple[str, str]) -> str:
    return f"{n} {words[0] if n == 1 else words[1]}"


def property_line(prop: Property, locale: str = "fr") -> str:
    """How the place reads on the quote.

    Audience-aware, which it was not: it listed bedrooms, bathrooms and area, so
    a shop -- which has washrooms and floors and neither of the first two -- got
    a line with nothing on it but a number of square feet, or an empty line.
    """
    t = T[locale]
    bits: list[str] = []
    if prop.bedrooms is not None:
        bits.append(_count(prop.bedrooms, t["bedrooms"]))
    if prop.bathrooms is not None:
        bits.append(_count(prop.bathrooms, t["bathrooms"]))
    if prop.restrooms is not None:
        bits.append(_count(prop.restrooms, t["restrooms"]))
    if prop.floors is not None and prop.floors > 1:
        bits.append(_count(prop.floors, t["floors"]))
    if prop.area_sqft:
        bits.append(t["area"].format(n=_int(prop.area_sqft)))
    return " · ".join(bits)


def first_name(lead: Lead) -> str:
    """The first word of their name, or nothing.

    `full_name.split()[0]` was an IndexError waiting for a name of pure
    whitespace -- which passes the form's min_length of 2 -- and it would have
    surfaced as a 500 at the moment Amine pressed send.
    """
    parts = (lead.full_name or "").split()
    return parts[0] if parts else ""


def period_words(request: QuoteRequest | None, locale: str) -> str:
    frequency = getattr(request, "frequency", None)
    value = getattr(frequency, "value", frequency) or "one_time"
    return PERIOD[locale]["one" if value == "one_time" else "recurring"]


def frequency_words(request: QuoteRequest | None, locale: str) -> str:
    frequency = getattr(request, "frequency", None)
    value = getattr(frequency, "value", frequency)
    return FREQUENCY[locale].get(value or "", "")


def reference(request: QuoteRequest | None) -> str:
    """The same eight characters the confirmation page and the admin show."""
    return str(getattr(request, "id", "") or "")[:8]


def _facts(
    settings: Settings, *, lead: Lead, prop: Property, request: QuoteRequest | None,
    total_cents: int, locale: str,
) -> list[tuple[str, str]]:
    t = T[locale]
    fmt = money if locale == "fr" else money_en
    rows: list[tuple[str, str]] = []

    ref = reference(request)
    if ref:
        rows.append((t["reference"], ref))

    details = property_line(prop, locale)
    if details:
        rows.append((t["property"], details))

    freq = frequency_words(request, locale)
    if freq:
        rows.append((t["frequency"], freq))

    start = getattr(request, "desired_start", None)
    if start:
        rows.append((t["start"], long_date(start, locale)))

    rows.append((t["price"], f"{fmt(total_cents)} {period_words(request, locale)}"))
    return rows


def valid_until(settings: Settings, today: dt.date | None = None) -> dt.date:
    return (today or dt.date.today()) + dt.timedelta(days=settings.offer_valid_days)


def render(
    settings: Settings,
    *,
    lead: Lead,
    prop: Property,
    message: str,
    total_cents: int,
    request: QuoteRequest | None = None,
    today: dt.date | None = None,
) -> tuple[str, str]:
    """Returns (subject, text). One rendering, used for the email and the stored
    record -- two renderings would eventually disagree."""
    locale = locale_of(lead)
    t = T[locale]
    ref = reference(request)

    subject = t["subject"].format(
        ref=f"#{ref}" if ref else "", business=settings.business_name
    ).replace("  ", " ")

    name = first_name(lead)
    greeting = t["greeting"].format(name=name) if name else t["greeting_plain"]

    lines = [greeting, "", message.strip(), ""]
    for label, value in _facts(
        settings, lead=lead, prop=prop, request=request,
        total_cents=total_cents, locale=locale,
    ):
        lines.append(f"{label} : {value}" if locale == "fr" else f"{label}: {value}")
    lines += [t["taxes"], ""]

    lines.append(t["valid"].format(
        days=settings.offer_valid_days,
        date=long_date(valid_until(settings, today), locale),
    ))
    lines.append("")

    lines.append(t["included_head"])
    lines += [f"  - {item}" for item in t["included"]]
    lines += ["", t["accept"], ""]

    lines += [
        settings.business_name,
        settings.business_phone,
        bare_address(settings.mail_reply_to or settings.mail_from),
        f"{settings.site_url}{'/conditions' if locale == 'fr' else '/en/terms'}",
    ]
    return subject, "\n".join(lines)


# --------------------------------------------------------------------------
# The logo
# --------------------------------------------------------------------------

LOGO_CID = "proline-logo"


@lru_cache(maxsize=1)
def logo_bytes(frontend_dir: str) -> bytes | None:
    """The badge, read once, or None if it is not where we expect.

    A missing logo must never cost a quote. The HTML degrades to the wordmark
    alone -- which is what the email looked like before this existed -- rather
    than raising at the moment Amine presses send.

    `logo-email.png` rather than `logo.png`: the site's copy is 160px and 47 KB,
    and this is rendered at 48. Mailing three times the bytes for pixels nobody
    sees is the sort of thing that only shows up in someone's data cap.
    """
    roots = [pathlib.Path(frontend_dir)] if frontend_dir else []
    roots.append(pathlib.Path(__file__).resolve().parents[3] / "frontend")
    for root in roots:
        candidate = root / "img" / "logo-email.png"
        try:
            if candidate.is_file():
                return candidate.read_bytes()
        except OSError:  # pragma: no cover - unreadable file on the box
            continue
    logger.warning("offer.logo.missing", looked_in=[str(r) for r in roots])
    return None


# --------------------------------------------------------------------------
# The HTML alternative
# --------------------------------------------------------------------------

# Table layout and inline styles, which is not how anyone writes HTML in 2026 --
# it is how email clients still render it. Outlook has no flexbox and strips a
# <style> block; a stylesheet here would leave the quote unstyled for a share of
# recipients that is small, unknowable, and disproportionately corporate.
#
# No images, no web fonts, no tracking pixel: every one of those is a reason for
# a mail client to show "this message has blocked content" above a quote, which
# is the last thing a stranger deciding whether to trust you with their keys
# needs to see.

_NAVY = "#1d396e"
_INK = "#16223a"
_BODY = "#4a5568"
_LINE = "#e2e6ee"
_CREAM = "#faf7ee"
_GOLD = "#c9992e"


def render_html(
    settings: Settings,
    *,
    lead: Lead,
    prop: Property,
    message: str,
    total_cents: int,
    request: QuoteRequest | None = None,
    today: dt.date | None = None,
    with_logo: bool = True,
) -> str:
    locale = locale_of(lead)
    t = T[locale]
    fmt = money if locale == "fr" else money_en
    name = first_name(lead)
    greeting = t["greeting"].format(name=name) if name else t["greeting_plain"]

    rows = _facts(
        settings, lead=lead, prop=prop, request=request,
        total_cents=total_cents, locale=locale,
    )
    # The price gets its own panel rather than a table row; the rest are facts.
    facts = [r for r in rows if r[0] != t["price"]]

    fact_html = "".join(
        f'<tr>'
        f'<td style="padding:3px 16px 3px 0;color:{_BODY};font-size:14px;'
        f'white-space:nowrap;vertical-align:top">{escape(label)}</td>'
        f'<td style="padding:3px 0;color:{_INK};font-size:14px">{escape(value)}</td>'
        f"</tr>"
        for label, value in facts
    )

    included = "".join(
        f'<tr><td style="padding:2px 0;color:{_BODY};font-size:14px">'
        f'<span style="color:{_GOLD};font-weight:700">&#10003;</span>&nbsp;&nbsp;'
        f"{escape(item)}</td></tr>"
        for item in t["included"]
    )

    paragraphs = "".join(
        f'<p style="margin:0 0 12px;color:{_BODY};font-size:15px;line-height:1.6">'
        f"{escape(block)}</p>"
        for block in message.strip().split("\n\n")
        if block.strip()
    )

    # Fixed width and height attributes as well as the CSS: Outlook ignores the
    # style and would otherwise draw the badge at its natural size.
    logo_cell = (
        f'<td style="padding-right:12px;vertical-align:middle">'
        f'<img src="cid:{LOGO_CID}" width="44" height="44" alt=""'
        f' style="display:block;width:44px;height:44px;border:0"></td>'
    ) if with_logo else ""

    terms_path = "/conditions" if locale == "fr" else "/en/terms"
    phone_digits = "+1" + "".join(c for c in settings.business_phone if c.isdigit())
    reply_to = bare_address(settings.mail_reply_to or settings.mail_from)

    return f"""<!doctype html>
<html lang="{locale}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(settings.business_name)}</title></head>
<body style="margin:0;padding:0;background:{_CREAM};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"
       style="background:{_CREAM};padding:24px 12px">
<tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"
       style="max-width:560px;background:#ffffff;border:1px solid {_LINE};
              border-radius:10px;overflow:hidden;
              font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif">

  <tr><td style="height:4px;background:{_GOLD};font-size:0;line-height:0">&nbsp;</td></tr>

  <tr><td style="padding:24px 30px 0">
    <table role="presentation" cellpadding="0" cellspacing="0"><tr>
      {logo_cell}
      <td style="vertical-align:middle">
        <div style="font-size:15px;font-weight:700;letter-spacing:.08em;color:{_NAVY};
                    line-height:1.2">{escape(settings.business_name.upper())}</div>
        <div style="font-size:12px;color:{_BODY};letter-spacing:.04em">{escape(t["tagline"])}</div>
      </td>
    </tr></table>
  </td></tr>

  <tr><td style="padding:22px 30px 0">
    <p style="margin:0 0 14px;color:{_INK};font-size:15px">{escape(greeting)}</p>
    {paragraphs}
  </td></tr>

  <tr><td style="padding:6px 30px 0">
    <table role="presentation" cellpadding="0" cellspacing="0" width="100%">{fact_html}</table>
  </td></tr>

  <tr><td style="padding:18px 30px 0">
    <table role="presentation" cellpadding="0" cellspacing="0" width="100%"
           style="background:{_CREAM};border-radius:8px">
      <tr><td style="padding:16px 18px">
        <div style="font-size:30px;font-weight:700;color:{_NAVY};line-height:1.1">
          {escape(fmt(total_cents))}</div>
        <div style="margin-top:4px;color:{_BODY};font-size:13px">
          {escape(period_words(request, locale))} &middot; {escape(t["taxes"])}</div>
      </td></tr>
    </table>
  </td></tr>

  <tr><td style="padding:16px 30px 0">
    <div style="font-size:11px;font-weight:700;letter-spacing:.1em;
                text-transform:uppercase;color:{_BODY};margin-bottom:6px">
      {escape(t["included_head"])}</div>
    <table role="presentation" cellpadding="0" cellspacing="0" width="100%">{included}</table>
  </td></tr>

  <tr><td style="padding:18px 30px 0">
    <p style="margin:0;color:{_BODY};font-size:14px;line-height:1.6">
      {escape(t["accept"])}</p>
    <p style="margin:10px 0 0;color:{_BODY};font-size:13px">
      {escape(t["valid"].format(days=settings.offer_valid_days,
                                date=long_date(valid_until(settings, today), locale)))}</p>
  </td></tr>

  <tr><td style="padding:22px 30px 26px">
    <table role="presentation" cellpadding="0" cellspacing="0" width="100%"
           style="border-top:1px solid {_LINE}">
      <tr><td style="padding-top:14px;color:{_BODY};font-size:13px;line-height:1.7">
        <strong style="color:{_INK}">{escape(settings.business_name)}</strong><br>
        <a href="tel:{escape(phone_digits)}"
           style="color:{_NAVY};text-decoration:none">{escape(settings.business_phone)}</a>
        &nbsp;&middot;&nbsp;
        <a href="mailto:{escape(reply_to)}"
           style="color:{_NAVY};text-decoration:none">{escape(reply_to)}</a><br>
        <a href="{escape(settings.site_url + terms_path)}"
           style="color:{_BODY}">{escape(t["terms"])}</a>
      </td></tr>
    </table>
  </td></tr>

</table>
</td></tr></table>
</body></html>"""


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

    ONLY THE TEXT IS STORED. The HTML is a presentation of the same facts, and
    keeping two copies of one quote invites the question of which one is the
    quote. The text part is what a court, or an argument six months from now,
    would read.
    """
    subject, text = render(
        settings, lead=lead, prop=prop, message=message,
        total_cents=total_cents, request=request,
    )
    logo = logo_bytes(settings.frontend_dir or "")
    html = render_html(
        settings, lead=lead, prop=prop, message=message,
        total_cents=total_cents, request=request, with_logo=logo is not None,
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
            build_message(
                settings, to=lead.email, subject=subject, text=text, html=html,
                inline={LOGO_CID: (logo, "png")} if logo else None,
            ),
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


