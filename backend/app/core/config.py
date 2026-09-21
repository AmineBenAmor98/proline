"""Settings, validated at boot. A missing key fails the deploy, not the first client."""

from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["local", "staging", "production"] = "local"
    database_url: str = "postgresql+asyncpg://proline:proline@localhost:5432/proline"
    frontend_dir: str = ""

    # Admin sign-in. Change these in .env before the site is public.
    admin_username: str = "admin"
    admin_password: str = "proline"
    secret_key: str = "dev-secret-change-me"

    resend_api_key: str = ""
    notify_email_from: str = "soumissions@example.ca"
    notify_email_to: str = ""
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from: str = ""
    notify_sms_to: str = ""

    sentry_dsn: str = ""

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
            (self.resend_api_key and self.notify_email_to)
            or (self.twilio_account_sid and self.notify_sms_to)
        )
        return configured and self.environment != "local"


@lru_cache
def get_settings() -> Settings:
    return Settings()
