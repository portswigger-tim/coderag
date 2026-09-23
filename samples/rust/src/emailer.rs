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

//! Outbound customer email.

use crate::models::Order;

/// The from-address on outbound mail.
pub const SENDER: &str = "orders@bookstore.example";

/// Emails an order confirmation.
pub fn send_confirmation(order: &Order, address: &str) -> bool {
    let body = format!(
        "Order {} confirmed. Total {:.2}.",
        order.order_id,
        order.total.as_decimal()
    );
    deliver(address, "Your order is confirmed", &body)
}

/// Tells a customer their price moved.
pub fn send_price_change_notice(address: &str, reason: &str) -> bool {
    deliver(address, "A price on your account changed", reason)
}

fn deliver(address: &str, subject: &str, body: &str) -> bool {
    if !address.contains('@') {
        return false;
    }
    println!("[email] {} -> {}: {}\n{}", SENDER, address, subject, body);
    true
}
