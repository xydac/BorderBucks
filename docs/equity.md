# Equity Worksheet (2025)

Educational alpha software, not filing-ready or professional advice. Runtime is
Python standard library only and does not access the network. `calculate(document)`
returns `facts`, `warnings`, `lots`, and `sales`. The dispatcher supplies a local
Decimal context with precision 60 and ROUND_HALF_EVEN, validates the source manifest
and source references, and resolves rule IDs. Values are unrounded decimal strings.

## Document Schema

Exact top-level keys: `schema_version` (string `"1"`), `tax_year` (integer `2025`),
`kind` (`"equity"`), `sources`, `lots`, `sales`. Unknown fields fail closed, including
in lots, sales, and source objects. `sources` contains `{id, document, locator}`
objects. Every lot and sale has a nonempty, duplicate-free `source_ids` list.
Financial inputs and share counts are decimal strings, not JSON numbers.

Each lot requires these fields:

| Field | Meaning |
| --- | --- |
| `lot_id` | Unique nonempty identifier |
| `award_type` | `RSU`, `NSO`, `ISO`, or `ESPP` |
| `acquired` | YYYY-MM-DD; settlement for RSU, exercise and transfer for options |
| `shares` | Positive full gross award shares, including shares sold to cover withholding |
| `cost_per_share` | Actual cash price, nonnegative; zero for supported RSUs |
| `shares_are_gross` | Must be literal `true`, supported by cited award records |
| `all_disposals_included` | Must be `true`: all disposals since acquisition are listed, all in 2025; no prior-year disposals |
| `unadjusted_basis` | Must be `true`: no splits, return of capital, wash basis, reorganizations, gifts, or other basis adjustments |
| `unrestricted_at_acquisition` | Must be `true`: stock is fully vested and transferable at acquisition; no deferred vesting or income elections |
| `source_ids` | Records supporting financial inputs and scope assertions |

Award-specific required fields (fields from other award types are rejected):

| Award | Additional Fields |
| --- | --- |
| RSU | `compensation_per_share` (positive), `wages_included: true` |
| NSO | `grant`, `exercise_fmv_per_share`, `compensation_per_share`, `wages_included: true`, `grant_value_not_determinable: true` |
| ISO | `grant`, `exercise_fmv_per_share`, `statutory_plan_confirmed: true`, `prior_amt_adjustment_per_share` |
| ESPP | `grant`, `exercise_fmv_per_share`, `grant_fmv_per_share`, `grant_option_price_per_share`, `statutory_plan_confirmed: true` |

`statutory_plan_confirmed` asserts that the award actually qualifies under section
422/423, including employment, nontransferability and applicable limits. This engine
does not establish plan eligibility. Grant must be on or before acquisition. FMVs
are positive; underwater exercises are not supported. NSO wages must exactly match
the exercise spread, and must already have been included in income. For RSU,
settlement and wage recognition must coincide, with no cash purchase cost.

For ESPP, `grant_option_price_per_share` means the price computed **as if exercised
at grant**, not necessarily the actual exercise price. This handles lookback plans
without guessing a discount. It must be 85%-100% of grant FMV. Actual exercise price
must be at least 85% of the lower of grant/exercise FMV.

For ISO acquired before 2025, `prior_amt_adjustment_per_share` must explicitly
confirm the exercise FMV minus price included in AMT basis in the exercise year.
For a 2025 exercise it must be `"0"`. This is a basis assertion, not an assertion
that AMT was actually payable. Missing/contradictory records are rejected.

Each sale requires `sale_id` (unique), `lot_id` (existing), `shares` (positive),
`date` (2025 YYYY-MM-DD), `proceeds` (gross total before fees), `fees` (total),
`reported_basis` (broker-reported total), `arm_length: true`,
`at_fair_market_value: true`, and `source_ids`. Monetary totals are nonnegative.
`proceeds` represents disposal FMV under the explicit FMV-sale assertion; it is not
net cash after withholding taxes. Withholding taxes do not reduce sale proceeds.

Disqualified ISO sales additionally require `iso_sale_limitation_eligible: true`:
the cited records confirm a fully taxable arm's-length sale for which a loss, if
sustained, would be recognized, with no related-party or wash-sale limitation.
This field is rejected for other dispositions. Without that assertion, the engine
refuses to apply the ISO sale-price limitation. It cannot verify replacement
purchases automatically.

Sales must be chronological within each lot and cannot precede acquisition.
Same-day sales are allowed. Multiple same-day sales consume in input order. Partial
sales reduce remaining shares cumulatively; oversales fail. All history for the
lot must be present. Net-only grants, withheld-share cancellations, and prior-year
sales are unsupported. An actual sell-to-cover sale can be listed explicitly, as
in `examples/equity.json`. There is no statement inference, FIFO selection, or
automatic creation of missing withholding transactions. Assertions must be backed
by records; a bare `true` is not evidence of completeness.

## Calculations

