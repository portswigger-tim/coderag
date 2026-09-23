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
