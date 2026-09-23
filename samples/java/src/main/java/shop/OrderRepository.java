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
