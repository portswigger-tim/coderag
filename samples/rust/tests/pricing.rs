//! Tests for the pricing rules.

use bookstore::models::{Book, Cart, CartLine, Tier};
use bookstore::money::Money;
use bookstore::pricing::{validate, PricingService};

fn sample_cart(quantity: i64, tier: Tier) -> Cart {
    let book = Book {
        isbn: "978-0".to_string(),
        title: "A Book".to_string(),
        unit_price: Money::new(1000),
    };
    Cart {
        customer_id: "c1".to_string(),
        tier,
        lines: vec![CartLine { book, quantity }],
    }
}

#[test]
fn base_price_multiplies_by_quantity() {
    let service = PricingService;
    assert_eq!(service.base_price(&sample_cart(3, Tier::Bronze)).pence, 3000);
}

#[test]
fn bulk_discount_covers_every_tier() {
    let service = PricingService;
    for tier in [Tier::Bronze, Tier::Silver, Tier::Gold] {
        let priced = service.apply_bulk_discount(&sample_cart(10, tier), tier).unwrap();
        assert!(priced.pence > 0);
    }
}

#[test]
fn validate_rejects_empty_cart() {
    let cart = Cart { customer_id: "c1".to_string(), tier: Tier::Bronze, lines: vec![] };
    assert!(validate(&cart).is_err());
}
