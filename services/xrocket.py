"""
xRocket Pay API client (current Pay API).
Docs: https://docs.xrocket.exchange/api/pay/
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

import httpx
from loguru import logger

from config import get_settings


class XRocketError(Exception):
    def __init__(self, message: str, status_code: int | None = None, payload: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class XRocketClient:
    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = settings.xrocket_base_url.rstrip("/")
        self.api_key = settings.xrocket_api_key
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        json: dict | None = None,
        params: dict | None = None,
    ) -> Any:
        url = f"/api/v1{path}"
        try:
            response = await self._client.request(method, url, json=json, params=params)
            if response.status_code >= 400:
                logger.error(
                    "xRocket error {} {} → {} {}",
                    method,
                    url,
                    response.status_code,
                    response.text,
                )
                raise XRocketError(
                    f"xRocket API error {response.status_code}",
                    status_code=response.status_code,
                    payload=response.text,
                )
            if response.status_code == 204:
                return None
            return response.json()
        except httpx.RequestError as e:
            logger.exception("xRocket network error")
            raise XRocketError(f"Network error: {e}") from e

    # ------------------------------------------------------------------
    # App / Balance
    # ------------------------------------------------------------------
    async def get_app_info(self) -> dict:
        return await self._request("GET", "/app")

    # ------------------------------------------------------------------
    # Payout (send money to user) — used when issuing a loan
    # ------------------------------------------------------------------
    async def create_payout(
        self,
        *,
        telegram_user_id: int,
        amount: str | float,
        asset: str = "USDT",
        description: str = "Loan disbursement",
        client_payout_id: str | None = None,
        callback_url: str | None = None,
    ) -> dict:
        """
        Send funds to a Telegram user via xRocket wallet.
        targetType = telegram_user_id
        """
        payload: dict[str, Any] = {
            "clientPayoutId": client_payout_id or str(uuid.uuid4()),
            "target": str(telegram_user_id),
            "targetType": "telegram_user_id",
            "asset": asset,
            "amount": str(amount),
            "description": description,
        }
        if callback_url:
            payload["callback"] = {"callbackUrl": callback_url}

        return await self._request("POST", "/payouts", json=payload)

    # ------------------------------------------------------------------
    # Invoice (receive money) — used for installment repayments
    # ------------------------------------------------------------------
    async def create_invoice(
        self,
        *,
        amount: str | float,
        currency: str = "USDT",
        description: str = "Loan installment repayment",
        client_invoice_id: str | None = None,
        expires_in: int = 86400 * 7,  # 7 days
        callback_url: str | None = None,
        telegram_id: int | None = None,
    ) -> dict:
        payload: dict[str, Any] = {
            "priceAmount": str(amount),
            "priceCurrency": currency,
            "payoutCurrency": currency,
            "payCurrencies": [currency],
            "numPayments": 1,
            "description": description,
            "expiresIn": expires_in,
            "clientInvoiceId": client_invoice_id or str(uuid.uuid4()),
        }
        if callback_url:
            payload["callback"] = {"callbackUrl": callback_url}
        if telegram_id:
            payload["customer"] = {"telegramId": str(telegram_id)}

        return await self._request("POST", "/invoices", json=payload)

    async def get_invoice(self, invoice_id: str) -> dict:
        return await self._request("GET", "/invoice", params={"invoiceId": invoice_id})

    async def get_invoice_payments(self, invoice_id: str) -> dict:
        return await self._request(
            "GET", "/invoice/payments", params={"invoiceId": invoice_id}
        )


# Singleton-style helper
_xrocket: Optional[XRocketClient] = None


def get_xrocket() -> XRocketClient:
    global _xrocket
    if _xrocket is None:
        _xrocket = XRocketClient()
    return _xrocket
