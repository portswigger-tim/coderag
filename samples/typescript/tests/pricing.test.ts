/*
 * Copyright 2026 The coderag sample authors.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

// Tests for the pricing rules.

import { Money } from "../src/money";
import { Cart, Tier } from "../src/models";
import { PricingService, validate } from "../src/pricing";

function makeCart(quantity: number, tier: Tier = Tier.Bronze): Cart {
  const book = { isbn: "978-0", title: "A Book", unitPrice: new Money(1000) };
  return { customerId: "c1", tier, lines: [{ book, quantity }] };
}

test("base price multiplies by quantity", () => {
  expect(new PricingService().basePrice(makeCart(3)).pence).toBe(3000);
});

test("bulk discount covers every tier", () => {
  const service = new PricingService();
  for (const tier of Object.values(Tier)) {
    expect(service.applyBulkDiscount(makeCart(10), tier).pence).toBeGreaterThan(0);
  }
});

test("validate rejects an empty cart", () => {
  expect(() => validate({ customerId: "c1", tier: Tier.Bronze, lines: [] })).toThrow();
});
