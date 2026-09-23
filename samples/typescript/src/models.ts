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
