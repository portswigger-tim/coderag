package shop;

/** One book and how many of it. */
public class CartLine {
    private final String isbn;
    private final Money unitPrice;
    private final int quantity;

    public CartLine(String isbn, Money unitPrice, int quantity) {
        this.isbn = isbn;
        this.unitPrice = unitPrice;
        this.quantity = quantity;
    }

    public String getIsbn() {
        return isbn;
    }

    public Money getUnitPrice() {
        return unitPrice;
    }

    public int getQuantity() {
        return quantity;
    }
}
