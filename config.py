from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: str
    api_id: int | None = None
    api_hash: str | None = None

    xrocket_api_key: str
    xrocket_base_url: str = "https://pay.api.xrocket.exchange"

    admins: str = "marcenzo,shibainuo"
    admin_ids: str = ""  # optional: 123456789,987654321

    database_url: str = "sqlite+aiosqlite:///./data/loan_bot.db"

    default_currency: str = "USDT"
    min_loan_amount: float = 0.10
    max_loan_amount: float = 100.0
    initial_credit_limit: float = 5.0
    credit_multiplier: float = 2.0
    successful_loans_for_upgrade: int = 3
    default_installments: int = 5
    max_installments: int = 10
    late_fee_percent: float = 5.0

    default_language: str = "en"
    support_username: str = "marcenzo"

    @property
    def admin_list(self) -> List[str]:
        return [a.strip().lower().lstrip("@") for a in self.admins.split(",") if a.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
