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

"""Domain entities shared across services and repositories."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

from common.money import Money


class Tier(enum.Enum):
    """Customer loyalty tier. Discount rates live in config/rates.yaml."""

    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"


@dataclass(slots=True)
class Book:
    isbn: str
    title: str
    unit_price: Money


@dataclass(slots=True)
class CartLine:
    book: Book
    quantity: int


@dataclass(slots=True)
class Cart:
    """A customer's basket, prior to pricing."""

    customer_id: str
    tier: Tier
    lines: list[CartLine] = field(default_factory=list)

    def total_quantity(self) -> int:
        return sum(line.quantity for line in self.lines)


@dataclass(slots=True)
class Order:
    order_id: str
    customer_id: str
    total: Money
    status: str = "pending"
