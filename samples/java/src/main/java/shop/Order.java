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

/** A placed order. */
public class Order {
    private final String orderId;
    private final String customerId;
    private final Money total;
    private String status = "pending";

    public Order(String orderId, String customerId, Money total) {
        this.orderId = orderId;
        this.customerId = customerId;
        this.total = total;
    }

    public String getOrderId() {
        return orderId;
    }

    public String getCustomerId() {
        return customerId;
    }

    public Money getTotal() {
        return total;
    }

    public String getStatus() {
        return status;
    }

    public void markPaid() {
        this.status = "paid";
    }
}
