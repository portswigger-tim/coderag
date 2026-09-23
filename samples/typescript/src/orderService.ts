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

// Order placement: cart to persisted, confirmed order.

import { Money } from "./money";
import { Cart, Order } from "./models";
import { PricingService } from "./pricing";
import { OrderRepository } from "./orderRepo";
import { sendConfirmation } from "./emailer";

export class OrderService {
  constructor(
    private readonly pricing: PricingService,
    private readonly repo: OrderRepository,
  ) {}

  quote(cart: Cart): Money {
    return this.pricing.applyBulkDiscount(cart, cart.tier);
  }

  placeOrder(cart: Cart, email: string): Order {
    const total = this.pricing.applyBulkDiscount(cart, cart.tier);
    const order = this.repo.save(cart.customerId, total);
    sendConfirmation(order, email);
    return order;
  }

  settle(orderId: string): Order {
    return this.repo.markPaid(orderId);
  }
}
