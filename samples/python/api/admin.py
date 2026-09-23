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

"""Internal admin endpoints. Not exposed to customers."""

from __future__ import annotations

from db.models import Cart
from notifications.emailer import send_price_change_notice
from repositories.order_repo import OrderRepository
from services.pricing import PricingService

_pricing = PricingService()
_repo = OrderRepository()


def recalculate(cart: Cart, email: str) -> dict:
    """Re-price an existing cart after a rate change and tell the customer."""
    total = _pricing.apply_bulk_discount(cart, cart.tier)
    send_price_change_notice(email, f"New total is {total.as_decimal():.2f}")
    return {"total": total.as_decimal()}


def force_settle(order_id: str) -> dict:
    """Mark an order paid without a payment, for support use."""
    order = _repo.mark_paid(order_id)
    return {"order_id": order.order_id, "status": order.status}
