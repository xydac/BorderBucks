"""Narrow, untainted section 1296 annual mark-to-market worksheets."""

from decimal import Decimal

from .common import fields, fact, number, require, source_ids, text


def calculate(document):
    """Calculate each holding separately; the engine supplies the decimal context."""
    fields(document, ("schema_version", "tax_year", "kind", "sources", "method", "holdings"),
           label="pfic")
    require(document["schema_version"] == "1", "schema_version must be '1'")
    require(type(document["tax_year"]) is int and document["tax_year"] == 2025,
            "tax_year must be the integer 2025")
    require(document["kind"] == "pfic", "kind must be pfic")
    require(document["method"] == "mtm",
            "only mtm (section 1296) is supported; default section 1291 tax/interest and QEF are not implemented")
    require(isinstance(document["sources"], list), "sources must be a list")
    manifest_ids = set()
    for source in document["sources"]:
        fields(source, ("id", "document", "locator"), label="source")
        for key in ("id", "document", "locator"):
            text(source[key], f"source {key}")
        require(source["id"] not in manifest_ids, "duplicate source ID in manifest")
        manifest_ids.add(source["id"])
    require(isinstance(document["holdings"], list) and bool(document["holdings"]),
            "holdings must be a nonempty list")
    ids = set()
    facts = []
    confirmations = (
        "directly_held", "held_at_yearend", "marketable_stock", "valid_election",
        "no_section1291_taint", "no_dispositions", "no_distributions",
    )
    for holding in document["holdings"]:
        fields(holding, (
            "id", "description", "adjusted_basis_usd", "yearend_fmv_usd",
            "prior_unreversed_inclusions_usd", "eligibility", "source_ids",
        ), label="PFIC holding")
        holding_id = text(holding["id"], "holding ID")
        text(holding["description"], "holding description")
        require(holding_id not in ids, "duplicate holding ID")
        ids.add(holding_id)
        eligibility = holding["eligibility"]
        fields(eligibility, (*confirmations, "election_start"), label="PFIC eligibility")
        for key in confirmations:
            require(eligibility[key] is True, f"eligibility.{key} must be explicitly true")
        require(eligibility["election_start"] in ("acquisition", "prior_year"),
                "election_start must be acquisition or prior_year; late/tainted elections are unsupported")
        basis = number(holding["adjusted_basis_usd"], "adjusted_basis_usd")
        fmv = number(holding["yearend_fmv_usd"], "yearend_fmv_usd")
        prior = number(holding["prior_unreversed_inclusions_usd"], "prior_unreversed_inclusions_usd")
        provenance = source_ids(holding)
        change = fmv - basis
        gain = max(change, Decimal(0))
        economic_loss = max(-change, Decimal(0))
        deductible_loss = min(economic_loss, prior)
        # Disallowed annual losses do not reset basis to FMV or create a loss carryforward.
        new_basis = basis + gain - deductible_loss
        new_unreversed = prior + gain - deductible_loss
        outputs = (
            ("fmv_change_usd", change, "yearend_fmv_usd - adjusted_basis_usd",
             {"yearend_fmv_usd": fmv, "adjusted_basis_usd": basis}),
            ("ordinary_income_usd", gain, "max(fmv_change_usd, 0)", {"fmv_change_usd": change}),
            ("deductible_ordinary_loss_usd", deductible_loss,
             "min(max(-fmv_change_usd, 0), prior_unreversed_inclusions_usd)",
             {"fmv_change_usd": change, "prior_unreversed_inclusions_usd": prior}),
            ("unallowed_loss_usd", economic_loss - deductible_loss,
             "max(-fmv_change_usd, 0) - deductible_ordinary_loss_usd",
             {"fmv_change_usd": change, "deductible_ordinary_loss_usd": deductible_loss}),
            ("ending_basis_usd", new_basis,
             "adjusted_basis_usd + ordinary_income_usd - deductible_ordinary_loss_usd",
             {"adjusted_basis_usd": basis, "ordinary_income_usd": gain,
              "deductible_ordinary_loss_usd": deductible_loss}),
            ("ending_unreversed_inclusions_usd", new_unreversed,
             "prior_unreversed_inclusions_usd + ordinary_income_usd - deductible_ordinary_loss_usd",
             {"prior_unreversed_inclusions_usd": prior, "ordinary_income_usd": gain,
              "deductible_ordinary_loss_usd": deductible_loss}),
        )
        for suffix, amount, formula, inputs in outputs:
            facts.append(fact(f"pfic.{holding_id}.{suffix}", amount, formula, inputs,
                              provenance, "pfic.mtm.2025"))
    return {
        "facts": facts,
        "method": "mtm",
        "warnings": [
            "Educational alpha worksheet, not filing-ready or professional advice; no tax liability is computed.",
            "PFIC status, marketability, direct ownership, and a valid untainted election are user assertions. "
            "Indian mutual funds are not assumed eligible for section 1296.",
            "Only annual yearend holdings without dispositions or distributions are supported. "
            "Default section 1291 tax/interest, late-election coordination, indirect ownership, and QEF are excluded.",
            "Unallowed annual loss is not a loss carryforward; basis decreases only by the allowed deduction. "
            "Prior unreversed inclusions are specific to each holding and cannot be shared across holdings.",
        ],
    }
