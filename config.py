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

    # Legacy (optional if using Polygon only)
    xrocket_api_key: str = ""
    xrocket_base_url: str = "https://pay.api.xrocket.exchange"

    # Polygon USDT payments
    polygon_rpc_url: str = "https://polygon-rpc.com"
    polygon_private_key: str = ""  # treasury hot wallet — ONLY in server .env
    treasury_address: str = ""  # 0x... main wallet that receives sweeps + sends loans

    admins: str = "marcenzo,shibainuo"
    admin_ids: str = ""

    database_url: str = "sqlite+aiosqlite:///./data/loan_bot.db"

    default_currency: str = "USDT"
    min_loan_amount: float = 0.10
    max_loan_amount: float = 100.0
    initial_credit_limit: float = 5.0
    credit_multiplier: float = 2.0
    successful_loans_for_upgrade: int = 3
    default_installments: int = 1
    max_installments: int = 10
    loan_interest_percent: float = 10.0
    interest_period_days: int = 7
    late_increase_percent: float = 1.0
    installment_period_days: int = 7
    min_invest_amount: float = 1.0
    investor_weekly_target_percent: float = 10.0

    default_language: str = "en"
    support_username: str = "marcenzo"
    bot_username: str = "See30bot"

    @property
    def admin_list(self) -> List[str]:
        return [a.strip().lower().lstrip("@") for a in self.admins.split(",") if a.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
