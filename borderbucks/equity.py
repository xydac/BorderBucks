"""Explicit, unadjusted employee-stock lots; educational pre-wash worksheets."""

from decimal import Decimal

from .common import day, fact, fields, number, require, source_ids, text


def _anniversary(value, years):
    """February 29 anniversaries fall on February 28 in non-leap years."""
    try:
        return value.replace(year=value.year + years)
    except ValueError:
        return value.replace(year=value.year + years, day=28)


def calculate(document):
    """Calculate inside the dispatcher's fixed precision-60 Decimal context."""
    fields(document, ("schema_version", "tax_year", "kind", "sources", "lots", "sales"),
           label="equity document")
    require(document["schema_version"] == "1" and type(document["tax_year"]) is int
            and document["tax_year"] == 2025 and document["kind"] == "equity",
            "equity requires schema_version '1', tax_year 2025, kind 'equity'")
    require(isinstance(document["lots"], list) and document["lots"],
            "lots must be a nonempty list")
    require(isinstance(document["sales"], list), "sales must be a list")
    # Manifest validation is also done by the dispatcher, but nested shapes stay strict.
    require(isinstance(document["sources"], list), "sources must be a list")
    for source in document["sources"]:
        fields(source, ("id", "document", "locator"), label="source")

    zero = Decimal(0)
    facts, lots, sale_results = [], {}, []
    common_fields = ("lot_id", "award_type", "acquired", "shares", "cost_per_share",
                     "shares_are_gross", "all_disposals_included", "unadjusted_basis",
                     "unrestricted_at_acquisition", "source_ids")
    award_fields = {
        "RSU": ("compensation_per_share", "wages_included"),
        "NSO": ("grant", "exercise_fmv_per_share", "compensation_per_share",
                "wages_included", "grant_value_not_determinable"),
        "ISO": ("grant", "exercise_fmv_per_share", "statutory_plan_confirmed",
                "prior_amt_adjustment_per_share"),
        "ESPP": ("grant", "exercise_fmv_per_share", "grant_fmv_per_share",
                 "grant_option_price_per_share", "statutory_plan_confirmed"),
    }
    for raw in document["lots"]:
        require(isinstance(raw, dict), "lot must be an object")
        award = raw.get("award_type")
        require(isinstance(award, str) and award in award_fields, "unsupported award_type")
        fields(raw, common_fields + award_fields[award], label="lot")
        lot_id = text(raw["lot_id"], "lot_id")
        require(lot_id not in lots, "duplicate lot_id")
        sources = source_ids(raw)
        for assertion in ("shares_are_gross", "all_disposals_included", "unadjusted_basis",
                          "unrestricted_at_acquisition"):
            require(raw[assertion] is True, f"{lot_id}: {assertion} must be true")
        acquired = day(raw["acquired"], "acquired")
        require(acquired.year <= 2025, "acquisition must be no later than 2025")
        shares = number(raw["shares"], "shares", positive=True)
        cost = number(raw["cost_per_share"], "cost_per_share")
        compensation, exercise_fmv, prior_amt = zero, zero, zero
        grant, grant_fmv, grant_price = None, zero, zero
        if award != "RSU":
            grant = day(raw["grant"], "grant")
            require(grant <= acquired, "grant must not follow acquisition/exercise")
            exercise_fmv = number(raw["exercise_fmv_per_share"],
                                  "exercise_fmv_per_share", positive=True)
            require(cost <= exercise_fmv, "underwater exercises are unsupported")
        if award in ("RSU", "NSO"):
            require(raw["wages_included"] is True,
                    "RSU/NSO compensation must be explicitly confirmed included in wages")
            compensation = number(raw["compensation_per_share"], "compensation_per_share")
            if award == "RSU":
                require(cost == zero and compensation > zero,
                        "RSU requires zero cost and positive settlement compensation")
            else:
                require(raw["grant_value_not_determinable"] is True,
                        "NSO requires no readily determinable grant value")
                require(compensation == exercise_fmv - cost,
                        "NSO compensation must equal the exercise spread")
        else:
            require(raw["statutory_plan_confirmed"] is True,
                    "statutory plan and employee eligibility must be confirmed")
        if award == "ESPP":
            grant_fmv = number(raw["grant_fmv_per_share"], "grant_fmv_per_share", positive=True)
            grant_price = number(raw["grant_option_price_per_share"],
                                 "grant_option_price_per_share", positive=True)
            require(grant_fmv * Decimal("0.85") <= grant_price <= grant_fmv,
                    "ESPP grant option price must be 85%-100% of grant FMV")
            require(cost >= min(grant_fmv, exercise_fmv) * Decimal("0.85"),
                    "ESPP exercise price below statutory minimum is unsupported")
        if award == "ISO":
            prior_amt = number(raw["prior_amt_adjustment_per_share"],
                               "prior_amt_adjustment_per_share")
            expected = exercise_fmv - cost if acquired.year < 2025 else zero
            require(prior_amt == expected,
                    "ISO prior AMT adjustment must equal prior-year exercise spread, or zero for 2025")
        lots[lot_id] = dict(award=award, acquired=acquired, shares=shares, remaining=shares,
                            cost=cost, compensation=compensation, exercise_fmv=exercise_fmv,
                            grant=grant, grant_fmv=grant_fmv, grant_price=grant_price,
                            prior_amt=prior_amt, sources=sources, last_sale=acquired,
                            sale_sources=[])
        facts.append(fact(f"lot.{lot_id}.purchase_cost", shares * cost,
                          "shares * cost_per_share", {"shares": shares, "cost_per_share": cost},
                          sources, "equity.basis.2025"))
        if award in ("RSU", "NSO"):
            facts.append(fact(f"lot.{lot_id}.acquisition_compensation", shares * compensation,
                              "shares * compensation_per_share (already included in wages)",
                              {"shares": shares, "compensation_per_share": compensation,
                               "acquired": acquired.isoformat(), "wages_included": True},
                              sources, f"equity.{award.lower()}.2025"))

    seen_sales = set()
    for raw in document["sales"]:
        required = ("sale_id", "lot_id", "shares", "date", "proceeds", "fees",
                    "reported_basis", "arm_length", "at_fair_market_value", "source_ids")
        fields(raw, required, ("iso_sale_limitation_eligible",), label="sale")
        sale_id = text(raw["sale_id"], "sale_id")
        require(sale_id not in seen_sales, "duplicate sale_id")
        seen_sales.add(sale_id)
        lot_id = text(raw["lot_id"], "lot_id")
        require(lot_id in lots, "sale references unknown lot_id")
        lot = lots[lot_id]
        award = lot["award"]
        sources = sorted(set(lot["sources"] + source_ids(raw)))
        require(raw["arm_length"] is True and raw["at_fair_market_value"] is True,
                "only arm's-length sales at fair market value are supported")
        sold = day(raw["date"], "sale date")
        require(sold.year == 2025, "only 2025 sales supported; lots must have no earlier disposals")
        require(sold >= lot["acquired"], "sale precedes acquisition")
        require(sold >= lot["last_sale"], "sales for each lot must be chronological")
        shares = number(raw["shares"], "sale shares", positive=True)
        require(shares <= lot["remaining"], "sale oversells remaining gross lot shares")
        proceeds = number(raw["proceeds"], "proceeds")
        fees = number(raw["fees"], "fees")
        reported = number(raw["reported_basis"], "reported_basis")
        qualified = None
        long_term = sold > _anniversary(lot["acquired"], 1)
        if award in ("ISO", "ESPP"):
            qualified = long_term and sold > _anniversary(lot["grant"], 2)
        if award == "ISO" and not qualified:
            require(raw.get("iso_sale_limitation_eligible") is True,
                    "disqualified ISO requires explicit sale-limitation eligibility (no wash/related sale)")
        else:
            require("iso_sale_limitation_eligible" not in raw,
                    "iso_sale_limitation_eligible is only valid for disqualified ISO sales")

        cost = shares * lot["cost"]
        spread = shares * (lot["exercise_fmv"] - lot["cost"])
        disposition_compensation = zero
        operands = {"shares": shares, "cost_per_share": lot["cost"],
                    "exercise_fmv_per_share": lot["exercise_fmv"], "proceeds": proceeds,
                    "fees": fees, "qualified": qualified}
        formula = "0 (no disposition compensation)"
        if award == "ESPP":
            if qualified:
                discount = shares * (lot["grant_fmv"] - lot["grant_price"])
                disposition_compensation = min(discount, max(zero, proceeds - cost))
                operands.update(grant_fmv_per_share=lot["grant_fmv"],
                                grant_option_price_per_share=lot["grant_price"])
                formula = ("min(shares * (grant_fmv_per_share - grant_option_price_per_share), "
                           "max(0, proceeds - shares * cost_per_share))")
            else:
                disposition_compensation = spread
                formula = "shares * (exercise_fmv_per_share - cost_per_share)"
        elif award == "ISO" and not qualified:
            disposition_compensation = min(spread, max(zero, proceeds - fees - cost))
            operands["iso_sale_limitation_eligible"] = True
            formula = ("min(shares * (exercise_fmv_per_share - cost_per_share), "
                       "max(0, proceeds - fees - shares * cost_per_share))")
        actual_basis = cost + shares * lot["compensation"] + disposition_compensation
        prefix = f"sale.{sale_id}"
        facts.extend([
            fact(f"{prefix}.disposition_compensation", disposition_compensation, formula,
                 operands, sources, f"equity.{award.lower()}.2025"),
            fact(f"{prefix}.actual_basis", actual_basis,
                 "shares * (cost_per_share + acquisition_compensation_per_share) + disposition_compensation",
                 {"shares": shares, "cost_per_share": lot["cost"],
                  "acquisition_compensation_per_share": lot["compensation"],
                  "disposition_compensation": disposition_compensation}, sources, "equity.basis.2025"),
            fact(f"{prefix}.reported_basis_correction", reported - actual_basis,
                 "reported_basis - actual_basis (Form 8949 adjustment sign)",
                 {"reported_basis": reported, "actual_basis": actual_basis}, sources, "equity.basis.2025"),
            fact(f"{prefix}.capital_gain_before_wash", proceeds - fees - actual_basis,
                 "proceeds - fees - actual_basis",
                 {"proceeds": proceeds, "fees": fees, "actual_basis": actual_basis},
                 sources, "equity.basis.2025"),
            fact(f"{prefix}.long_term", Decimal(int(long_term)),
                 "sale_date > first acquisition anniversary",
                 {"sale_date": sold.isoformat(), "acquired": lot["acquired"].isoformat(),
                  "anniversary": _anniversary(lot["acquired"], 1).isoformat()},
                 sources, "equity.holding.2025", unit="boolean"),
        ])
        if qualified is not None:
            facts.append(fact(f"{prefix}.qualified", Decimal(int(qualified)),
                              "sale_date > acquisition_anniversary AND sale_date > grant_anniversary",
                              {"sale_date": sold.isoformat(),
                               "acquisition_anniversary": _anniversary(lot["acquired"], 1).isoformat(),
                               "grant_anniversary": _anniversary(lot["grant"], 2).isoformat()},
                              sources, "equity.holding.2025", unit="boolean"))
        if award == "ISO":
            same_year = lot["acquired"].year == sold.year
            amt_basis = actual_basis if same_year else cost + shares * lot["prior_amt"]
            facts.append(fact(f"{prefix}.amt_basis", amt_basis,
                              "actual_basis if same_year else shares * (cost_per_share + prior_amt_adjustment_per_share)",
                              {"same_year": same_year, "actual_basis": actual_basis, "shares": shares,
                               "cost_per_share": lot["cost"],
                               "prior_amt_adjustment_per_share": lot["prior_amt"]},
                              sources, "equity.iso.2025"))
        before = lot["remaining"]
        lot["remaining"] -= shares
        lot["last_sale"] = sold
        lot["sale_sources"] = sorted(set(lot["sale_sources"] + sources))
        facts.append(fact(f"{prefix}.remaining_shares", lot["remaining"],
                          "remaining_before_sale - shares_sold",
                          {"remaining_before_sale": before, "shares_sold": shares},
                          lot["sale_sources"], "equity.basis.2025", unit="shares"))
        sale_results.append({"sale_id": sale_id, "lot_id": lot_id, "date": sold.isoformat(),
                             "award_type": award, "qualified": qualified,
                             "term": "long" if long_term else "short"})

    lot_results = []
    for lot_id, lot in lots.items():
        sources = sorted(set(lot["sources"] + lot["sale_sources"]))
        remaining = fact(f"lot.{lot_id}.remaining_shares", lot["remaining"],
                         "gross_shares - cumulative_sold_shares",
                         {"gross_shares": lot["shares"],
                          "cumulative_sold_shares": lot["shares"] - lot["remaining"]},
                         sources, "equity.basis.2025", unit="shares")
        facts.append(remaining)
        lot_results.append({"lot_id": lot_id, "award_type": lot["award"],
                            "acquired": lot["acquired"].isoformat(),
                            "remaining_shares": remaining["value"]})
        if lot["award"] == "ISO":
            current_year = lot["acquired"].year == 2025
            adjustment = lot["remaining"] * (lot["exercise_fmv"] - lot["cost"]) if current_year else zero
            facts.append(fact(f"lot.{lot_id}.current_year_amt_exercise_adjustment", adjustment,
                              "remaining_shares * (exercise_fmv_per_share - cost_per_share) if acquired_in_2025 else 0",
                              {"remaining_shares": lot["remaining"], "acquired_in_2025": current_year,
                               "exercise_fmv_per_share": lot["exercise_fmv"],
                               "cost_per_share": lot["cost"]}, sources, "equity.iso.2025"))
            facts.append(fact(f"lot.{lot_id}.remaining_amt_basis",
                              lot["remaining"] * (lot["cost"] + lot["prior_amt"]) + adjustment,
                              "remaining_shares * (cost_per_share + prior_amt_adjustment_per_share) + current_year_adjustment",
                              {"remaining_shares": lot["remaining"], "cost_per_share": lot["cost"],
                               "prior_amt_adjustment_per_share": lot["prior_amt"],
                               "current_year_adjustment": adjustment}, sources, "equity.iso.2025"))
    return {"facts": facts, "lots": lot_results, "sales": sale_results, "warnings": [
        "Educational alpha worksheet, not filing-ready or professional advice.",
        "Capital gains/losses are BEFORE wash sales; wash-sale integration is not automated. Gains are not final.",
        "Disposition compensation is total required income, not extra wages to add to an existing W-2; reconcile reporting separately.",
        "ISO AMT amounts are separate basis/exercise worksheets, not a full Form 6251 or AMT credit calculation.",
    ]}
