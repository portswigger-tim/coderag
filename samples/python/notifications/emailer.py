"""Outbound customer email."""

from __future__ import annotations

from db.models import Order

SENDER = "orders@bookstore.example"


def send_confirmation(order: Order, address: str) -> bool:
    """Email an order confirmation. Returns whether it was accepted."""
    body = f"Order {order.order_id} confirmed. Total {order.total.as_decimal():.2f}."
    return _deliver(address, "Your order is confirmed", body)


def send_price_change_notice(address: str, reason: str) -> bool:
    """Tell a customer their price changed after a rate adjustment."""
    return _deliver(address, "A price on your account changed", reason)


def _deliver(address: str, subject: str, body: str) -> bool:
    if "@" not in address:
        return False
    print(f"[email] {SENDER} -> {address}: {subject}\n{body}")
    return True
