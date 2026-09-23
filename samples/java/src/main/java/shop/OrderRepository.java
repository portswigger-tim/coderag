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

import java.util.HashMap;
import java.util.Map;

/** Stores and retrieves orders by id. */
public class OrderRepository {
    private final Map<String, Order> orders = new HashMap<>();
    private int sequence = 0;

    /** Allocates a stable, sortable order id. */
    public String nextId() {
        sequence += 1;
        return String.format("ORD-%06d", sequence);
    }

    /** Persists a new order and returns it. */
    public Order save(String customerId, Money total) {
        Order order = new Order(nextId(), customerId, total);
        orders.put(order.getOrderId(), order);
        return order;
    }

    public Order get(String orderId) {
        return orders.get(orderId);
    }

    /** Moves an order to the paid state. */
    public Order markPaid(String orderId) {
        Order order = orders.get(orderId);
        if (order != null) {
            order.markPaid();
        }
        return order;
    }
}
