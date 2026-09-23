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

// Package bookstore prices and places book orders.
//
// Money is held in integer minor units. Never use floats for currency.
package bookstore

import "fmt"

const Currency = "GBP"

// Money is an amount in minor units with a currency code.
type Money struct {
	Pence    int
	Currency string
}

// NewMoney builds an amount in the default currency.
func NewMoney(pence int) Money {
	return Money{Pence: pence, Currency: Currency}
}

// Add returns the sum, refusing to mix currencies.
func (m Money) Add(other Money) (Money, error) {
	if other.Currency != m.Currency {
		return Money{}, fmt.Errorf("cannot add %s to %s", other.Currency, m.Currency)
	}
	return Money{Pence: m.Pence + other.Pence, Currency: m.Currency}, nil
}

// Scaled multiplies the amount, rounding to the nearest penny.
func (m Money) Scaled(factor float64) Money {
	return Money{Pence: int(float64(m.Pence)*factor + 0.5), Currency: m.Currency}
}

// AsDecimal renders the amount in major units.
func (m Money) AsDecimal() float64 {
	return float64(m.Pence) / 100.0
}
