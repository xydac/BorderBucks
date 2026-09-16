"""Public, deterministic entry points; fail closed before emitting any report."""

from copy import deepcopy
from decimal import Context, DecimalException, ROUND_HALF_EVEN, localcontext
import hashlib
import json

from . import __version__, equity, foreign, pfic, wash
from .common import TaxInputError, fields, require, source_ids, text
from .rules import RULES

MAX_BYTES = 2 * 1024 * 1024
DISCLAIMER = "Educational alpha, not tax advice or filing-ready. Verify with a qualified tax professional."
CALCULATORS = {"equity": equity.calculate, "foreign": foreign.calculate,
               "pfic": pfic.calculate, "wash": wash.calculate}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def loads(raw):
    """Reject duplicate keys and non-JSON constants instead of silently overwriting evidence."""
    require(isinstance(raw, (str, bytes)), "JSON input must be text or bytes")
    require(len(raw.encode("utf-8") if isinstance(raw, str) else raw) <= MAX_BYTES,
            "input exceeds 2 MiB limit")

    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate JSON key")
            result[key] = value
        return result

    def invalid(value):
        raise TaxInputError(f"non-JSON numeric constant: {value}")

    try:
        result = json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)
        pending = [(result, 0)]
        while pending:
            value, depth = pending.pop()
            require(depth <= 30, "document nesting exceeds 30 levels")
            children = value.values() if isinstance(value, dict) else value if isinstance(value, list) else ()
            pending.extend((child, depth + 1) for child in children)
        return result
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise TaxInputError(f"invalid JSON: {exc}") from exc


def calculate(document):
    """Return JSON-safe facts with full source input and a reproducible content digest."""
    require(isinstance(document, dict), "document must be an object")
    try:
        encoded = canonical(document)
        require(len(encoded) <= MAX_BYTES, "input exceeds 2 MiB limit")
        original = loads(encoded)
    except (TypeError, ValueError, RecursionError) as exc:
        raise TaxInputError(f"document must be bounded JSON data: {exc}") from exc
    require(original.get("schema_version") == "1", "schema_version must be '1'")
    require(type(original.get("tax_year")) is int and original["tax_year"] == 2025,
            "only tax_year 2025 is supported")
    kind = original.get("kind")
    require(isinstance(kind, str) and kind in CALCULATORS, "unsupported document kind")
    manifest = original.get("sources")
    require(isinstance(manifest, list) and bool(manifest), "sources must be a nonempty manifest")
    known = set()
    for source in manifest:
        fields(source, ("id", "document", "locator"), label="source")
        for key in source:
            text(source[key], f"source {key}")
        require(source["id"] not in known, "duplicate source manifest ID")
        known.add(source["id"])

    def validate_refs(value, depth=0):
        require(depth <= 30, "document nesting exceeds 30 levels")
        if isinstance(value, dict):
            if "source_ids" in value:
                require(set(source_ids(value)) <= known, "unresolved source reference")
            for child in value.values():
                validate_refs(child, depth + 1)
        elif isinstance(value, list):
            for child in value:
                validate_refs(child, depth + 1)

    validate_refs(original)
    try:
        # A new Context isolates precision, rounding, exponent limits AND traps.
        with localcontext(Context(prec=60, rounding=ROUND_HALF_EVEN)):
            result = CALCULATORS[kind](deepcopy(original))
    except DecimalException as exc:
        raise TaxInputError("decimal arithmetic outside supported bounds") from exc
    seen, used_rules = set(), set()
    for item in result["facts"]:
        require(item["id"] not in seen, "duplicate output fact ID")
        seen.add(item["id"])
        require(bool(item["source_ids"]) and set(item["source_ids"]) <= known,
                "output fact has unresolved provenance")
        require(bool(item["rule_ids"]) and set(item["rule_ids"]) <= RULES.keys(),
                "output fact has unresolved rule")
        used_rules.update(item["rule_ids"])
    return {
        "schema_version": "1", "engine_version": __version__, "tax_year": 2025,
        "kind": kind, "status": "needs_professional_review", "disclaimer": DISCLAIMER,
        "input_sha256": hashlib.sha256(encoded.encode("ascii")).hexdigest(),
        "inputs": original,
        "rules": {key: deepcopy(RULES[key]) for key in sorted(used_rules)},
        **result,
    }


def explain(document, fact_id):
    report = calculate(document)
    text(fact_id, "fact_id")
    for item in report["facts"]:
        if item["id"] == fact_id:
            return {"disclaimer": DISCLAIMER, "input_sha256": report["input_sha256"],
                    "fact": item, "sources": [s for s in report["inputs"]["sources"]
                                               if s["id"] in item["source_ids"]],
                    "rules": {key: report["rules"][key] for key in item["rule_ids"]},
                    "warnings": report["warnings"]}
    raise TaxInputError(f"unknown fact_id: {fact_id}")


def scenario(document, sale_id, proceeds, date=None):
    baseline = calculate(document)
    require(document["kind"] == "equity", "scenarios support existing equity sales only")
    modified = deepcopy(document)
    for sale in modified["sales"]:
        if sale["sale_id"] == sale_id:
            source_id = "scenario-assumption"
            while any(source["id"] == source_id for source in modified["sources"]):
                source_id += "-new"
            modified["sources"].append({"id": source_id, "document": "User-supplied hypothetical",
                                        "locator": "Scenario proceeds/date override; not a statement transaction"})
            sale["source_ids"].append(source_id)
            sale["proceeds"] = proceeds
            if date is not None:
                sale["date"] = date
            result = calculate(modified)
            result["scenario"] = {"baseline_input_sha256": baseline["input_sha256"], "sale_id": sale_id,
                                  "hypothetical": True}
            result["warnings"].append("Hypothetical replacement of an existing sale; not a new trade or tax recommendation.")
            return result
    raise TaxInputError(f"unknown sale_id: {sale_id}")
