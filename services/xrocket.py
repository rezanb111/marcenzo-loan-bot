"""
xRocket Pay client — Current Pay API + Legacy fallback.
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
        self.api_key = settings.xrocket_api_key.strip()
        self._client = httpx.AsyncClient(timeout=30.0)

    async def close(self) -> None:
        await self._client.aclose()

    def _bearer_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _legacy_headers(self) -> dict:
        return {
            "Rocket-Pay-Key": self.api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        url: str,
        *,
        headers: dict,
        json: dict | None = None,
        params: dict | None = None,
    ) -> Any:
        try:
            response = await self._client.request(
                method, url, headers=headers, json=json, params=params
            )
            body_text = response.text
            if response.status_code >= 400:
                logger.error(
                    "xRocket {} {} → {} {}",
                    method,
                    url,
                    response.status_code,
                    body_text[:800],
                )
                # Extract readable message
                msg = body_text[:300]
                try:
                    data = response.json()
                    if isinstance(data, dict):
                        msg = (
                            data.get("message")
                            or data.get("detail")
                            or data.get("title")
                            or data.get("error")
                            or msg
                        )
                        if isinstance(msg, list):
                            msg = str(msg)
                except Exception:
                    pass
                raise XRocketError(
                    str(msg),
                    status_code=response.status_code,
                    payload=body_text,
                )
            if response.status_code == 204 or not body_text:
                return None
            data = response.json()
            # Legacy envelope
            if isinstance(data, dict) and "success" in data:
                if not data.get("success"):
                    raise XRocketError(
                        str(data.get("message") or "Legacy API error"),
                        status_code=response.status_code,
                        payload=data,
                    )
                return data.get("data", data)
            return data
        except httpx.RequestError as e:
            logger.exception("xRocket network error")
            raise XRocketError(f"Network error: {e}") from e

    async def get_app_info(self) -> dict:
        url = f"{self.base_url}/api/v1/app"
        try:
            return await self._request("GET", url, headers=self._bearer_headers())
        except XRocketError:
            # Legacy
            legacy_base = "https://pay.xrocket.tg"
            return await self._request(
                "GET", f"{legacy_base}/app/info", headers=self._legacy_headers()
            )

    async def create_payout(
        self,
        *,
        telegram_user_id: int,
        amount: str | float,
        asset: str = "USDT",
        description: str = "Loan disbursement",
        client_payout_id: str | None = None,
    ) -> dict:
        """
        Send funds to a Telegram user.
        Tries Current Pay API first, then Legacy /app/transfer.
        """
        cid = (client_payout_id or str(uuid.uuid4()).replace("-", ""))[:50]
        amount_str = f"{float(amount):.2f}"

        # --- Current Pay API ---
        payload = {
            "clientPayoutId": cid,
            "target": str(telegram_user_id),
            "targetType": "telegram_user_id",
            "asset": asset,
            "amount": amount_str,
            "description": description[:200],
        }
        url = f"{self.base_url}/api/v1/payouts"
        try:
            result = await self._request(
                "POST", url, headers=self._bearer_headers(), json=payload
            )
            logger.info("Payout OK (Pay API): {}", result)
            return result if isinstance(result, dict) else {"raw": result}
        except XRocketError as e:
            logger.warning("Pay API payout failed ({}), trying Legacy…", e)

        # --- Legacy API ---
        # Docs: POST /app/transfer with Rocket-Pay-Key
        legacy_hosts = [
            "https://pay.xrocket.tg",
            "https://pay.xrocket.exchange",
        ]
        legacy_body = {
            "tgUserId": int(telegram_user_id),
            "currency": asset,
            "amount": float(amount_str),
            "transferId": cid,
            "description": description[:200],
        }
        last_err: Exception | None = None
        for host in legacy_hosts:
            try:
                result = await self._request(
                    "POST",
                    f"{host}/app/transfer",
                    headers=self._legacy_headers(),
                    json=legacy_body,
                )
                logger.info("Payout OK (Legacy {}): {}", host, result)
                return result if isinstance(result, dict) else {"raw": result}
            except XRocketError as e:
                last_err = e
                logger.warning("Legacy {} failed: {}", host, e)

        # Also try TONCOIN alias if USDT failed on Pay API only path already done
        if asset.upper() == "USDT":
            for alt in ("USDTTRC20", "USDT_TON", "TONCOIN"):
                try:
                    payload_alt = dict(payload)
                    payload_alt["asset"] = alt
                    payload_alt["clientPayoutId"] = (cid + alt[:4])[:50]
                    result = await self._request(
                        "POST", url, headers=self._bearer_headers(), json=payload_alt
                    )
                    logger.info("Payout OK with asset {}: {}", alt, result)
                    return result if isinstance(result, dict) else {"raw": result}
                except XRocketError:
                    continue

        raise XRocketError(
            str(last_err or "Payout failed on all endpoints"),
            status_code=getattr(last_err, "status_code", None),
            payload=getattr(last_err, "payload", None),
        )

    async def create_invoice(
        self,
        *,
        amount: str | float,
        currency: str = "USDT",
        description: str = "Loan installment repayment",
        client_invoice_id: str | None = None,
        expires_in: int = 86400 * 7,
        telegram_id: int | None = None,
    ) -> dict:
        amount_str = f"{float(amount):.2f}"
        cid = (client_invoice_id or str(uuid.uuid4()).replace("-", ""))[:50]

        payload: dict[str, Any] = {
            "priceAmount": amount_str,
            "priceCurrency": currency,
            "payoutCurrency": currency,
            "payCurrencies": [currency],
            "numPayments": 1,
            "description": description[:200],
            "expiresIn": expires_in,
            "clientInvoiceId": cid,
        }
        if telegram_id:
            payload["customer"] = {"telegramId": str(telegram_id)}

        url = f"{self.base_url}/api/v1/invoices"
        try:
            return await self._request(
                "POST", url, headers=self._bearer_headers(), json=payload
            )
        except XRocketError as e:
            logger.warning("Invoice Pay API failed: {}", e)

        # Legacy invoice
        legacy_body = {
            "amount": float(amount_str),
            "currency": currency,
            "description": description[:200],
            "numPayments": 1,
            "expiredIn": expires_in,
        }
        return await self._request(
            "POST",
            "https://pay.xrocket.tg/tg-invoices",
            headers=self._legacy_headers(),
            json=legacy_body,
        )

    async def get_invoice(self, invoice_id: str) -> dict:
        try:
            return await self._request(
                "GET",
                f"{self.base_url}/api/v1/invoice",
                headers=self._bearer_headers(),
                params={"invoiceId": invoice_id},
            )
        except XRocketError:
            return await self._request(
                "GET",
                f"https://pay.xrocket.tg/tg-invoices/{invoice_id}",
                headers=self._legacy_headers(),
            )


_xrocket: Optional[XRocketClient] = None


def get_xrocket() -> XRocketClient:
    global _xrocket
    if _xrocket is None:
        _xrocket = XRocketClient()
    return _xrocket
