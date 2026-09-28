"""Sending mail, over SMTP, deliberately.

This used to POST to Resend's REST API. It speaks SMTP now, and the reason is
not technical elegance -- it is that choosing an email provider took an
afternoon and changed four times, and the code should not have had a vote.

Every provider worth using speaks SMTP: Amazon SES, Resend, Zoho, Postmark,
Google Workspace. So the provider is five environment variables, and switching
is a redeploy with different values rather than a rewrite. Given how much this
deployment moved between vendors before it ever launched, that portability is
worth more than the marginal ergonomics of any one vendor's SDK.

Nothing here retries. A transient failure on a lead notification is logged and
the lead survives in the database; a failure on an offer is reported to Amine
in the admin, where a person decides whether to send it again. Silent retries
are how a client receives the same quote three times.
"""

from __future__ import annotations

from email.message import EmailMessage

import aiosmtplib

from app.core.config import Settings
from app.core.logging import logger


class MailNotConfigured(RuntimeError):
    """Raised rather than logged when a person is waiting on the result.

    `notify_new_request` treats an unconfigured mailer as "log it and move on",
    because the visitor's submission already succeeded. Sending an offer is the
    opposite: Amine pressed a button and is owed an answer, so this surfaces as
    a 503 with something he can act on.
    """


def build_message(
    settings: Settings,
    *,
    to: str,
    subject: str,
    text: str,
    html: str | None = None,
    inline: dict[str, tuple[bytes, str]] | None = None,
) -> EmailMessage:
    """Text always; HTML as an alternative when one is given.

    This used to be text-only on the argument that an HTML part "would only give
    it more ways to render badly". That argument is right about the risk and
    wrong about the remedy: multipart/alternative carries BOTH, and a client
    that would have rendered the HTML badly is a client that shows the text
    instead. Text-only did not avoid the bad rendering -- it chose it for
    everyone, on a document quoting a stranger four figures.

    The text part is written first and stays the record of what was sent. Order
    matters in multipart/alternative: least-rich first, and a reader shows the
    last part it understands.
    """
    message = EmailMessage()
    message["From"] = settings.mail_from
    message["To"] = to
    message["Subject"] = subject
    # Reply-To matters more than it looks: mail is SENT through the provider
    # (SES, say) but RECEIVED at the mailbox on the domain, and without this a
    # client's reply goes to whatever bounce address the provider used.
    message["Reply-To"] = settings.mail_reply_to or settings.mail_from
    message.set_content(text)
    if html:
        message.add_alternative(html, subtype="html")
        # Images travel WITH the message, referenced as cid:, never fetched from
        # our server. A remote <img> is what makes a mail client print "this
        # message has blocked content" across the top of a quote -- to a stranger
        # deciding whether to trust us with their keys -- and it doubles as a
        # read receipt the recipient never agreed to.
        #
        # They attach to the HTML part, not the message: attaching to the message
        # would make it multipart/mixed and the logo would arrive as a file to
        # download rather than a picture in the layout.
        for cid, (data, subtype) in (inline or {}).items():
            message.get_payload()[-1].add_related(
                data, maintype="image", subtype=subtype, cid=f"<{cid}>"
            )
    return message


async def send(settings: Settings, message: EmailMessage) -> None:
    """Deliver one message, or raise.

    Errors are not swallowed here. Each caller knows whether someone is waiting.
    """
    if not settings.smtp_host:
        raise MailNotConfigured("SMTP_HOST is not set")

    await aiosmtplib.send(
        message,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_user or None,
        password=settings.smtp_password or None,
        start_tls=settings.smtp_starttls,
        timeout=20,
    )
    logger.info(
        "mail.sent",
        to=message["To"],
        subject=message["Subject"],
        host=settings.smtp_host,
    )
