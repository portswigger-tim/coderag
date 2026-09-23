"""Persistence for orders. In-memory here; a real one would hit a database."""

from __future__ import annotations

from common.money import Money
from db.models import Order


class OrderRepository:
    """Stores and retrieves orders by id."""

    def __init__(self) -> None:
        self._orders: dict[str, Order] = {}
        self._sequence = 0

    def next_id(self) -> str:
        self._sequence += 1
        return f"ORD-{self._sequence:06d}"

    def save(self, customer_id: str, total: Money) -> Order:
        """Persist a new order and return it."""
        order = Order(order_id=self.next_id(), customer_id=customer_id, total=total)
        self._orders[order.order_id] = order
        return order

    def get(self, order_id: str) -> Order | None:
        return self._orders.get(order_id)

    def mark_paid(self, order_id: str) -> Order:
        order = self._orders[order_id]
        order.status = "paid"
        return order
