"""Polymarket CLOB trader — places real bets using py-clob-client."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

_CLOB_HOST = "https://clob.polymarket.com"
_POLYGON_CHAIN_ID = 137
_MIN_ORDER_USDC = 1.0   # Polymarket minimum order size
_PRICE_BUFFER = 0.02    # Buy slightly above market to ensure fill (taker)


@dataclass
class BetResult:
    """Result of a placed bet."""

    success: bool
    order_id: Optional[str]
    token_id: str
    price: float
    shares: float
    usdc_spent: float
    raw_response: Optional[dict] = None
    error: Optional[str] = None


class PolymarketTrader:
    """Places orders on Polymarket via the CLOB API.

    Requires py-clob-client:
        pip install py-clob-client

    Args:
        private_key: Hex private key of your Polygon EOA wallet (with 0x prefix).
    """

    def __init__(self, private_key: str) -> None:
        self._private_key = private_key
        self._client = self._init_client()

    # ── Public API ────────────────────────────────────────────────────────────

    def get_usdc_balance(self) -> float:
        """Return available USDC balance on Polymarket (in dollars).

        Falls back to 0.0 on failure.
        """
        try:
            from py_clob_client.clob_types import AssetType, BalanceAllowanceParams
            resp = self._client.get_balance_allowance(
                params=BalanceAllowanceParams(
                    asset_type=AssetType.USDC,
                    signature_type=0,
                )
            )
            raw = resp.get("balance", "0")
            # Balance is in micro-USDC (6 decimals)
            return float(raw) / 1_000_000
        except Exception as exc:
            logger.warning("Could not fetch Polymarket balance: %s", exc)
            return 0.0

    def place_bet(self, token_id: str, market_price: float, usdc_amount: float) -> BetResult:
        """Buy *usdc_amount* USDC worth of the given token.

        Args:
            token_id:     CLOB token ID (UP or DOWN token).
            market_price: Current market price for the token (0–1).
            usdc_amount:  Amount in USDC to spend.

        Returns:
            BetResult with success flag and order details.
        """
        if usdc_amount < _MIN_ORDER_USDC:
            msg = f"Stake ${usdc_amount:.2f} below minimum ${_MIN_ORDER_USDC}"
            logger.warning(msg)
            return BetResult(
                success=False, order_id=None, token_id=token_id,
                price=market_price, shares=0.0, usdc_spent=0.0, error=msg,
            )

        # Use a limit price slightly above market to act as a taker order
        limit_price = round(min(0.99, market_price + _PRICE_BUFFER), 4)
        shares = round(usdc_amount / limit_price, 2)

        logger.info(
            "Placing Polymarket order | token=%s... | price=%.4f | shares=%.2f | usdc=%.2f",
            token_id[:12],
            limit_price,
            shares,
            usdc_amount,
        )

        try:
            from py_clob_client.clob_types import OrderArgs
            from py_clob_client.order_builder.constants import BUY

            order_args = OrderArgs(
                token_id=token_id,
                price=limit_price,
                size=shares,
                side=BUY,
            )
            resp = self._client.create_and_post_order(order_args)

            order_id = None
            if isinstance(resp, dict):
                order_id = resp.get("orderID") or resp.get("id")

            logger.info(
                "Order placed successfully | id=%s | usdc=%.2f",
                order_id, usdc_amount,
            )
            return BetResult(
                success=True,
                order_id=order_id,
                token_id=token_id,
                price=limit_price,
                shares=shares,
                usdc_spent=usdc_amount,
                raw_response=resp if isinstance(resp, dict) else None,
            )

        except Exception as exc:
            logger.error("Order placement failed: %s", exc)
            return BetResult(
                success=False, order_id=None, token_id=token_id,
                price=limit_price, shares=shares, usdc_spent=0.0,
                error=str(exc),
            )

    def cancel_all_orders(self) -> None:
        """Cancel all open orders (safety measure)."""
        try:
            self._client.cancel_all()
            logger.info("All open Polymarket orders cancelled.")
        except Exception as exc:
            logger.warning("Failed to cancel orders: %s", exc)

    # ── Private ───────────────────────────────────────────────────────────────

    def _init_client(self):
        """Initialise and authenticate the CLOB client."""
        try:
            from py_clob_client.client import ClobClient

            client = ClobClient(
                host=_CLOB_HOST,
                key=self._private_key,
                chain_id=_POLYGON_CHAIN_ID,
                signature_type=0,  # EOA wallet
            )
            creds = client.create_or_derive_api_creds()
            client.set_api_creds(creds)
            logger.info("Polymarket CLOB client initialised successfully.")
            return client

        except ImportError:
            raise RuntimeError(
                "py-clob-client is not installed. "
                "Run: pip install py-clob-client"
            )
        except Exception as exc:
            raise RuntimeError(f"Failed to initialise Polymarket client: {exc}") from exc
