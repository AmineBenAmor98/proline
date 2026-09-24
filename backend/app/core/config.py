"""Settings, validated at boot. A missing key fails the deploy, not the first client."""

from functools import lru_cache
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Hosts hand out libpq connection strings, because libpq is what psql and every
# ORM in every other language expects. We drive asyncpg, which wants neither
# half of that string as given:
#
#   postgresql://…?sslmode=require        <- what DigitalOcean's database
#                                            binding injects
#   postgresql+asyncpg://…?ssl=require    <- what this app can actually open
#
# The scheme is the loud failure: SQLAlchemy reads `postgresql://` as the sync
# psycopg2 dialect and create_async_engine dies at import with a missing module.
#
# `sslmode` is the quiet one, and the reason this is normalised rather than
# documented. SQLAlchemy passes unknown query parameters through to the driver
# untouched, so `sslmode` reaches asyncpg.connect(), which has no such argument
# -- and that is a TypeError on the FIRST CONNECTION, not at boot. The container
# starts, the health check passes, and the site 500s the first time a visitor
# asks for a price.
_SSLMODE_TO_ASYNCPG = {
    "require": "require",
    "verify-ca": "verify-full",
    "verify-full": "verify-full",
    "prefer": "prefer",
    "allow": "prefer",
    "disable": "disable",
}


def normalise_database_url(url: str) -> str:
    """Accept what a managed-Postgres provider gives; return what asyncpg opens."""
    parts = urlsplit(url)
    if parts.scheme in ("postgres", "postgresql"):
        parts = parts._replace(scheme="postgresql+asyncpg")
    elif not parts.scheme.startswith("postgresql+asyncpg"):
        return url  # not ours to touch: sqlite in a test, or a driver set on purpose

    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    mode = query.pop("sslmode", None)
    if mode and "ssl" not in query:
        # An unknown value is left to fail loudly at connect rather than being
        # guessed into something weaker than what was asked for.
        query["ssl"] = _SSLMODE_TO_ASYNCPG.get(mode.lower(), mode)
    return urlunsplit(parts._replace(query=urlencode(query)))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["local", "staging", "production"] = "local"
    database_url: str = "postgresql+asyncpg://proline:proline@localhost:5432/proline"
    frontend_dir: str = ""

    # Admin sign-in. Change these in .env before the site is public.
    admin_username: str = "admin"
    admin_password: str = "proline"
    secret_key: str = "dev-secret-change-me"

    # SMTP, not a vendor API. See app/services/mailer.py for why: every provider
    # speaks it, so changing provider is these five values and a redeploy.
    # Amazon SES: email-smtp.ca-central-1.amazonaws.com:587 with SES SMTP
    # credentials (which are NOT your AWS access keys).
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True

    # What the client sees, and where their reply lands. The reply address is a
    # real mailbox on the domain; the sending host above is not.
    mail_from: str = "Proline Cleaning Solutions <info@prolinecleaningsolutions.ca>"
    mail_reply_to: str = ""

    notify_email_to: str = ""
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from: str = ""
    notify_sms_to: str = ""

    sentry_dsn: str = ""

    @field_validator("database_url")
    @classmethod
    def _asyncpg_url(cls, value: str) -> str:
        """Done here, not in db/session.py, because Alembic reads this same
        setting through migrations/env.py: normalising at one of the two call
        sites would leave the other failing on the deploy that runs them both."""
        return normalise_database_url(value)

    # Every default below is a development convenience and a production hole.
    _INSECURE_DEFAULTS = {
        "admin_username": "admin",
        "admin_password": "proline",
        "secret_key": "dev-secret-change-me",
    }

    @model_validator(mode="after")
    def _refuse_insecure_production(self) -> "Settings":
        """The module docstring promises this; without it a forgotten env var
        ships /admin with admin/proline and a known signing key."""
        if self.environment != "production":
            return self
        left = [
            name
            for name, default in self._INSECURE_DEFAULTS.items()
            if getattr(self, name) == default
        ]
        if left:
            raise ValueError(
                "refusing to start in production with default "
                + ", ".join(sorted(left))
                + ": set them in the environment"
            )
        return self

    @property
    def notifications_enabled(self) -> bool:
        """SMS alone is a valid setup: gating on Resend made a Twilio-only
        deployment save every lead and tell nobody."""
        configured = bool(
            (self.smtp_host and self.notify_email_to)
            or (self.twilio_account_sid and self.notify_sms_to)
        )
        return configured and self.environment != "local"


@lru_cache
def get_settings() -> Settings:
    return Settings()