| Award | Compensation and Regular Basis |
| --- | --- |
| RSU | Acquisition wages already included; basis = cash cost (zero) + those wages |
| NSO | Acquisition wages already included = exercise spread; basis = price + wages |
| Qualifying ISO | No disposition wages; regular basis = exercise price |
| Disqualified ISO | Wages = lesser of exercise spread and positive net sale gain over exercise cost; basis = exercise cost + required wages |
| Qualifying ESPP | Wages = lesser of grant discount and positive disposal FMV less purchase cost; basis = purchase cost + required wages |
| Disqualified ESPP | Wages = full exercise spread, even on a sale below purchase cost; basis = purchase cost + required wages |

ESPP qualifying compensation uses disposal FMV (gross proceeds), not proceeds net
of commissions. Fees reduce capital gain. This intentionally differs from the ISO
disqualified net-sale-gain limitation. Disposition compensation is the **total
required income**, not an instruction to add it again when already reported on a
W-2. W-2 reconciliation is outside this module.

Qualification requires sale strictly **after** both the second grant anniversary
and the first acquisition anniversary. Long-term capital treatment requires sale
strictly after the first acquisition anniversary and is independent of statutory
qualification. February 29 maps to February 28 in a non-leap anniversary year;
March 1 qualifies, February 28 does not. Day-count shortcuts are not used.

For earlier-year ISO exercises, AMT sale basis = purchase cost + the separately
asserted prior AMT adjustment, without adding regular-tax disposition wages again.
For same-year exercise and sale, AMT sale basis equals regular basis and there is
no exercise adjustment for the sold shares. The current-year exercise adjustment
applies only to 2025-exercised shares still held at year-end. Remaining AMT basis
is reported separately. This is not a complete AMT disposition reconciliation,
Form 6251 calculation, capital-loss limitation, or minimum-tax-credit calculation.

## Output And Limits

Fact IDs are `lot.<lot_id>.<metric>` and `sale.<sale_id>.<metric>`. Each fact retains
its formula, named inputs, source IDs, and versioned rule ID. Sale metrics include
`disposition_compensation`, `actual_basis`, `reported_basis_correction`,
`capital_gain_before_wash`, `remaining_shares`, and `long_term` (0/1). ISO/ESPP add
`qualified` (0/1); ISO adds `amt_basis`. Lot metrics include `purchase_cost`,
`remaining_shares`, RSU/NSO `acquisition_compensation` (already recognized income),
and ISO `current_year_amt_exercise_adjustment` and `remaining_amt_basis`.

The signed Form 8949 basis correction is **reported basis minus correct basis**.
Thus an understated reported basis creates a negative adjustment. Withholding,
commission reporting conventions, adjustment codes, and other Form 8949 fields
are not inferred. Gain = gross proceeds - fees - actual basis, **before wash
sales**, and is never described as final. `sales` metadata reports date, award,
lot, qualification, and long/short term; `lots` reports acquisition date and
remaining shares. Acquisition compensation is historical already-recognized
income for the acquisition year, not necessarily 2025 income.

Unsupported: non-FMV/non-arm's-length transfers, gifts, death, corporate actions,
restricted exercises, readily determinable NSO grant values, 83(b)/83(i) elections,
nonstatutory ESPPs, ISO limit reclassification, foreign-currency inputs, historical
disposals, existing wash-sale adjustments, automated wage matching, and tax filing.
Financial inputs are USD. Scenarios can replace a single existing sale in the
document and call the same API again; there is no hidden mutable state.

## Citations And Tests

Pinned publication: https://www.irs.gov/pub/irs-prior/p525--2025.pdf

| Rule ID | Publication 525 (2025) Locator |
| --- | --- |
| `equity.rsu.2025` | Restricted Property, substantially vested property and basis rules |
| `equity.nso.2025` | Stock Options > Nonstatutory Stock Options > Option without readily determinable value; Sale of the stock |
| `equity.iso.2025` | Statutory Stock Options > Alternative minimum tax (AMT); ISOs > holding period satisfied/not satisfied; Example 8 |
| `equity.espp.2025` | Statutory Stock Options > Employee stock purchase plan > Option granted at a discount; holding period not satisfied; Examples 10-11 |
| `equity.basis.2025` | Nonstatutory/Statutory Stock Options > Sale of the stock; Form 8949 basis-adjustment cautions |
| `equity.holding.2025` | Statutory Stock Options > Holding period requirement |

`fixtures/official/p525_espp_example10.json` retains 100 shares, prices $20/$22/$23/$30,
$200 wages, and $800 capital gain. Example 11 retains $300 wages and $700 capital
gain. Neither IRS ESPP example gives calendar years: fixture metadata says so and
explicitly labels the assigned dates adapted, preserving 18+14 and 18+6 month
intervals. `p525_iso_example8.json` keeps the original 2023/2024/2025 dates and
$200 wages/$300 capital gain. Fixtures record precise locators, quotes, and the
pinned URL. Official expected outputs are separate from derived assertions and
fixture assumptions. Other test cases and the sample document are synthetic.

Run `python3 -m unittest discover -s tests -p 'test_equity.py' -v`.
