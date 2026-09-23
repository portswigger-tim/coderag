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

package shop;

import java.util.EnumMap;
import java.util.Map;

/** Turns a cart into a payable amount. */
public class PricingService {

    private static final int[] BAND_QUANTITIES = {5, 10, 25};
    private static final double[] BAND_DISCOUNTS = {0.05, 0.10, 0.18};

    private static final Map<Tier, Double> TIER_MULTIPLIERS = new EnumMap<>(Tier.class);

    static {
        TIER_MULTIPLIERS.put(Tier.BRONZE, 1.00);
        TIER_MULTIPLIERS.put(Tier.SILVER, 0.97);
        TIER_MULTIPLIERS.put(Tier.GOLD, 0.94);
    }

    /** Rejects carts that cannot be priced. */
    public void validate(Cart cart) {
        if (cart.getLines().isEmpty()) {
            throw new IllegalArgumentException("cannot price an empty cart");
        }
    }

    /** Sums unit price times quantity across all lines. */
    public Money basePrice(Cart cart) {
        Money total = new Money(0);
        for (CartLine line : cart.getLines()) {
            total = total.add(line.getUnitPrice().scaled(line.getQuantity()));
        }
        return total;
    }

    /**
     * Applies the quantity band, then the tier multiplier.
     *
     * <p>Adding a Tier without adding a multiplier here prices at zero.
     */
    public Money applyBulkDiscount(Cart cart, Tier tier) {
        validate(cart);
        Money subtotal = basePrice(cart);
        int quantity = cart.totalQuantity();

        double discount = 0.0;
        for (int i = 0; i < BAND_QUANTITIES.length; i++) {
            if (quantity >= BAND_QUANTITIES[i]) {
                discount = BAND_DISCOUNTS[i];
            }
        }
        return subtotal.scaled((1.0 - discount) * TIER_MULTIPLIERS.get(tier));
    }

    /** Takes 10% off for recognised coupon codes. */
    public Money applyCoupon(Money amount, String code) {
        return code.startsWith("BOOK") ? amount.scaled(0.9) : amount;
    }
}
