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
