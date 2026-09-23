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
