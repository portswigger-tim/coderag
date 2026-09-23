// Copyright 2026 The coderag sample authors.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

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
