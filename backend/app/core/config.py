"""Settings, validated at boot. A missing key fails the deploy, not the first client."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["local", "staging", "production"] = "local"
    database_url: str = "postgresql+asyncpg://proline:proline@localhost:5432/proline"
    frontend_dir: str = ""

    # Sprint 1 admin access: a shared token in the env. Replaced by real auth in sprint 4.
    admin_token: str = ""

    resend_api_key: str = ""
    notify_email_from: str = "soumissions@example.ca"
    notify_email_to: str = ""
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from: str = ""
    notify_sms_to: str = ""

    sentry_dsn: str = ""

    @property
    def notifications_enabled(self) -> bool:
        return bool(self.resend_api_key) and self.environment != "local"


@lru_cache
def get_settings() -> Settings:
    return Settings()
