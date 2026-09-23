//! Persistence for orders. In-memory here.

use std::collections::HashMap;

use crate::models::Order;
use crate::money::Money;

/// Stores and retrieves orders by id.
pub struct OrderRepository {
    orders: HashMap<String, Order>,
    sequence: u32,
}

impl OrderRepository {
    /// Builds an empty repository.
    pub fn new() -> OrderRepository {
        OrderRepository { orders: HashMap::new(), sequence: 0 }
    }

    /// Allocates a stable, sortable order id.
    pub fn next_id(&mut self) -> String {
        self.sequence += 1;
        format!("ORD-{:06}", self.sequence)
    }

    /// Persists a new order and returns a copy.
    pub fn save(&mut self, customer_id: &str, total: Money) -> Order {
        let order = Order {
            order_id: self.next_id(),
            customer_id: customer_id.to_string(),
            total,
            status: "pending".to_string(),
        };
        self.orders.insert(order.order_id.clone(), order.clone());
        order
    }

    /// Returns an order if it is known.
    pub fn get(&self, order_id: &str) -> Option<&Order> {
        self.orders.get(order_id)
    }

    /// Moves an order to the paid state.
    pub fn mark_paid(&mut self, order_id: &str) -> Option<Order> {
        let order = self.orders.get_mut(order_id)?;
        order.status = "paid".to_string();
        Some(order.clone())
    }
}

impl Default for OrderRepository {
    fn default() -> Self {
        Self::new()
    }
}
