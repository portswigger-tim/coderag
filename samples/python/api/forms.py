"""Request payload validation for the HTTP layer.

Deliberately contains a `validate` that has nothing to do with the one in
services/pricing.py. Real repositories are full of same-named functions in
unrelated modules; a name-only search returns both and cannot tell you which
one you meant. The graph can.
"""

from __future__ import annotations

REQUIRED_ORDER_FIELDS = ("customer_id", "email", "lines")


def validate(payload: dict) -> list[str]:
    """Check an inbound JSON payload for missing or malformed fields."""
    errors = []
    for field in REQUIRED_ORDER_FIELDS:
        if field not in payload:
            errors.append(f"missing field: {field}")
    if "email" in payload and "@" not in str(payload["email"]):
        errors.append("email is not an address")
    return errors


def normalise(payload: dict) -> dict:
    """Trim strings and drop unknown keys from an inbound payload."""
    return {
        key: value.strip() if isinstance(value, str) else value
        for key, value in payload.items()
        if key in REQUIRED_ORDER_FIELDS
    }
