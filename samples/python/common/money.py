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
