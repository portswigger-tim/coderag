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
