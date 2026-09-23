// Browser-side cart. Talks to the order endpoints.

export interface CartLine {
  isbn: string;
  quantity: number;
}

export interface QuoteResponse {
  total: number;
}

// Unrelated to services/pricing.py validate(). Same name, different job:
// this checks form input, that one checks a domain object.
export function validate(lines: CartLine[]): string[] {
  const errors: string[] = [];
  for (const line of lines) {
    if (line.quantity < 1) {
      errors.push(`quantity for ${line.isbn} must be at least 1`);
    }
  }
  return errors;
}

export async function requestQuote(lines: CartLine[]): Promise<QuoteResponse> {
  const response = await fetch("/quote", {
    method: "POST",
    body: JSON.stringify({ lines }),
  });
  return response.json();
}

export async function submitOrder(lines: CartLine[], email: string): Promise<string> {
  const errors = validate(lines);
  if (errors.length > 0) {
    throw new Error(errors.join("; "));
  }
  const response = await fetch("/orders", {
    method: "POST",
    body: JSON.stringify({ lines, email }),
  });
  const body = await response.json();
  return body.order_id;
}
