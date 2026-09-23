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

"""Customer-facing HTTP endpoints."""

from __future__ import annotations

from api.forms import validate
from db.models import Cart
from repositories.order_repo import OrderRepository
from services.order_service import OrderService
from services.pricing import PricingService

_pricing = PricingService()
_repo = OrderRepository()
_orders = OrderService(_pricing, _repo)


def create_order(cart: Cart, email: str) -> dict:
    """POST /orders -- place an order for the given cart."""
    errors = validate({"customer_id": cart.customer_id, "email": email, "lines": cart.lines})
    if errors:
        return {"errors": errors}
    order = _orders.place_order(cart, email)
    return {"order_id": order.order_id, "total": order.total.as_decimal()}


def get_quote(cart: Cart) -> dict:
    """POST /quote -- price a cart without placing an order."""
    total = _orders.quote(cart)
    return {"total": total.as_decimal()}


def get_order(order_id: str) -> dict:
    """GET /orders/{id}."""
    order = _repo.get(order_id)
    if order is None:
        return {"error": "not found"}
    return {"order_id": order.order_id, "status": order.status}
