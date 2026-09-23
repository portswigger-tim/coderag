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

//! Order placement: cart to persisted, confirmed order.

use crate::emailer::send_confirmation;
use crate::models::{Cart, Order};
use crate::money::Money;
use crate::order_repo::OrderRepository;
use crate::pricing::PricingService;

/// Coordinates pricing, persistence and notification.
pub struct OrderService {
    pub pricing: PricingService,
    pub repo: OrderRepository,
}

impl OrderService {
    /// Wires an order service over a fresh repository.
    pub fn new() -> OrderService {
        OrderService { pricing: PricingService, repo: OrderRepository::new() }
    }

    /// Prices a cart without committing to an order.
    pub fn quote(&self, cart: &Cart) -> Result<Money, String> {
        self.pricing.apply_bulk_discount(cart, cart.tier)
    }

    /// Prices the cart, persists the order and notifies the customer.
    pub fn place_order(&mut self, cart: &Cart, email: &str) -> Result<Order, String> {
        let total = self.pricing.apply_bulk_discount(cart, cart.tier)?;
        let order = self.repo.save(&cart.customer_id, total);
        send_confirmation(&order, email);
        Ok(order)
    }

    /// Marks an order paid.
    pub fn settle(&mut self, order_id: &str) -> Option<Order> {
        self.repo.mark_paid(order_id)
    }
}

impl Default for OrderService {
    fn default() -> Self {
        Self::new()
    }
}
