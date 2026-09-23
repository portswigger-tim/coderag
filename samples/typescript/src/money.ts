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

// Money as integer minor units. Never use floats for currency.

export const CURRENCY = "GBP";

export class Money {
  constructor(
    public readonly pence: number,
    public readonly currency: string = CURRENCY,
  ) {}

  add(other: Money): Money {
    if (other.currency !== this.currency) {
      throw new Error(`cannot add ${other.currency} to ${this.currency}`);
    }
    return new Money(this.pence + other.pence, this.currency);
  }

  scaled(factor: number): Money {
    return new Money(Math.round(this.pence * factor), this.currency);
  }

  asDecimal(): number {
    return this.pence / 100;
  }
}
