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

// Persistence for orders. In-memory here.

import { Money } from "./money";
import { Order } from "./models";

export class OrderRepository {
  private orders = new Map<string, Order>();
  private sequence = 0;

  nextId(): string {
    this.sequence += 1;
    return `ORD-${String(this.sequence).padStart(6, "0")}`;
  }

  save(customerId: string, total: Money): Order {
    const order: Order = {
      orderId: this.nextId(), customerId, total, status: "pending",
    };
    this.orders.set(order.orderId, order);
    return order;
  }

  get(orderId: string): Order | undefined {
    return this.orders.get(orderId);
  }

  markPaid(orderId: string): Order {
    const order = this.orders.get(orderId);
    if (!order) throw new Error(`unknown order ${orderId}`);
    order.status = "paid";
    return order;
  }
}
