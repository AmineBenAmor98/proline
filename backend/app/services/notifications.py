"""Email and SMS. In local dev nothing is sent; the payload is logged instead."""

from __future__ import annotations

import httpx

from app.core.config import Settings
from app.core.logging import logger


async def notify_new_request(settings: Settings, *, request_id: str, summary: str) -> None:
    if not settings.notifications_enabled:
        logger.info("notification.skipped", request_id=request_id, summary=summary)
        return

    async with httpx.AsyncClient(timeout=10) as client:
        if settings.resend_api_key and settings.notify_email_to:
            await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
                json={
                    "from": settings.notify_email_from,
                    "to": [settings.notify_email_to],
                    "subject": f"Nouvelle demande de soumission — {request_id[:8]}",
                    "text": summary,
                },
            )

        if settings.twilio_account_sid and settings.notify_sms_to:
            await client.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json",
                auth=(settings.twilio_account_sid, settings.twilio_auth_token),
                data={
                    "From": settings.twilio_from,
                    "To": settings.notify_sms_to,
                    "Body": f"Proline: nouvelle demande {request_id[:8]}. {summary[:120]}",
                },
            )
    logger.info("notification.sent", request_id=request_id)
