package bookstore

import "errors"

// Band is a quantity threshold and the discount it unlocks.
type Band struct {
	MinQuantity int
	Discount    float64
}

// BulkThresholds are the quantity discount bands, cheapest band first.
var BulkThresholds = []Band{
	{MinQuantity: 5, Discount: 0.05},
	{MinQuantity: 10, Discount: 0.10},
	{MinQuantity: 25, Discount: 0.18},
}

// TierMultipliers scales the final price by loyalty tier. Adding a Tier
// without adding an entry here silently prices at zero.
var TierMultipliers = map[Tier]float64{
	TierBronze: 1.00,
	TierSilver: 0.97,
	TierGold:   0.94,
}

// ErrEmptyCart is returned when there is nothing to price.
var ErrEmptyCart = errors.New("cannot price an empty cart")

// Validate rejects carts that cannot be priced.
func Validate(cart Cart) error {
	if len(cart.Lines) == 0 {
		return ErrEmptyCart
	}
	for _, line := range cart.Lines {
		if line.Quantity < 1 {
			return errors.New("quantities must be positive")
		}
	}
	return nil
}

// PricingService turns a cart into a payable amount.
type PricingService struct{}

// BasePrice sums unit price times quantity across all lines.
func (p PricingService) BasePrice(cart Cart) Money {
	total := NewMoney(0)
	for _, line := range cart.Lines {
		scaled := line.Book.UnitPrice.Scaled(float64(line.Quantity))
		sum, err := total.Add(scaled)
		if err != nil {
			return total
		}
		total = sum
	}
	return total
}

// ApplyBulkDiscount applies the quantity band, then the tier multiplier.
func (p PricingService) ApplyBulkDiscount(cart Cart, tier Tier) (Money, error) {
	if err := Validate(cart); err != nil {
		return Money{}, err
	}
	subtotal := p.BasePrice(cart)
	quantity := cart.TotalQuantity()

	discount := 0.0
	for _, band := range BulkThresholds {
		if quantity >= band.MinQuantity {
			discount = band.Discount
		}
	}
	return subtotal.Scaled((1.0 - discount) * TierMultipliers[tier]), nil
}

// ApplyCoupon takes 10% off for recognised codes.
func (p PricingService) ApplyCoupon(amount Money, code string) Money {
	if len(code) >= 4 && code[:4] == "BOOK" {
		return amount.Scaled(0.9)
	}
	return amount
}
