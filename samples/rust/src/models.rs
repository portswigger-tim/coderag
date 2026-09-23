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

//! Domain entities shared across services and repositories.

use crate::money::Money;

/// Customer loyalty band. Multipliers live in the pricing module.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Tier {
    Bronze,
    Silver,
    Gold,
}

/// A sellable item.
#[derive(Debug, Clone)]
pub struct Book {
    pub isbn: String,
    pub title: String,
    pub unit_price: Money,
}

/// One book and how many of it.
#[derive(Debug, Clone)]
pub struct CartLine {
    pub book: Book,
    pub quantity: i64,
}

/// A customer's basket prior to pricing.
#[derive(Debug, Clone)]
pub struct Cart {
    pub customer_id: String,
    pub tier: Tier,
    pub lines: Vec<CartLine>,
}

impl Cart {
    /// Sums the quantities across all lines.
    pub fn total_quantity(&self) -> i64 {
        self.lines.iter().map(|line| line.quantity).sum()
    }
}

/// A placed order.
#[derive(Debug, Clone)]
pub struct Order {
    pub order_id: String,
    pub customer_id: String,
    pub total: Money,
    pub status: String,
}
