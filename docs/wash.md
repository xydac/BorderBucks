# Isolated Wash-Sale Worksheet

Educational alpha software, not filing-ready or professional advice. This module
does not determine substantial identity, discover transactions, import statements,
or automatically integrate employee-equity calculations.

## API

`borderbucks.wash.calculate(document)` returns `facts`, `warnings`, `replacements`,
`window`, and `allocation_decimal_places`. Invalid or unsupported input raises
`TaxInputError`. The dispatcher must provide a fixed precision-60 Decimal context
and validate the source manifest, resolve all source references, attach raw inputs
and their canonical hash, and resolve rule IDs. Direct module calls validate
record shapes and source-ID lists, but do not resolve manifest references.

Run the module tests with:

```sh
python3 -m unittest discover -s tests -p 'test_wash.py' -v
```

## Input Schema

Every listed field is required; unknown fields fail closed at every object level.
Financial numbers are decimal strings, at most 18 integer and 12 fractional
digits, without exponent notation. Shares and sale basis must be positive;
proceeds, fees, and replacement purchase basis must be nonnegative. Gross proceeds
must cover sale fees, and net proceeds must be strictly less than sale basis.
Dates use `YYYY-MM-DD`. Assertions must be JSON `true`, never `1` or `"true"`.

| Object | Required Fields |
| --- | --- |
| Document | `schema_version: "1"`, `tax_year: 2025` (integer), `kind: "wash"`, `sources`, `scope`, `sale`, `replacements` |
| Source manifest entry | `id`, `document`, `locator` |
| Scope | `reviewed_from`, `reviewed_through`, `complete_window`, `no_competing_loss_sales`, `no_related_party_or_derivative_transactions`, `not_a_dealer`, `source_ids` |
| Sale (one object, not a list) | `lot_id`, `security`, `acquired`, `date`, `shares`, `basis`, `proceeds`, `fees`, `account_type: "taxable"`, `entire_single_unadjusted_lot`, `arm_length`, `source_ids` |
| Replacement | `lot_id`, `security`, `acquired`, `acquisition_order`, `shares`, `purchase_basis`, `account_type`, `substantially_identical`, `purchase_only`, `unadjusted_basis`, `never_disposed`, `not_previously_matched`, `source_ids` |

`sources` is the manifest list. Every scope, sale, and replacement has a nonempty
list of distinct `source_ids`. IDs and security descriptions are nonempty text
of at most 500 characters with no control characters. Lot IDs must be distinct
across the sold lot and every replacement. `replacements` may be empty and has
a 10,000-lot limit. `acquisition_order` is an integer from 1 to 10,000, unique
within each acquisition date, supplied by the user to resolve actual same-day
purchase order. Document list order has no effect on results.

`basis` is the **total** basis of all sold shares, including acquisition fees.
`proceeds` is the total gross sale amount; `fees` contains sale expenses not already
subtracted from proceeds. `purchase_basis` is the **full replacement lot's**
purchase cost including acquisition fees, not merely the matched shares' cost.
Do not enter sale fees twice or mix gross and net amounts.

## Required Scope

- One arm's-length taxable loss sale in 2025 of an entire single ordinary stock
  purchase lot, with one actual acquisition date and equal loss per sold share.
  `entire_single_unadjusted_lot` confirms this and that basis and holding period
  have no prior wash adjustments, rollovers, inherited/gift basis, or other
  special adjustments. This is not a heterogeneous multi-lot sale.
- `complete_window` confirms all relevant acquisitions and holdings have been
  reviewed across all brokers, taxable accounts, your IRA/Roth IRA, and related
  parties, and every eligible replacement is included. The inclusive review
  starts on or before sale minus 30 days and ends on or after sale plus 30 days.
  December sales require January **2026** review. An empty list is an explicit
  assertion of no replacements, not a missing-data default.
- `no_competing_loss_sales` confirms isolation: no other losses compete for these
  shares, no wash-sale chain exists, and replacements have not been allocated in
  another worksheet. This stateless API cannot detect reuse across documents.
- `no_related_party_or_derivative_transactions` excludes spouse or controlled
  corporation transactions, options, contracts, short sales, straddles, warrants,
  and other non-stock or special matching rules. If review finds one, this
  worksheet is unsupported rather than permission to omit it.
- Each replacement is a direct purchase (`purchase_only`, not an award, rollover,
  transfer, or reorganization), has no prior basis adjustments (`unadjusted_basis`),
  has never been disposed of in whole or part (`never_disposed`), and has not
  previously been used in any wash match (`not_previously_matched`). These
  assertions apply through `reviewed_through`; no future disposition is calculated.
- Every listed replacement must be explicitly `substantially_identical: true`.
  Security text is descriptive, not a ticker-matching heuristic. Different labels
  can be confirmed identical; false or missing identity is rejected, not silently
  ignored. Do not include unrelated securities in the replacement list.
