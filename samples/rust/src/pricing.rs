//! Pricing rules: bulk discounts and loyalty tier multipliers.

use crate::models::{Cart, Tier};
use crate::money::Money;

/// A quantity threshold and the discount it unlocks.
pub struct Band {
    pub min_quantity: i64,
    pub discount: f64,
}

/// Quantity discount bands, smallest threshold first.
pub const BULK_THRESHOLDS: [Band; 3] = [
    Band { min_quantity: 5, discount: 0.05 },
    Band { min_quantity: 10, discount: 0.10 },
    Band { min_quantity: 25, discount: 0.18 },
];

/// Scales the final price by loyalty tier. A new Tier needs an arm here.
pub fn tier_multiplier(tier: Tier) -> f64 {
    match tier {
        Tier::Bronze => 1.00,
        Tier::Silver => 0.97,
        Tier::Gold => 0.94,
    }
}

/// Rejects carts that cannot be priced.
pub fn validate(cart: &Cart) -> Result<(), String> {
    if cart.lines.is_empty() {
        return Err("cannot price an empty cart".to_string());
    }
    if cart.lines.iter().any(|line| line.quantity < 1) {
        return Err("quantities must be positive".to_string());
    }
    Ok(())
}

/// Turns a cart into a payable amount.
pub struct PricingService;

impl PricingService {
    /// Sums unit price times quantity across all lines.
    pub fn base_price(&self, cart: &Cart) -> Money {
        let mut total = Money::new(0);
        for line in &cart.lines {
            total = total.add(&line.book.unit_price.scaled(line.quantity as f64));
        }
        total
    }

    /// Applies the quantity band, then the tier multiplier.
    pub fn apply_bulk_discount(&self, cart: &Cart, tier: Tier) -> Result<Money, String> {
        validate(cart)?;
        let subtotal = self.base_price(cart);
        let quantity = cart.total_quantity();

        let mut discount = 0.0;
        for band in BULK_THRESHOLDS.iter() {
            if quantity >= band.min_quantity {
                discount = band.discount;
            }
        }
        Ok(subtotal.scaled((1.0 - discount) * tier_multiplier(tier)))
    }

    /// Takes 10% off for recognised coupon codes.
    pub fn apply_coupon(&self, amount: Money, code: &str) -> Money {
        if code.starts_with("BOOK") { amount.scaled(0.9) } else { amount }
    }
}
