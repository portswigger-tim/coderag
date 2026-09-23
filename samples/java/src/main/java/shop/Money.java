package shop;

/** An amount in minor units. Never use floating point for currency. */
public final class Money {
    public static final String CURRENCY = "GBP";

    private final int pence;
    private final String currency;

    public Money(int pence) {
        this(pence, CURRENCY);
    }

    public Money(int pence, String currency) {
        this.pence = pence;
        this.currency = currency;
    }

    public int getPence() {
        return pence;
    }

    public String getCurrency() {
        return currency;
    }

    /** Adds two amounts, refusing to mix currencies. */
    public Money add(Money other) {
        if (!other.currency.equals(this.currency)) {
            throw new IllegalArgumentException("cannot add " + other.currency + " to " + currency);
        }
        return new Money(this.pence + other.pence, this.currency);
    }

    /** Multiplies the amount, rounding to the nearest penny. */
    public Money scaled(double factor) {
        return new Money((int) Math.round(pence * factor), currency);
    }

    public double asDecimal() {
        return pence / 100.0;
    }
}
