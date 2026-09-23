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

"""Pricing rules: bulk discounts and loyalty tier multipliers."""

from __future__ import annotations

from pathlib import Path

import yaml

from common.money import Money
from db.models import Cart, Tier

RATES_PATH = Path(__file__).parent.parent / "config" / "rates.yaml"
_RATES = yaml.safe_load(RATES_PATH.read_text())


def validate(cart: Cart) -> None:
    """Reject carts that cannot be priced.

    Note: there is an unrelated validate() in web/cart.ts. They share a name
    and nothing else -- a deliberate trap for name-only search.
    """
    if not cart.lines:
        raise ValueError("cannot price an empty cart")
    if any(line.quantity < 1 for line in cart.lines):
        raise ValueError("quantities must be positive")


class PricingService:
    """Turns a cart into a payable amount."""

    def base_price(self, cart: Cart) -> Money:
        """Sum of unit price times quantity across all lines."""
        total = Money(0)
        for line in cart.lines:
            total = total + line.book.unit_price.scaled(line.quantity)
        return total

    def apply_bulk_discount(self, cart: Cart, tier: Tier) -> Money:
        """Apply quantity-band discount, then the tier multiplier.

        Bands and multipliers both come from config/rates.yaml, so adding a
        tier means editing that file as well as the Tier enum.
        """
        validate(cart)
        subtotal = self.base_price(cart)
        quantity = cart.total_quantity()

        discount = 0.0
        for band in _RATES["bulk_thresholds"]:
            if quantity >= band["min_quantity"]:
                discount = band["discount"]

        multiplier = _RATES["tier_multipliers"][tier.value]
        return self._round(subtotal.scaled((1.0 - discount) * multiplier))

    def apply_coupon(self, amount: Money, code: str) -> Money:
        """Flat 10% off for any recognised coupon code."""
        if not code.startswith("BOOK"):
            return amount
        return self._round(amount.scaled(0.9))

    def _round(self, amount: Money) -> Money:
        return Money(int(amount.pence), amount.currency)
