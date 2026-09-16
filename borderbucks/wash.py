"""Isolated single-lot stock loss sale, not a wash-sale chain engine."""

from datetime import timedelta
from decimal import Decimal
from fractions import Fraction

from .common import day, decimal_text, fact, fields, number, require, source_ids, text


def calculate(document):
    """Run inside the dispatcher's precision-60 context and source validation."""
    fields(document, ("schema_version", "tax_year", "kind", "sources", "scope",
                      "sale", "replacements"), label="wash document")
    require(document["schema_version"] == "1" and type(document["tax_year"]) is int
            and document["tax_year"] == 2025 and document["kind"] == "wash",
            "wash requires schema_version '1', tax_year 2025, kind 'wash'")
    require(isinstance(document["sources"], list), "sources must be a list")
    for source in document["sources"]:
        fields(source, ("id", "document", "locator"), label="source")
    scope = document["scope"]
    scope_flags = ("complete_window", "no_competing_loss_sales",
                   "no_related_party_or_derivative_transactions", "not_a_dealer")
    fields(scope, scope_flags + ("reviewed_from", "reviewed_through", "source_ids"),
           label="scope")
    for flag in scope_flags:
        require(scope[flag] is True, f"scope: {flag} must be true")
    reviewed_from = day(scope["reviewed_from"], "reviewed_from")
    reviewed_through = day(scope["reviewed_through"], "reviewed_through")
    sources = source_ids(scope)

    sale = document["sale"]
    fields(sale, ("lot_id", "security", "acquired", "date", "shares", "basis",
                  "proceeds", "fees", "account_type", "entire_single_unadjusted_lot",
                  "arm_length", "source_ids"), label="sale")
    sale_id = text(sale["lot_id"], "sale lot_id")
    text(sale["security"], "sale security")
    require(sale["account_type"] == "taxable", "loss sale must be taxable")
    for flag in ("entire_single_unadjusted_lot", "arm_length"):
        require(sale[flag] is True, f"sale: {flag} must be true")
    acquired = day(sale["acquired"], "sale acquired")
    sold = day(sale["date"], "sale date")
    require(acquired <= sold and sold.year == 2025,
            "sale must be in 2025 and not precede acquisition")
    window_start, window_end = sold - timedelta(days=30), sold + timedelta(days=30)
    require(reviewed_from <= window_start and reviewed_through >= window_end,
            "review must cover the complete inclusive sale +/-30-day window, including 2026")
    shares = number(sale["shares"], "sale shares", positive=True)
    basis = number(sale["basis"], "sale basis", positive=True)
    proceeds = number(sale["proceeds"], "sale proceeds")
    fees = number(sale["fees"], "sale fees")
    require(fees <= proceeds, "sale fees must not exceed gross proceeds")
    loss = basis - (proceeds - fees)
    require(loss > 0, "only a single loss sale is supported")
    sources += source_ids(sale)

    raw_lots = document["replacements"]
    require(isinstance(raw_lots, list) and len(raw_lots) <= 10000,
            "replacements must be a list of at most 10000 lots")
    lots, seen, orders = [], {sale_id}, set()
    lot_flags = ("substantially_identical", "purchase_only", "unadjusted_basis",
                 "never_disposed", "not_previously_matched")
    for raw in raw_lots:
        fields(raw, ("lot_id", "security", "acquired", "acquisition_order", "shares",
                     "purchase_basis", "account_type", "source_ids") + lot_flags,
               label="replacement")
        lot_id = text(raw["lot_id"], "replacement lot_id")
        require(lot_id not in seen, "duplicate or reused sale/replacement lot_id")
        seen.add(lot_id)
        text(raw["security"], "replacement security")
        for flag in lot_flags:
            require(raw[flag] is True, f"{lot_id}: {flag} must be true")
        require(raw["account_type"] in ("taxable", "ira"),
                "replacement account_type must be taxable or ira (including Roth IRA)")
        bought = day(raw["acquired"], "replacement acquired")
        require(bought <= reviewed_through, "replacement acquired after reviewed_through")
        order = raw["acquisition_order"]
        require(type(order) is int and 0 < order <= 10000,
                "acquisition_order must be an integer from 1 to 10000")
        require((bought, order) not in orders, "ambiguous same-day acquisition_order")
        orders.add((bought, order))
        quantity = number(raw["shares"], "replacement shares", positive=True)
        cost = number(raw["purchase_basis"], "purchase_basis")
        sources += source_ids(raw)
        lots.append((bought, order, lot_id, raw, quantity, cost))
    lots.sort(key=lambda lot: lot[:3])
    sources = sorted(set(sources))

    zero = Decimal(0)
    matched_total = disallowed = deferred = permanent = zero
    facts = [fact("wash.total_loss", loss, "basis - (proceeds - fees)",
                  {"basis": basis, "proceeds": proceeds, "fees": fees},
                  sources, "wash.sale.2025")]
    results = []
    # Floor cumulative exact fractions at 40 decimal places, then take differences.
    # This telescopes exactly, including the final residual on a fully matched sale.
    scale = 10 ** 40
    for bought, order, lot_id, raw, quantity, cost in lots:
        in_window = window_start <= bought <= window_end
        matched = min(quantity, shares - matched_total) if in_window else zero
        before = matched_total
        matched_total += matched
        cumulative = Fraction(loss) * Fraction(matched_total) / Fraction(shares)
        cumulative_decimal = Decimal(cumulative.numerator * scale // cumulative.denominator).scaleb(-40)
        allocation = cumulative_decimal - disallowed
        prior_disallowed = disallowed
        disallowed = cumulative_decimal
        exact = Fraction(loss) * Fraction(matched) / Fraction(shares)
        taxable = raw["account_type"] == "taxable"
        increase = allocation if taxable else zero
        denied = zero if taxable else allocation
        deferred += increase
        permanent += denied
        carried_days = Decimal((sold - acquired).days) if taxable and matched > 0 else zero
        prefix = f"replacement.{lot_id}"
        matching_inputs = {"replacement_shares": quantity, "sold_shares": shares,
                           "previously_matched_shares": before, "in_window": in_window,
                           "acquired": bought.isoformat(), "acquisition_order": order,
                           "window_start": window_start.isoformat(),
                           "window_end": window_end.isoformat()}
        facts.extend([
            fact(f"{prefix}.matched_shares", matched,
                 "min(replacement_shares, sold_shares - previously_matched_shares) if in_window else 0",
                 matching_inputs, sources, "wash.sale.2025", unit="shares"),
            fact(f"{prefix}.disallowed_loss", allocation,
                 "floor40(total_loss * cumulative_matched_shares / sold_shares) - prior_disallowed_loss",
                 {"total_loss": loss, "cumulative_matched_shares": matched_total,
                  "sold_shares": shares, "prior_disallowed_loss": prior_disallowed,
                  "exact_allocation_numerator": str(exact.numerator),
                  "exact_allocation_denominator": str(exact.denominator)},
                 sources, "wash.sale.2025"),
            fact(f"{prefix}.basis_increase", increase,
                 "disallowed_loss if account_type == taxable else 0",
                 {"disallowed_loss": allocation, "account_type": raw["account_type"]},
                 sources, "wash.sale.2025" if taxable else "wash.ira.2025"),
            fact(f"{prefix}.permanent_loss", denied,
                 "disallowed_loss if account_type == ira else 0",
                 {"disallowed_loss": allocation, "account_type": raw["account_type"]},
                 sources, "wash.ira.2025"),
            fact(f"{prefix}.carried_holding_days", carried_days,
                 "(sale_date - sold_lot_acquired).days if taxable and matched_shares > 0 else 0",
                 {"sale_date": sold.isoformat(), "sold_lot_acquired": acquired.isoformat(),
                  "matched_shares": matched, "taxable": taxable},
                 sources, "wash.holding.2025", unit="days"),
        ])
        if taxable:
            facts.append(fact(f"{prefix}.adjusted_basis", cost + increase,
                              "full_purchase_basis + basis_increase",
                              {"full_purchase_basis": cost, "basis_increase": increase},
                              sources, "wash.sale.2025"))
        results.append({"lot_id": lot_id, "security": raw["security"],
                        "acquired": bought.isoformat(), "acquisition_order": order,
                        "account_type": raw["account_type"], "in_window": in_window,
                        "matched_shares": decimal_text(matched),
                        "unmatched_shares": decimal_text(quantity - matched),
                        "exact_loss_fraction": {"numerator": str(exact.numerator),
                                                "denominator": str(exact.denominator)},
                        "holding_period_carry": {
                            "applies_to_shares": decimal_text(matched if taxable else zero),
                            "sold_lot_acquired": acquired.isoformat(),
                            "sold_lot_disposed": sold.isoformat(),
                            "days": decimal_text(carried_days)}})

    facts.extend([
        fact("wash.matched_shares", matched_total, "sum(replacement matched_shares)",
             {"matched_by_lot": {lot["lot_id"]: lot["matched_shares"] for lot in results}},
             sources, "wash.sale.2025", unit="shares"),
        fact("wash.disallowed_loss", disallowed,
             "floor40(total_loss * matched_shares / sold_shares)",
             {"total_loss": loss, "matched_shares": matched_total, "sold_shares": shares},
             sources, "wash.sale.2025"),
        fact("wash.deferred_loss", deferred, "disallowed_loss - permanent_loss",
             {"disallowed_loss": disallowed, "permanent_loss": permanent},
             sources, "wash.sale.2025"),
        fact("wash.permanent_loss", permanent, "disallowed_loss - deferred_loss",
             {"disallowed_loss": disallowed, "deferred_loss": deferred},
             sources, "wash.ira.2025"),
        fact("wash.allowed_loss", loss - disallowed, "total_loss - disallowed_loss (positive loss)",
             {"total_loss": loss, "disallowed_loss": disallowed}, sources, "wash.sale.2025"),
        fact("wash.recognized_gain", disallowed - loss, "disallowed_loss - total_loss (negative loss)",
             {"total_loss": loss, "disallowed_loss": disallowed}, sources, "wash.sale.2025"),
    ])
    return {"facts": facts, "replacements": results,
            "window": {"start": window_start.isoformat(), "end": window_end.isoformat()},
            "allocation_decimal_places": 40,
            "warnings": [
                "Educational alpha worksheet, not filing-ready or professional advice.",
                "Isolated stock sale only; identity and complete cross-account review are user assertions, not inferred.",
                "No automatic equity integration, wash-sale chains, replacement reuse, or subsequent dispositions.",
                "IRA matches permanently deny the loss; no IRA basis increase or taxable holding-period result is computed.",
                "Exact loss fractions accompany cumulative floor-to-40-place allocations; these are not filing-rounded amounts.",
                "Holding-period carry applies only to matched taxable shares; actual acquisition dates are unchanged.",
            ]}
