package shop;

/** A placed order. */
public class Order {
    private final String orderId;
    private final String customerId;
    private final Money total;
    private String status = "pending";

    public Order(String orderId, String customerId, Money total) {
        this.orderId = orderId;
        this.customerId = customerId;
        this.total = total;
    }

    public String getOrderId() {
        return orderId;
    }

    public String getCustomerId() {
        return customerId;
    }

    public Money getTotal() {
        return total;
    }

    public String getStatus() {
        return status;
    }

    public void markPaid() {
        this.status = "paid";
    }
}
