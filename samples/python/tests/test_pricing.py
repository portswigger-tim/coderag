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

"""Tests for the pricing rules."""

from __future__ import annotations

import pytest

from common.money import Money
from db.models import Book, Cart, CartLine, Tier
from services.pricing import PricingService, validate


def _cart(quantity: int, tier: Tier = Tier.BRONZE) -> Cart:
    book = Book(isbn="978-0", title="A Book", unit_price=Money(1000))
    return Cart(customer_id="c1", tier=tier, lines=[CartLine(book=book, quantity=quantity)])


def test_base_price_multiplies_by_quantity():
    service = PricingService()
    assert service.base_price(_cart(3)).pence == 3000


def test_bulk_discount_tiers():
    """Every Tier member must have a multiplier in config/rates.yaml."""
    service = PricingService()
    for tier in Tier:
        result = service.apply_bulk_discount(_cart(10), tier)
        assert result.pence > 0


def test_bulk_discount_applies_band():
    service = PricingService()
    cheap = service.apply_bulk_discount(_cart(25), Tier.BRONZE)
    dear = service.apply_bulk_discount(_cart(1), Tier.BRONZE)
    assert cheap.pence / 25 < dear.pence


def test_validate_rejects_empty_cart():
    with pytest.raises(ValueError):
        validate(Cart(customer_id="c1", tier=Tier.BRONZE, lines=[]))


def test_apply_coupon_ignores_unknown_code():
    service = PricingService()
    assert service.apply_coupon(Money(1000), "NOPE").pence == 1000
