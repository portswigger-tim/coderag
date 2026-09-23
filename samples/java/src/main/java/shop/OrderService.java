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

package shop;

/** Coordinates pricing, persistence and notification. */
public class OrderService {
    private final PricingService pricing;
    private final OrderRepository repo;

    public OrderService(PricingService pricing, OrderRepository repo) {
        this.pricing = pricing;
        this.repo = repo;
    }

    /** Prices a cart without committing to an order. */
    public Money quote(Cart cart) {
        return pricing.applyBulkDiscount(cart, cart.getTier());
    }

    /** Prices the cart, persists the order and notifies the customer. */
    public Order placeOrder(Cart cart, String email) {
        Money total = pricing.applyBulkDiscount(cart, cart.getTier());
        Order order = repo.save(cart.getCustomerId(), total);
        Emailer.sendConfirmation(order, email);
        return order;
    }

    /** Marks an order paid. */
    public Order settle(String orderId) {
        return repo.markPaid(orderId);
    }
}
