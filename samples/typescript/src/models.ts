/*
 * Copyright 2026 The coderag sample authors.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

// Domain entities shared across services and repositories.

import { Money } from "./money";

export enum Tier {
  Bronze = "bronze",
  Silver = "silver",
  Gold = "gold",
}

export interface Book {
  isbn: string;
  title: string;
  unitPrice: Money;
}

export interface CartLine {
  book: Book;
  quantity: number;
}

export interface Cart {
  customerId: string;
  tier: Tier;
  lines: CartLine[];
}

export interface Order {
  orderId: string;
  customerId: string;
  total: Money;
  status: string;
}

export function totalQuantity(cart: Cart): number {
  return cart.lines.reduce((sum, line) => sum + line.quantity, 0);
}
