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

"""Money as integer minor units. Never use floats for currency."""

from __future__ import annotations

from dataclasses import dataclass

CURRENCY = "GBP"


@dataclass(frozen=True, slots=True)
class Money:
    """An amount in minor units (pence), with a currency code."""

    pence: int
    currency: str = CURRENCY

    def __add__(self, other: "Money") -> "Money":
        if other.currency != self.currency:
            raise ValueError(f"cannot add {other.currency} to {self.currency}")
        return Money(self.pence + other.pence, self.currency)

    def scaled(self, factor: float) -> "Money":
        return Money(round(self.pence * factor), self.currency)

    def as_decimal(self) -> float:
        return self.pence / 100.0
