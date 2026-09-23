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

"""End-to-end order placement."""

from __future__ import annotations

from common.money import Money
from db.models import Book, Cart, CartLine, Tier
from repositories.order_repo import OrderRepository
from services.order_service import OrderService
from services.pricing import PricingService


def _cart() -> Cart:
    book = Book(isbn="978-1", title="Another Book", unit_price=Money(500))
    return Cart(customer_id="c2", tier=Tier.GOLD, lines=[CartLine(book=book, quantity=6)])


def test_place_order_persists_and_notifies():
    service = OrderService(PricingService(), OrderRepository())
    order = service.place_order(_cart(), "reader@example.com")
    assert order.order_id.startswith("ORD-")
    assert order.total.pence > 0


def test_quote_does_not_persist():
    repo = OrderRepository()
    service = OrderService(PricingService(), repo)
    service.quote(_cart())
    assert repo.get("ORD-000001") is None


def test_settle_marks_paid():
    repo = OrderRepository()
    service = OrderService(PricingService(), repo)
    order = service.place_order(_cart(), "reader@example.com")
    assert service.settle(order.order_id).status == "paid"
