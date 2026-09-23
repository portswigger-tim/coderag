package bookstore

import "testing"

func sampleCart(quantity int, tier Tier) Cart {
	book := Book{ISBN: "978-0", Title: "A Book", UnitPrice: NewMoney(1000)}
	return Cart{CustomerID: "c1", Tier: tier, Lines: []CartLine{{Book: book, Quantity: quantity}}}
}

func TestBasePrice(t *testing.T) {
	service := PricingService{}
	if got := service.BasePrice(sampleCart(3, TierBronze)); got.Pence != 3000 {
		t.Fatalf("expected 3000, got %d", got.Pence)
	}
}

func TestApplyBulkDiscountCoversEveryTier(t *testing.T) {
	service := PricingService{}
	for _, tier := range []Tier{TierBronze, TierSilver, TierGold} {
		got, err := service.ApplyBulkDiscount(sampleCart(10, tier), tier)
		if err != nil || got.Pence <= 0 {
			t.Fatalf("tier %s priced badly: %v %d", tier, err, got.Pence)
		}
	}
}

func TestValidateRejectsEmptyCart(t *testing.T) {
	if err := Validate(Cart{CustomerID: "c1", Tier: TierBronze}); err == nil {
		t.Fatal("expected an error for an empty cart")
	}
}
