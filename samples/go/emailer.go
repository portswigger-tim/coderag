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

import (
	"fmt"
	"strings"
)

// Sender is the from-address on outbound mail.
const Sender = "orders@bookstore.example"

// SendConfirmation emails an order confirmation.
func SendConfirmation(order *Order, address string) bool {
	body := fmt.Sprintf("Order %s confirmed. Total %.2f.", order.OrderID, order.Total.AsDecimal())
	return deliver(address, "Your order is confirmed", body)
}

// SendPriceChangeNotice tells a customer their price moved.
func SendPriceChangeNotice(address string, reason string) bool {
	return deliver(address, "A price on your account changed", reason)
}

func deliver(address string, subject string, body string) bool {
	if !strings.Contains(address, "@") {
		return false
	}
	fmt.Printf("[email] %s -> %s: %s\n%s\n", Sender, address, subject, body)
	return true
}