- Replacement `account_type` is `taxable` or `ira`; `ira` includes the taxpayer's
  traditional and Roth IRA. Other retirement account types are unsupported.
  Dealer transactions are excluded by `not_a_dealer`.

Acquisitions outside the +/-30-day window can be supplied as reviewed context,
but match zero shares. No acquisition may follow `reviewed_through`. Boundary
dates exactly minus 30 and plus 30 are included; minus 31 and plus 31 are excluded.
The originally sold lot is not a replacement and cannot be listed again.

## Results And Arithmetic

Replacements are sorted by actual acquisition date and user-confirmed same-day
order. Each in-window lot matches the lesser of its shares and the remaining
unmatched sold shares. Partial and fractional quantities are supported.

```text
total_loss = basis - (proceeds - fees)
exact_lot_wash_loss = total_loss * matched_lot_shares / sold_shares
taxable_adjusted_basis = full_purchase_basis + allocated_wash_loss
allowed_loss = total_loss - disallowed_loss             # positive loss
recognized_gain = disallowed_loss - total_loss          # negative loss or zero
disallowed_loss = deferred_loss + permanent_loss
```

These allowed-loss figures describe this isolated sale only, not Schedule D
netting, an annual capital-loss deduction limit, or a carryforward calculation.

Each match retains its exact reduced rational allocation as string `numerator`
and `denominator` in `exact_loss_fraction` and the disallowed-loss fact operands.
Decimal outputs use cumulative exact fractions floored to 40 fractional places,
then subtract the previous cumulative allocation. This explicit sub-cent
representation policy avoids repeating-division accumulation: allocations
telescope to total disallowance, disallowance never exceeds total loss, and the
last fully matching lot receives the residual so that a fully matched sale has
exactly zero allowed loss. Individual allocations differ from their exact
fractions by less than `1e-40` USD. Exact fractions remain authoritative for
further rational calculations; these are not IRS filing-rounded amounts.
The 40-place scale plus bounded monetary inputs fits the precision-60 context
without losing small adjustments when adding them to a large full-lot basis.

Taxable lots receive `replacement.<lot_id>.adjusted_basis` for the **entire lot**,
even when only some shares match. The wash adjustment belongs only to matched
shares; do not spread it onto unmatched shares. The response includes matched
and unmatched quantities so a later system can maintain separate sublots.

For an IRA match, the allocated loss is **permanently denied**. The basis increase
is zero. No `adjusted_basis` fact is emitted for an IRA: its purchase cost is not
the owner's basis in the IRA, and this module computes neither IRA contribution
basis nor distribution tax treatment.

Holding-period carry is separate from actual acquisition dates. For matched
taxable shares, `holding_period_carry` retains the sold lot's acquisition and
sale dates and `(sale_date - acquired).days` (exclude acquisition day, include
sale day). It applies only to `applies_to_shares`, never the unmatched balance.
No fake replacement acquisition date is generated. IRA carry is zero/not
computed, and no future long/short-term classification is attempted.

All facts contain decimal-string values, units, formulas, operands, source IDs,
and a versioned rule ID. Every fact conservatively includes sources from the
scope, sale, and all reviewed lots, since chronological matching depends on the
entire candidate set. Inputs are not mutated.

## Official Citations

| Registry Rule ID | Authority |
| --- | --- |
| `wash.sale.2025` | [Publication 550 (2025), Chapter 4, Wash Sales](https://www.irs.gov/pub/irs-prior/p550--2025.pdf), including Example 1 and "More or less stock bought than sold": inclusive 30-day tests, equal-share chronological matching, loss denial, and taxable basis increase. |
| `wash.ira.2025` | [Revenue Ruling 2008-5, 2008-3 I.R.B. 271, Holding](https://www.irs.gov/irb/2008-03_IRB#RR-2008-5): loss disallowed; basis in the individual's IRA or Roth IRA is not increased. Publication 550's IRA exception also applies. |
| `wash.holding.2025` | Publication 550 (2025), Chapter 4, "Holding Period" and "Wash Sales": replacement holding period includes the period of the stock sold. Same pinned PDF above. |

`fixtures/official/p550-wash.json` preserves the verified official Example 1
numbers: buy 100 for $1,000, sell for $750, replace 100 for $800, deny $250, new
basis $1,050. Its verbatim quote was verified against the IRS page explicitly
titled [Publication 550 (2025)](https://www.irs.gov/publications/p550); the fixture
pins the 2025 PDF edition. The example supplies no exact dates. Date, zero-fee,
account, and isolation assertions are separately labeled synthetic scaffolding,
not official facts or official holding-period expectations.

`examples/wash.json` and all boundary tests are synthetic. That example spans
2025/2026, with $500 total loss, $200 taxable deferral, $100 permanent IRA denial,
$200 allowed loss, and $820 full taxable replacement basis. No runtime network
access is used. Rule registry and engine integration are intentionally external
to these five files.
