//! Money as integer minor units. Never use floats for currency.

pub const CURRENCY: &str = "GBP";

/// An amount in minor units with a currency code.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Money {
    pub pence: i64,
}

impl Money {
    /// Builds an amount in the default currency.
    pub fn new(pence: i64) -> Money {
        Money { pence }
    }

    /// Returns the sum of two amounts.
    pub fn add(&self, other: &Money) -> Money {
        Money { pence: self.pence + other.pence }
    }

    /// Multiplies the amount, rounding to the nearest penny.
    pub fn scaled(&self, factor: f64) -> Money {
        Money { pence: (self.pence as f64 * factor).round() as i64 }
    }

    /// Renders the amount in major units.
    pub fn as_decimal(&self) -> f64 {
        self.pence as f64 / 100.0
    }
}
