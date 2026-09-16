"""Explicit-inventory FBAR and Form 8938 threshold arithmetic for 2025."""

from decimal import Decimal
from fractions import Fraction

from .common import fields, fact, number, require, source_ids, text


def calculate(document):
    """Compare exact USD fractions; the engine supplies the presentation context."""
    fields(document, (
        "schema_version", "tax_year", "kind", "sources", "source_ids",
        "filing_status", "residence", "qualifying_abroad_confirmed",
        "inventory_complete", "no_double_counting_confirmed", "fx_rates", "assets",
        "same_valuation_for_both_regimes_confirmed",
    ), label="foreign")
    require(document["schema_version"] == "1", "schema_version must be '1'")
    require(type(document["tax_year"]) is int and document["tax_year"] == 2025,
            "tax_year must be the integer 2025")
    require(document["kind"] == "foreign", "kind must be foreign")
    require(isinstance(document["sources"], list), "sources must be a list")
    manifest_ids = set()
    for source in document["sources"]:
        fields(source, ("id", "document", "locator"), label="source")
        for key in ("id", "document", "locator"):
            text(source[key], f"source {key}")
        require(source["id"] not in manifest_ids, "duplicate source ID in manifest")
        manifest_ids.add(source["id"])
    assertion_sources = source_ids(document)
    require(document["filing_status"] in ("single", "married_separate", "married_joint"),
            "unsupported filing_status")
    require(document["residence"] in ("us", "abroad"), "residence must be us or abroad")
    require(type(document["qualifying_abroad_confirmed"]) is bool,
            "qualifying_abroad_confirmed must be a boolean")
    require(document["qualifying_abroad_confirmed"] == (document["residence"] == "abroad"),
            "abroad requires confirmation of the qualifying abroad test; us requires false")
    require(document["inventory_complete"] is True,
            "inventory_complete must be true; incomplete inventories are unsupported")
    require(document["no_double_counting_confirmed"] is True,
            "no_double_counting_confirmed must be true")
    require(document["same_valuation_for_both_regimes_confirmed"] is True,
            "same_valuation_for_both_regimes_confirmed must be true; spouse-joint MFS ownership "
            "and other regime-specific valuations are unsupported")

    require(isinstance(document["fx_rates"], list), "fx_rates must be a list")
    rates = {}
    for rate in document["fx_rates"]:
        fields(rate, ("currency", "date", "local_per_usd", "source_ids"), label="FX rate")
        currency = rate["currency"]
        require(currency in ("USD", "INR"), "only USD and INR are supported")
        require(currency not in rates, "duplicate FX currency")
        require(rate["date"] == "2025-12-31", "FX date must be 2025-12-31")
        value = number(rate["local_per_usd"], "local_per_usd", positive=True)
        require(currency != "USD" or value == 1, "USD local_per_usd must be 1")
        rates[currency] = (value, source_ids(rate))

    require(isinstance(document["assets"], list), "assets must be a list")
    assets = {}
    for asset in document["assets"]:
        fields(asset, (
            "id", "description", "asset_type", "currency", "maximum_local",
            "yearend_local", "include_fbar", "include_form8938", "source_ids",
        ), ("included_in_account_id",), label="asset")
        asset_id = text(asset["id"], "asset ID")
        text(asset["description"], "asset description")
        require(asset_id not in assets, "duplicate asset ID")
        require(asset["asset_type"] in ("account", "asset"), "asset_type must be account or asset")
        require(asset["currency"] in ("USD", "INR"), "only USD and INR are supported")
        require(asset["currency"] in rates, "every asset currency needs an explicit yearend FX rate")
        for key in ("include_fbar", "include_form8938"):
            require(type(asset[key]) is bool, f"{key} must be a boolean")
        require(not asset["include_fbar"] or asset["asset_type"] == "account",
                "FBAR inclusion requires an explicitly classified account")
        maximum = number(asset["maximum_local"], "maximum_local")
        yearend = number(asset["yearend_local"], "yearend_local")
        require(yearend <= maximum, "yearend_local must not exceed maximum_local")
        asset_sources = source_ids(asset)
        if "included_in_account_id" in asset:
            text(asset["included_in_account_id"], "included_in_account_id")
            require(asset["asset_type"] == "asset", "only assets can be included in an account")
            require(not asset["include_fbar"] and not asset["include_form8938"],
                    "underlying assets already valued in an account must be excluded from both totals")
        assets[asset_id] = (asset, maximum, yearend, asset_sources)
    for asset, _, _, _ in assets.values():
        if "included_in_account_id" in asset:
            parent = asset["included_in_account_id"]
            require(parent in assets and assets[parent][0]["asset_type"] == "account",
                    "included_in_account_id must reference an account in this inventory")

    facts = []
    totals = {name: {"maximum": Fraction(0), "yearend": Fraction(0),
                     "sources": list(assertion_sources), "maximum_inputs": {}, "yearend_inputs": {}}
              for name in ("fbar", "form8938")}
    for asset_id, (asset, maximum, yearend, asset_sources) in assets.items():
        rate, rate_sources = rates[asset["currency"]]
        provenance = asset_sources + rate_sources
        for period, local_value in (("maximum", maximum), ("yearend", yearend)):
            # Never aggregate finite-precision presentations of recurring FX quotients.
            converted = Fraction(local_value) / Fraction(rate)
            fact_id = f"foreign.asset.{asset_id}.{period}_usd"
            facts.append(fact(fact_id, Decimal(converted.numerator) / Decimal(converted.denominator),
                              "local_value / local_per_usd",
                              {"local_value": local_value, "local_per_usd": rate},
                              provenance, "foreign.fx.2025"))
            for name in totals:
                if asset[f"include_{name}"]:
                    totals[name][period] += converted
                    totals[name][f"{period}_inputs"][fact_id] = f"{converted.numerator}/{converted.denominator}"
        for name in totals:
            if asset[f"include_{name}"]:
                totals[name]["sources"].extend(provenance)

    joint = document["filing_status"] == "married_joint"
    if document["residence"] == "abroad":
        fatca_yearend, fatca_maximum = (400000, 600000) if joint else (200000, 300000)
    else:
        fatca_yearend, fatca_maximum = (100000, 150000) if joint else (50000, 75000)
    screening = {}
    for name, yearend_limit, maximum_limit, rule in (
        ("fbar", 10000, 10000, "foreign.fbar.2025"),
        ("form8938", fatca_yearend, fatca_maximum, "foreign.fatca.2025"),
    ):
        total = totals[name]
        for period, limit in (("maximum", maximum_limit), ("yearend", yearend_limit)):
            suffix = "maximum_upper_bound_usd" if period == "maximum" else "yearend_usd"
            amount = Decimal(total[period].numerator) / Decimal(total[period].denominator)
            facts.append(fact(f"foreign.{name}.{suffix}", amount,
                              "sum(exact included USD fractions expressed as numerator/denominator)",
                              total[f"{period}_inputs"], total["sources"], rule))
            facts.append(fact(f"foreign.{name}.{period}_threshold_usd", Decimal(limit),
                              "2025 threshold for asserted filing_status and residence",
                              {"filing_status": document["filing_status"],
                               "residence": document["residence"]}, assertion_sources, rule))
        if total["yearend"] > yearend_limit:
            status = "yearend_threshold_crossed"
        elif total["maximum"] > maximum_limit:
            status = "potential_threshold_crossed_review"
        else:
            status = "known_not_exceeded"
        screening[name] = {"status": status, "filing_eligibility_determined": False}

    return {
        "facts": facts,
        "screening": screening,
        "warnings": [
            "Educational alpha worksheet, not filing-ready or professional advice.",
            "The sum of individual annual maxima is an upper bound, not a contemporaneous aggregate. "
            "A maximum-only crossing requires review, not a filing-required conclusion.",
            "Yearend crossings establish only arithmetic thresholds, not filing eligibility. "
            "Known-not-exceeded results rely on a complete, correctly classified inventory and supplied FX.",
            "Asset classifications, qualifying abroad status, and absence of double counting are user assertions; "
            "the worksheet does not infer them or verify the supplied yearend FX source.",
            "Identical valuation treatment for both regimes is a user assertion supported by root source_ids. "
            "Spouse-joint MFS ownership and other regime-specific valuations are unsupported.",
        ],
    }
