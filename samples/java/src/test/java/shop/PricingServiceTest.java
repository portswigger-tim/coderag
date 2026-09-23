package shop;

/** Tests for the pricing rules. Plain asserts, so no test framework is needed. */
public class PricingServiceTest {

    private static Cart sampleCart(int quantity, Tier tier) {
        return new Cart("c1", tier).addLine(new CartLine("978-0", new Money(1000), quantity));
    }

    public static void testBasePrice() {
        PricingService service = new PricingService();
        assertTrue(service.basePrice(sampleCart(3, Tier.BRONZE)).getPence() == 3000, "base price");
    }

    public static void testApplyBulkDiscountCoversEveryTier() {
        PricingService service = new PricingService();
        for (Tier tier : Tier.values()) {
            Money priced = service.applyBulkDiscount(sampleCart(10, tier), tier);
            assertTrue(priced.getPence() > 0, "tier " + tier + " priced");
        }
    }

    public static void testValidateRejectsEmptyCart() {
        try {
            new PricingService().validate(new Cart("c1", Tier.BRONZE));
            assertTrue(false, "expected an exception");
        } catch (IllegalArgumentException expected) {
            assertTrue(true, "empty cart rejected");
        }
    }

    private static void assertTrue(boolean condition, String what) {
        if (!condition) {
            throw new AssertionError("failed: " + what);
        }
        System.out.println("ok - " + what);
    }

    public static void main(String[] args) {
        testBasePrice();
        testApplyBulkDiscountCoversEveryTier();
        testValidateRejectsEmptyCart();
    }
}
