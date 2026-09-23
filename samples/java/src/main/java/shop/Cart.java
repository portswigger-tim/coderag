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

import java.util.ArrayList;
import java.util.List;

/** A customer's basket, prior to pricing. */
public class Cart {
    private final String customerId;
    private final Tier tier;
    private final List<CartLine> lines = new ArrayList<>();

    public Cart(String customerId, Tier tier) {
        this.customerId = customerId;
        this.tier = tier;
    }

    public String getCustomerId() {
        return customerId;
    }

    public Tier getTier() {
        return tier;
    }

    public List<CartLine> getLines() {
        return lines;
    }

    public Cart addLine(CartLine line) {
        lines.add(line);
        return this;
    }

    /** Sums the quantities across all lines. */
    public int totalQuantity() {
        int total = 0;
        for (CartLine line : lines) {
            total += line.getQuantity();
        }
        return total;
    }
}
