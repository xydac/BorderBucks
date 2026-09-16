"""Shared validation and auditable fact representation."""

from datetime import date
from decimal import Decimal
import re


class TaxInputError(ValueError):
    """Invalid, ambiguous, or unsupported input; no worksheet may be issued."""


def require(condition, message):
    if not condition:
        raise TaxInputError(message)


def fields(value, required, optional=(), label="input"):
    require(isinstance(value, dict), f"{label} must be an object")
    require(not (set(value) - set(required) - set(optional)),
            f"{label}: unknown fields {sorted(set(value) - set(required) - set(optional))}")
    require(not (set(required) - set(value)),
            f"{label}: missing fields {sorted(set(required) - set(value))}")


def text(value, label="text"):
    require(isinstance(value, str) and bool(value.strip()) and len(value) <= 500,
            f"{label} must be nonempty text (maximum 500 characters)")
    require(not any(ord(c) < 32 for c in value), f"{label} must not contain control characters")
    return value


def number(value, label="amount", *, nonnegative=True, positive=False):
    require(isinstance(value, str) and re.fullmatch(r"-?[0-9]{1,18}(?:\.[0-9]{1,12})?", value) is not None,
            f"{label} must be a decimal string, at most 18 integer and 12 fractional digits")
    result = Decimal(value)
    require(not nonnegative or result >= 0, f"{label} must be nonnegative")
    require(not positive or result > 0, f"{label} must be positive")
    return result


def day(value, label="date"):
    require(isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is not None,
            f"{label} must be YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise TaxInputError(f"{label} is not a valid calendar date") from exc


def decimal_text(value):
    result = format(value, "f")
    return result.rstrip("0").rstrip(".") if "." in result else result


def source_ids(record):
    ids = record.get("source_ids")
    require(isinstance(ids, list) and bool(ids), "source_ids must be a nonempty list")
    for value in ids:
        text(value, "source ID")
    require(len(ids) == len(set(ids)), "duplicate source IDs")
    return sorted(ids)


def fact(id, amount, formula, inputs, sources, rule, unit="USD"):
    """Retain unrounded decimal outputs; filing rounding belongs downstream."""
    return {
        "id": id, "value": decimal_text(amount), "unit": unit,
        "formula": formula,
        "inputs": {key: decimal_text(value) if isinstance(value, Decimal) else value
                   for key, value in inputs.items()},
        "source_ids": sorted(set(sources)), "rule_ids": [rule],
    }
