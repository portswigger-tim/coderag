package shop;

/** Outbound customer email. */
public final class Emailer {
    public static final String SENDER = "orders@bookstore.example";

    private Emailer() {
    }

    /** Emails an order confirmation. */
    public static boolean sendConfirmation(Order order, String address) {
        String body = String.format(
            "Order %s confirmed. Total %.2f.", order.getOrderId(), order.getTotal().asDecimal());
        return deliver(address, "Your order is confirmed", body);
    }

    /** Tells a customer their price moved. */
    public static boolean sendPriceChangeNotice(String address, String reason) {
        return deliver(address, "A price on your account changed", reason);
    }

    private static boolean deliver(String address, String subject, String body) {
        if (!address.contains("@")) {
            return false;
        }
        System.out.printf("[email] %s -> %s: %s%n%s%n", SENDER, address, subject, body);
        return true;
    }
}
