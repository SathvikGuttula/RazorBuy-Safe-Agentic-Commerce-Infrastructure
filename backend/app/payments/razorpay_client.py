"""Razorpay API client — real integration with test-mode support.

Uses the official razorpay Python SDK.
All amounts are converted to paise (1 INR = 100 paise) for Razorpay.
Synchronous SDK calls are wrapped in asyncio.to_thread for async FastAPI.
"""

import asyncio
import logging
from typing import Optional

import razorpay
from razorpay.errors import BadRequestError, GatewayError, ServerError

from app.config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class RazorpayClientError(Exception):
    """Custom exception for Razorpay API errors."""
    def __init__(self, message: str, code: Optional[str] = None):
        self.code = code
        super().__init__(message)


class RazorpayClient:
    """
    Wrapper around the official Razorpay SDK.
    Handles order creation, payment fetching, and signature verification.
    """

    def __init__(self):
        self._key_id = settings.razorpay_key_id
        self._key_secret = settings.razorpay_key_secret
        self._configured = bool(self._key_id and self._key_secret
                                and not self._key_id.startswith("your_"))

        if self._configured:
            self._client = razorpay.Client(
                auth=(self._key_id, self._key_secret)
            )
            logger.info("Razorpay client initialized (test mode)")
        else:
            self._client = None
            logger.warning(
                "Razorpay keys not configured. Using mock mode. "
                "Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET in .env"
            )

    @property
    def is_configured(self) -> bool:
        return self._configured

    # ─── Order Operations ────────────────────

    async def create_order(
        self, amount_inr: float, receipt: str, currency: str = "INR"
    ) -> dict:
        """
        Create a Razorpay order.

        Args:
            amount_inr: Amount in INR (e.g., 2499.00)
            receipt: Unique receipt identifier
            currency: Currency code (default INR)

        Returns:
            dict with id, amount, currency, status, etc.
        """
        amount_paise = int(amount_inr * 100)

        if not self._configured:
            return self._mock_create_order(amount_paise, receipt, currency)

        try:
            data = {
                "amount": amount_paise,
                "currency": currency,
                "receipt": receipt,
                "payment_capture": 1,  # auto-capture
            }
            order = await asyncio.to_thread(
                self._client.order.create, data=data
            )
            logger.info(f"Razorpay order created: {order['id']}")
            return order
        except BadRequestError as e:
            raise RazorpayClientError(
                f"Bad request: {e}", code="BAD_REQUEST"
            ) from e
        except (GatewayError, ServerError) as e:
            raise RazorpayClientError(
                f"Razorpay server error: {e}", code="GATEWAY_ERROR"
            ) from e
        except Exception as e:
            raise RazorpayClientError(
                f"Unexpected error: {e}", code="UNKNOWN"
            ) from e

    async def fetch_order(self, razorpay_order_id: str) -> dict:
        """Fetch order details from Razorpay."""
        if not self._configured:
            return self._mock_fetch_order(razorpay_order_id)

        try:
            order = await asyncio.to_thread(
                self._client.order.fetch, razorpay_order_id
            )
            return order
        except Exception as e:
            raise RazorpayClientError(
                f"Failed to fetch order: {e}", code="FETCH_ERROR"
            ) from e

    # ─── Payment Operations ──────────────────

    async def fetch_payment(self, razorpay_payment_id: str) -> dict:
        """Fetch payment details from Razorpay."""
        if not self._configured:
            return self._mock_fetch_payment(razorpay_payment_id)

        try:
            payment = await asyncio.to_thread(
                self._client.payment.fetch, razorpay_payment_id
            )
            return payment
        except Exception as e:
            raise RazorpayClientError(
                f"Failed to fetch payment: {e}", code="FETCH_ERROR"
            ) from e

    # ─── Signature Verification ──────────────

    def verify_payment_signature(
        self,
        razorpay_order_id: str,
        razorpay_payment_id: str,
        razorpay_signature: str,
    ) -> bool:
        """
        Verify Razorpay payment signature using HMAC-SHA256.
        This is the CRITICAL security check. Never skip this.
        """
        if not self._configured:
            # In mock mode, accept any signature that isn't empty
            return bool(razorpay_signature)

        try:
            attributes = {
                "razorpay_order_id": razorpay_order_id,
                "razorpay_payment_id": razorpay_payment_id,
                "razorpay_signature": razorpay_signature,
            }
            self._client.utility.verify_payment_signature(attributes)
            return True
        except Exception as e:
            logger.warning(f"Payment signature verification failed: {e}")
            return False

    # ─── Mock Mode (Development Only) ────────
    # Clearly marked as a development stub.
    # Never used in production. Remove before demo if keys are configured.

    def _mock_create_order(
        self, amount_paise: int, receipt: str, currency: str
    ) -> dict:
        import uuid
        mock_id = f"order_mock_{uuid.uuid4().hex[:14]}"
        logger.warning(f"MOCK: Created order {mock_id}")
        return {
            "id": mock_id,
            "entity": "order",
            "amount": amount_paise,
            "amount_paid": 0,
            "amount_due": amount_paise,
            "currency": currency,
            "receipt": receipt,
            "status": "created",
            "attempts": 0,
        }

    def _mock_fetch_order(self, order_id: str) -> dict:
        return {
            "id": order_id,
            "entity": "order",
            "amount": 249900,
            "status": "paid",
            "attempts": 1,
        }

    def _mock_fetch_payment(self, payment_id: str) -> dict:
        return {
            "id": payment_id,
            "entity": "payment",
            "amount": 249900,
            "currency": "INR",
            "status": "captured",
            "method": "card",
            "order_id": "order_mock_xxx",
        }


# Singleton instance
_razorpay_client: Optional[RazorpayClient] = None


def get_razorpay_client() -> RazorpayClient:
    """Get or create the Razorpay client singleton."""
    global _razorpay_client
    if _razorpay_client is None:
        _razorpay_client = RazorpayClient()
    return _razorpay_client