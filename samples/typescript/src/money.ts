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
