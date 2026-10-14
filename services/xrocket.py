"""
xRocket Pay client — Current Pay API (Bearer JWT).
Legacy Rocket-Pay-Key is only used for non-JWT keys.
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
        self.base_url = (settings.xrocket_base_url or "https://pay.api.xrocket.exchange").rstrip("/")
        self.api_key = (settings.xrocket_api_key or "").strip()
        self._client = httpx.AsyncClient(timeout=30.0)
        # JWT tokens must use Authorization: Bearer on Pay API only.
        self._is_jwt = self.api_key.count(".") >= 2 and self.api_key.startswith("eyJ")

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

    def _extract_error(self, response: httpx.Response) -> str:
        body_text = response.text or ""
        try:
            data = response.json()
            if isinstance(data, dict):
                msg = (
                    data.get("detail")
                    or data.get("title")
                    or data.get("message")
                    or data.get("error")
                    or body_text[:300]
                )
                if isinstance(msg, list):
                    msg = "; ".join(str(x) for x in msg)
                return str(msg)
        except Exception:
            pass
        return body_text[:300] or f"HTTP {response.status_code}"

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
                raise XRocketError(
                    self._extract_error(response),
                    status_code=response.status_code,
                    payload=body_text,
                )
            if response.status_code == 204 or not body_text:
                return None
            data = response.json()
            if isinstance(data, dict) and "success" in data:
                if not data.get("success"):
                    raise XRocketError(
                        str(data.get("message") or "API error"),
                        status_code=response.status_code,
                        payload=data,
                    )
                return data.get("data", data)
            return data
        except httpx.RequestError as e:
            logger.exception("xRocket network error")
            raise XRocketError(f"Network error: {e}") from e

    async def get_app_info(self) -> dict:
        if not self.api_key:
            raise XRocketError("XROCKET_API_KEY is empty in .env")

        if self._is_jwt:
            # Current Pay API
            for path in ("/api/v1/app-info", "/api/v1/app", "/api/v1/balances"):
                try:
                    return await self._request(
                        "GET", f"{self.base_url}{path}", headers=self._bearer_headers()
                    )
                except XRocketError as e:
                    last = e
                    continue
            raise last  # type: ignore[name-defined]

        # Legacy key
        for host in ("https://pay.xrocket.tg", "https://pay.xrocket.exchange"):
            try:
                return await self._request(
                    "GET", f"{host}/app/info", headers=self._legacy_headers()
                )
            except XRocketError as e:
                last = e
        raise last  # type: ignore[name-defined]

    async def create_payout(
        self,
        *,
        telegram_user_id: int,
        amount: str | float,
        asset: str = "USDT",
        description: str = "Loan disbursement",
        client_payout_id: str | None = None,
    ) -> dict:
        if not self.api_key:
            raise XRocketError(
                "XROCKET_API_KEY missing. Put your token in .env as XROCKET_API_KEY=..."
            )

        cid = (client_payout_id or str(uuid.uuid4()).replace("-", ""))[:50]
        amount_str = f"{float(amount):.2f}"

        # ---------- Current Pay API (JWT) ----------
        if self._is_jwt:
            payload = {
                "clientPayoutId": cid,
                "target": str(telegram_user_id),
                "targetType": "telegram_user_id",
                "asset": asset,
                "amount": amount_str,
                "description": (description or "Loan")[:200],
            }
            url = f"{self.base_url}/api/v1/payouts"
            try:
                result = await self._request(
                    "POST", url, headers=self._bearer_headers(), json=payload
                )
                logger.info("Payout OK (Pay API): {}", result)
                return result if isinstance(result, dict) else {"raw": result}
            except XRocketError as e:
                # Do NOT fall back to Legacy with a JWT — causes "Unknown API Key"
                raise XRocketError(
                    f"Pay API: {e}"
                    + (
                        " | Check: 1) token from @xRocket → app → Settings → API Token "
                        "2) API Version = Current 3) app has USDT balance 4) .env has full key"
                        if e.status_code in (401, 403, None)
                        or "key" in str(e).lower()
                        or "auth" in str(e).lower()
                        or "unauthorized" in str(e).lower()
                        else ""
                    ),
                    status_code=e.status_code,
                    payload=e.payload,
                ) from e

        # ---------- Legacy (non-JWT Rocket-Pay-Key) ----------
        legacy_body = {
            "tgUserId": int(telegram_user_id),
            "currency": asset,
            "amount": float(amount_str),
            "transferId": cid,
            "description": (description or "Loan")[:200],
        }
        last_err: Exception | None = None
        for host in ("https://pay.xrocket.tg", "https://pay.xrocket.exchange"):
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

        raise XRocketError(
            str(last_err or "Payout failed"),
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
        if not self.api_key:
            raise XRocketError("XROCKET_API_KEY missing in .env")

        amount_str = f"{float(amount):.2f}"
        cid = (client_invoice_id or str(uuid.uuid4()).replace("-", ""))[:50]

        if self._is_jwt:
            payload: dict[str, Any] = {
                "priceAmount": amount_str,
                "priceCurrency": currency,
                "payoutCurrency": currency,
                "payCurrencies": [currency],
                "numPayments": 1,
                "description": (description or "Payment")[:200],
                "expiresIn": expires_in,
                "clientInvoiceId": cid,
            }
            if telegram_id:
                payload["customer"] = {"telegramId": str(telegram_id)}

            return await self._request(
                "POST",
                f"{self.base_url}/api/v1/invoices",
                headers=self._bearer_headers(),
                json=payload,
            )

        legacy_body = {
            "amount": float(amount_str),
            "currency": currency,
            "description": (description or "Payment")[:200],
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
        if self._is_jwt:
            return await self._request(
                "GET",
                f"{self.base_url}/api/v1/invoice",
                headers=self._bearer_headers(),
                params={"invoiceId": invoice_id},
            )
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
