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

import "fmt"

// OrderRepository stores and retrieves orders by id.
type OrderRepository struct {
	orders   map[string]*Order
	sequence int
}

// NewOrderRepository builds an empty in-memory repository.
func NewOrderRepository() *OrderRepository {
	return &OrderRepository{orders: make(map[string]*Order)}
}

// NextID allocates a stable, sortable order id.
func (r *OrderRepository) NextID() string {
	r.sequence++
	return fmt.Sprintf("ORD-%06d", r.sequence)
}

// Save persists a new order and returns it.
func (r *OrderRepository) Save(customerID string, total Money) *Order {
	order := &Order{
		OrderID: r.NextID(), CustomerID: customerID, Total: total, Status: "pending",
	}
	r.orders[order.OrderID] = order
	return order
}

// Get returns an order, or nil when it is unknown.
func (r *OrderRepository) Get(orderID string) *Order {
	return r.orders[orderID]
}

// MarkPaid moves an order to the paid state.
func (r *OrderRepository) MarkPaid(orderID string) *Order {
	order := r.orders[orderID]
	if order != nil {
		order.Status = "paid"
	}
	return order
}
