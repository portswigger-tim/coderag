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
