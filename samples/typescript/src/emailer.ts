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

// Outbound customer email.

import { Order } from "./models";

export const SENDER = "orders@bookstore.example";

export function sendConfirmation(order: Order, address: string): boolean {
  const body = `Order ${order.orderId} confirmed. Total ${order.total.asDecimal().toFixed(2)}.`;
  return deliver(address, "Your order is confirmed", body);
}

export function sendPriceChangeNotice(address: string, reason: string): boolean {
  return deliver(address, "A price on your account changed", reason);
}

function deliver(address: string, subject: string, body: string): boolean {
  if (!address.includes("@")) return false;
  console.log(`[email] ${SENDER} -> ${address}: ${subject}\n${body}`);
  return true;
}
