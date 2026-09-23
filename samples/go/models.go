package bookstore

// Tier is a customer loyalty band. Multipliers live in pricing.go.
type Tier string

const (
	TierBronze Tier = "bronze"
	TierSilver Tier = "silver"
	TierGold   Tier = "gold"
)

// Book is a sellable item.
type Book struct {
	ISBN      string
	Title     string
	UnitPrice Money
}

// CartLine is one book and how many of it.
type CartLine struct {
	Book     Book
	Quantity int
}

// Cart is a customer's basket prior to pricing.
type Cart struct {
	CustomerID string
	Tier       Tier
	Lines      []CartLine
}

// TotalQuantity sums the quantities across all lines.
func (c Cart) TotalQuantity() int {
	total := 0
	for _, line := range c.Lines {
		total += line.Quantity
	}
	return total
}

// Order is a placed order.
type Order struct {
	OrderID    string
	CustomerID string
	Total      Money
	Status     string
}
