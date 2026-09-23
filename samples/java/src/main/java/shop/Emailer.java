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

package shop;

/** Outbound customer email. */
public final class Emailer {
    public static final String SENDER = "orders@bookstore.example";

    private Emailer() {
    }

    /** Emails an order confirmation. */
    public static boolean sendConfirmation(Order order, String address) {
        String body = String.format(
            "Order %s confirmed. Total %.2f.", order.getOrderId(), order.getTotal().asDecimal());
        return deliver(address, "Your order is confirmed", body);
    }

    /** Tells a customer their price moved. */
    public static boolean sendPriceChangeNotice(String address, String reason) {
        return deliver(address, "A price on your account changed", reason);
    }

    private static boolean deliver(String address, String subject, String body) {
        if (!address.contains("@")) {
            return false;
        }
        System.out.printf("[email] %s -> %s: %s%n%s%n", SENDER, address, subject, body);
        return true;
    }
}
