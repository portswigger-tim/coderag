// Pricing rules: bulk discounts and loyalty tier multipliers.
// Bands and multipliers live in config/rates.yaml -- adding a tier means
// editing that file as well as the Tier enum.

import { Money } from "./money";
import { Cart, Tier, totalQuantity } from "./models";

interface Band {
  minQuantity: number;
  discount: number;
}

export const BULK_THRESHOLDS: Band[] = [
  { minQuantity: 5, discount: 0.05 },
  { minQuantity: 10, discount: 0.1 },
  { minQuantity: 25, discount: 0.18 },
];

export const TIER_MULTIPLIERS: Record<Tier, number> = {
  [Tier.Bronze]: 1.0,
  [Tier.Silver]: 0.97,
  [Tier.Gold]: 0.94,
};

// Unrelated to web/cart.ts validate(). Same name, different job.
export function validate(cart: Cart): void {
  if (cart.lines.length === 0) {
    throw new Error("cannot price an empty cart");
  }
}

export class PricingService {
  basePrice(cart: Cart): Money {
    let total = new Money(0);
    for (const line of cart.lines) {
      total = total.add(line.book.unitPrice.scaled(line.quantity));
    }
    return total;
  }

  applyBulkDiscount(cart: Cart, tier: Tier): Money {
    validate(cart);
    const subtotal = this.basePrice(cart);
    const quantity = totalQuantity(cart);

    let discount = 0;
    for (const band of BULK_THRESHOLDS) {
      if (quantity >= band.minQuantity) {
        discount = band.discount;
      }
    }
    return subtotal.scaled((1 - discount) * TIER_MULTIPLIERS[tier]);
  }

  applyCoupon(amount: Money, code: string): Money {
    return code.startsWith("BOOK") ? amount.scaled(0.9) : amount;
  }
}
