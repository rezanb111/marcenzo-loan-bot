"""
Polygon (chain 137) USDT payments for Marcenzo Loan Bot.

- Each installment gets a DETERMINISTIC unique deposit address
  derived from TREASURY private key + installment id (no key storage needed).
- User pays USDT to that address.
- Sweeper: fund gas from treasury → transfer full USDT to TREASURY_ADDRESS.
- Loan disbursement: treasury sends USDT to user's polygon_wallet.

NEVER commit real private keys. Use .env only on the server.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional

from eth_account import Account
from eth_hash.auto import keccak
from loguru import logger
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

from config import get_settings

# Polygon PoS USDT (6 decimals)
USDT_ADDRESS = Web3.to_checksum_address("0xc2132D05D31c914a87C6611C10748AEb04B58e8F")
USDT_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
    },
    {
        "constant": False,
        "inputs": [
            {"name": "recipient", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "from", "type": "address"},
            {"indexed": True, "name": "to", "type": "address"},
            {"indexed": False, "name": "value", "type": "uint256"},
        ],
        "name": "Transfer",
        "type": "event",
    },
]


class PolygonError(Exception):
    pass


@dataclass
class DepositWallet:
    address: str
    installment_id: int
    user_tag: str


def _w3() -> Web3:
    settings = get_settings()
    rpc = getattr(settings, "polygon_rpc_url", None) or "https://polygon-rpc.com"
    w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 60}))
    # Polygon is POA-like for extraData
    try:
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    except Exception:
        pass
    if not w3.is_connected():
        raise PolygonError(f"Cannot connect to Polygon RPC: {rpc}")
    return w3


def _treasury_key() -> str:
    settings = get_settings()
    key = (getattr(settings, "polygon_private_key", None) or "").strip()
    if not key:
        raise PolygonError("POLYGON_PRIVATE_KEY missing in .env")
    if not key.startswith("0x"):
        key = "0x" + key
    return key


def treasury_address() -> str:
    settings = get_settings()
    addr = (getattr(settings, "treasury_address", None) or "").strip()
    if addr:
        return Web3.to_checksum_address(addr)
    return Account.from_key(_treasury_key()).address


def _usdt(w3: Web3):
    return w3.eth.contract(address=USDT_ADDRESS, abi=USDT_ABI)


def usdt_to_units(amount: Decimal | str | float) -> int:
    d = Decimal(str(amount)).quantize(Decimal("0.000001"))
    return int(d * Decimal(1_000_000))


def units_to_usdt(units: int) -> Decimal:
    return (Decimal(units) / Decimal(1_000_000)).quantize(Decimal("0.000001"))


def deposit_account_for(installment_id: int, user_telegram_id: int = 0) -> Account:
    """
    Deterministic unique EOA per installment.
    key material = keccak( treasury_priv || b'|dep|' || installment_id || b'|' || user_id )
    """
    master = _treasury_key().lower().encode()
    material = master + b"|dep|" + str(installment_id).encode() + b"|" + str(user_telegram_id).encode()
    raw = keccak(material)
    return Account.from_key(raw)


def get_deposit_wallet(installment_id: int, user_telegram_id: int = 0) -> DepositWallet:
    acc = deposit_account_for(installment_id, user_telegram_id)
    return DepositWallet(
        address=Web3.to_checksum_address(acc.address),
        installment_id=installment_id,
        user_tag=str(user_telegram_id),
    )


def get_usdt_balance(address: str) -> Decimal:
    w3 = _w3()
    bal = _usdt(w3).functions.balanceOf(Web3.to_checksum_address(address)).call()
    return units_to_usdt(int(bal))


def get_matic_balance(address: str) -> Decimal:
    w3 = _w3()
    wei = w3.eth.get_balance(Web3.to_checksum_address(address))
    return Decimal(wei) / Decimal(10**18)


def _sign_and_send(w3: Web3, signed) -> str:
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    return tx_hash.hex()


def send_usdt_from_treasury(to_address: str, amount: Decimal) -> str:
    """Disburse loan principal from main treasury to borrower."""
    w3 = _w3()
    key = _treasury_key()
    from_addr = Account.from_key(key).address
    to_addr = Web3.to_checksum_address(to_address)
    units = usdt_to_units(amount)
    if units <= 0:
        raise PolygonError("Amount must be positive")

    contract = _usdt(w3)
    treasury_bal = contract.functions.balanceOf(from_addr).call()
    if treasury_bal < units:
        raise PolygonError(
            f"Treasury USDT insufficient: have {units_to_usdt(treasury_bal)}, need {amount}"
        )

    nonce = w3.eth.get_transaction_count(from_addr)
    gas_price = int(w3.eth.gas_price * 1.2)
    tx = contract.functions.transfer(to_addr, units).build_transaction(
        {
            "from": from_addr,
            "nonce": nonce,
            "gas": 120_000,
            "gasPrice": gas_price,
            "chainId": 137,
        }
    )
    signed = w3.eth.account.sign_transaction(tx, private_key=key)
    hx = _sign_and_send(w3, signed)
    logger.info("Treasury USDT send {} -> {} tx={}", amount, to_addr, hx)
    return hx


def _send_matic(w3: Web3, from_key: str, to_address: str, matic: Decimal) -> str:
    from_acc = Account.from_key(from_key)
    to_addr = Web3.to_checksum_address(to_address)
    value = int(matic * Decimal(10**18))
    nonce = w3.eth.get_transaction_count(from_acc.address)
    gas_price = int(w3.eth.gas_price * 1.2)
    tx = {
        "from": from_acc.address,
        "to": to_addr,
        "value": value,
        "nonce": nonce,
        "gas": 21_000,
        "gasPrice": gas_price,
        "chainId": 137,
    }
    signed = w3.eth.account.sign_transaction(tx, private_key=from_key)
    return _sign_and_send(w3, signed)


def sweep_deposit_to_treasury(
    installment_id: int,
    user_telegram_id: int = 0,
    min_amount: Decimal | None = None,
) -> dict[str, Any]:
    """
    1) Read USDT balance on unique deposit address
    2) If >= min_amount (or any > 0), send a bit of MATIC for gas from treasury
    3) Transfer ALL USDT from deposit → TREASURY_ADDRESS
    Returns {ok, usdt, deposit, treasury, gas_tx?, sweep_tx?}
    """
    w3 = _w3()
    dep = deposit_account_for(installment_id, user_telegram_id)
    dep_addr = Web3.to_checksum_address(dep.address)
    treasury = treasury_address()
    contract = _usdt(w3)

    units = int(contract.functions.balanceOf(dep_addr).call())
    usdt = units_to_usdt(units)
    if units <= 0:
        return {"ok": False, "reason": "no_usdt", "usdt": usdt, "deposit": dep_addr}

    if min_amount is not None and usdt + Decimal("0.000001") < Decimal(str(min_amount)):
        return {
            "ok": False,
            "reason": "below_min",
            "usdt": usdt,
            "need": str(min_amount),
            "deposit": dep_addr,
        }

    result: dict[str, Any] = {
        "ok": True,
        "usdt": usdt,
        "deposit": dep_addr,
        "treasury": treasury,
    }

    # Ensure deposit has gas
    matic_bal = w3.eth.get_balance(dep_addr)
    need_gas_wei = 10**15  # 0.001 MATIC
    if matic_bal < need_gas_wei:
        try:
            gas_tx = _send_matic(w3, _treasury_key(), dep_addr, Decimal("0.002"))
            result["gas_tx"] = gas_tx
            # brief wait for inclusion is ideal; caller may retry
            for _ in range(15):
                asyncio.get_event_loop().run_until_complete(asyncio.sleep(0))  # noqa: no-op in sync path
                import time

                time.sleep(2)
                if w3.eth.get_balance(dep_addr) >= need_gas_wei:
                    break
        except Exception as e:
            logger.error("gas top-up failed: {}", e)
            raise PolygonError(f"Cannot fund gas for deposit address: {e}") from e

    nonce = w3.eth.get_transaction_count(dep_addr)
    gas_price = int(w3.eth.gas_price * 1.25)
    tx = contract.functions.transfer(treasury, units).build_transaction(
        {
            "from": dep_addr,
            "nonce": nonce,
            "gas": 100_000,
            "gasPrice": gas_price,
            "chainId": 137,
        }
    )
    signed = w3.eth.account.sign_transaction(tx, private_key=dep.key)
    sweep_tx = _sign_and_send(w3, signed)
    result["sweep_tx"] = sweep_tx
    logger.info(
        "Swept {} USDT from {} -> treasury {} tx={}",
        usdt,
        dep_addr,
        treasury,
        sweep_tx,
    )
    return result


async def async_sweep_deposit_to_treasury(
    installment_id: int,
    user_telegram_id: int = 0,
    min_amount: Decimal | None = None,
) -> dict[str, Any]:
    return await asyncio.to_thread(
        sweep_deposit_to_treasury, installment_id, user_telegram_id, min_amount
    )


async def async_send_usdt_from_treasury(to_address: str, amount: Decimal) -> str:
    return await asyncio.to_thread(send_usdt_from_treasury, to_address, amount)


async def async_get_usdt_balance(address: str) -> Decimal:
    return await asyncio.to_thread(get_usdt_balance, address)


def payment_instructions(installment_id: int, user_telegram_id: int, amount: Decimal) -> str:
    w = get_deposit_wallet(installment_id, user_telegram_id)
    return (
        f"💳 <b>Polygon USDT repayment</b>\n\n"
        f"Network: <b>Polygon PoS</b> (chain 137)\n"
        f"Token: <b>USDT</b>\n"
        f"Amount: <b>{amount} USDT</b>\n\n"
        f"🎯 <b>Your dedicated deposit address</b> (only for this installment):\n"
        f"<code>{w.address}</code>\n\n"
        f"Send exactly the amount above. After payment, tap "
        f"<b>I paid — Verify & Sweep</b>.\n"
        f"Funds are automatically forwarded to the main treasury.\n\n"
        f"⚠️ Wrong network / wrong token = loss of funds."
    )
