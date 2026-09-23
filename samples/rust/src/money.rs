// Copyright 2026 The coderag sample authors.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

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
