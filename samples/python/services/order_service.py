# Copyright 2026 The coderag sample authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Order placement: the path from a cart to a persisted, confirmed order."""

from __future__ import annotations

from common.money import Money
from db.models import Cart, Order
from notifications.emailer import send_confirmation
from repositories.order_repo import OrderRepository
from services.pricing import PricingService


class OrderService:
    """Coordinates pricing, persistence and notification."""

    def __init__(self, pricing: PricingService, repo: OrderRepository) -> None:
        self.pricing = pricing
        self.repo = repo

    def quote(self, cart: Cart) -> Money:
        """Price a cart without committing to an order."""
        return self.pricing.apply_bulk_discount(cart, cart.tier)

    def place_order(self, cart: Cart, email: str) -> Order:
        """Price the cart, persist the order, and email the customer.

        This is the main write path: any change to pricing, persistence or
        notification is observable here.
        """
        total = self.pricing.apply_bulk_discount(cart, cart.tier)
        order = self.repo.save(cart.customer_id, total)
        send_confirmation(order, email)
        return order

    def settle(self, order_id: str) -> Order:
        """Mark an order paid."""
        return self.repo.mark_paid(order_id)
