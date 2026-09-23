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

// OrderService coordinates pricing, persistence and notification.
type OrderService struct {
	Pricing PricingService
	Repo    *OrderRepository
}

// NewOrderService wires an order service.
func NewOrderService(repo *OrderRepository) *OrderService {
	return &OrderService{Pricing: PricingService{}, Repo: repo}
}

// Quote prices a cart without committing to an order.
func (s *OrderService) Quote(cart Cart) (Money, error) {
	return s.Pricing.ApplyBulkDiscount(cart, cart.Tier)
}

// PlaceOrder prices the cart, persists the order and notifies the customer.
func (s *OrderService) PlaceOrder(cart Cart, email string) (*Order, error) {
	total, err := s.Pricing.ApplyBulkDiscount(cart, cart.Tier)
	if err != nil {
		return nil, err
	}
	order := s.Repo.Save(cart.CustomerID, total)
	SendConfirmation(order, email)
	return order, nil
}

// Settle marks an order paid.
func (s *OrderService) Settle(orderID string) *Order {
	return s.Repo.MarkPaid(orderID)
}
