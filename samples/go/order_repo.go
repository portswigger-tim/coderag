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
