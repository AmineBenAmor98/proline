"""Email and SMS. In local dev nothing is sent; the payload is logged instead."""

from __future__ import annotations

import httpx

from app.core.config import Settings
from app.core.logging import logger
from app.services.mailer import build_message, send


async def _send_email(
    client: httpx.AsyncClient, settings: Settings, request_id: str, summary: str
) -> None:
    """The lead alert. Plain text on purpose: it is read on a phone, usually
    while holding something, and the only job is to say a lead arrived and what
    it was."""
    await send(
        settings,
        build_message(
            settings,
            to=settings.notify_email_to,
            subject=f"Nouvelle demande de soumission — {request_id[:8]}",
            text=summary,
        ),
    )


async def _send_sms(
    client: httpx.AsyncClient, settings: Settings, request_id: str, summary: str
) -> None:
    response = await client.post(
        f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json",
        auth=(settings.twilio_account_sid, settings.twilio_auth_token),
        data={
            "From": settings.twilio_from,
            "To": settings.notify_sms_to,
            "Body": f"Proline: nouvelle demande {request_id[:8]}. {summary[:120]}",
        },
    )
    response.raise_for_status()


async def notify_new_request(settings: Settings, *, request_id: str, summary: str) -> None:
    """Best effort, and loudly logged when it fails.

    The request is already saved by the time we get here, so a provider outage
    must never surface as a failed submission — but it must not vanish either:
    a channel that raises is logged with its name so the lead can be chased.
    """
    if not settings.notifications_enabled:
        logger.info("notification.skipped", request_id=request_id, summary=summary)
        return

    channels = []
    if settings.smtp_host and settings.notify_email_to:
        channels.append(("email", _send_email))
    if settings.twilio_account_sid and settings.notify_sms_to:
        channels.append(("sms", _send_sms))

    sent, failed = [], []
    async with httpx.AsyncClient(timeout=10) as client:
        for name, channel_send in channels:
            try:
                # Each channel raises on a provider-level refusal, so a 401 or a
                # rejected recipient is a failure even though the call returned.
                await channel_send(client, settings, request_id, summary)
            except Exception as exc:  # provider outage, DNS, timeout
                failed.append(name)
                logger.error(
                    "notification.failed",
                    request_id=request_id,
                    channel=name,
                    error=str(exc),
                    summary=summary,
                )
            else:
                sent.append(name)

    if sent:
        logger.info("notification.sent", request_id=request_id, channels=sent)
    if failed and not sent:
        # Nobody was told at all: the summary goes to the log so the lead survives.
        logger.error("notification.undelivered", request_id=request_id, summary=summary)
