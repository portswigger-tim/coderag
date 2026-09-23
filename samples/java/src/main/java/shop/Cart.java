package shop;

import java.util.ArrayList;
import java.util.List;

/** A customer's basket, prior to pricing. */
public class Cart {
    private final String customerId;
    private final Tier tier;
    private final List<CartLine> lines = new ArrayList<>();

    public Cart(String customerId, Tier tier) {
        this.customerId = customerId;
        this.tier = tier;
    }

    public String getCustomerId() {
        return customerId;
    }

    public Tier getTier() {
        return tier;
    }

    public List<CartLine> getLines() {
        return lines;
    }

    public Cart addLine(CartLine line) {
        lines.add(line);
        return this;
    }

    /** Sums the quantities across all lines. */
    public int totalQuantity() {
        int total = 0;
        for (CartLine line : lines) {
            total += line.getQuantity();
        }
        return total;
    }
}
