# India-US Cross-Border Worksheets (2025)

Educational alpha software, not filing-ready and not professional advice. These
worksheets perform limited arithmetic on explicit user assertions. They do not
classify assets, establish tax residence, validate elections, determine filing
eligibility, calculate tax due, or prepare FBAR, Form 8938, or Form 8621.

All examples and regression fixtures here are **synthetic**, not official IRS
worked examples. The INR rate in the example is an arithmetic assumption, not a
published or recommended exchange rate.

## Module Contract

`borderbucks.foreign.calculate(document)` and
`borderbucks.pfic.calculate(document)` return dictionaries with `facts` and
`warnings` lists. Foreign also returns `screening`; PFIC returns `method: "mtm"`.
Invalid or unsupported input raises `common.TaxInputError`.

The main engine supplies its fixed local Decimal context with precision 60 and
checks **every** input `source_ids` reference against the source manifest, even
for excluded assets and unused FX rates. These modules validate shapes and source
ID lists, but do not independently resolve references. Use the engine for public
input processing. A direct module caller must provide the same context and
reference checks. Neither module mutates the document or performs network I/O.

Facts use `common.fact(id, amount, formula, inputs, sources, rule, unit)`. Each has
a decimal-string `value`, `unit: "USD"`, formula, operands in `inputs`,
`source_ids`, and versioned `rule_ids`. There is no whole-dollar or cent rounding.
Foreign FX conversions and aggregates use exact rational arithmetic for threshold
comparisons. Per-asset facts are finite-precision Decimal presentations, not
aggregation operands; each aggregate is converted to Decimal once, from its exact
fraction. Recurring quotients may therefore be rounded for presentation but never
affect threshold decisions. No epsilon or tolerance is used.

All objects reject unknown fields. All keys described as required must be present.
Booleans must be JSON `true` or `false`, never `1`, `0`, strings, or null. Financial
numbers must be nonnegative decimal **strings** accepted by `common.number` (up
to 18 integer and 12 fractional digits; no exponent notation or commas). FX rates
must be strictly positive. IDs and descriptions are nonempty text. Source ID lists
must be nonempty and contain no duplicates. Asset, holding, source-manifest, and
FX-currency identifiers must be unique within their respective collections.

Both document kinds require these shared fields:

```json
{
  "schema_version": "1",
  "tax_year": 2025,
  "kind": "foreign",
  "sources": [
    {"id": "synthetic", "document": "Synthetic worksheet", "locator": "2025"}
  ]
}
```

This is only the shared envelope; add the kind-specific fields below for a valid
document. `tax_year` must be an integer, not a string or float. Source entries
contain exactly `id`, `document`, and `locator`.

## Foreign Schema

The complete working example is [`examples/foreign.json`](../examples/foreign.json).
In addition to the shared envelope with `kind: "foreign"`, required fields are:

| Field | Meaning |
| --- | --- |
| `source_ids` | Provenance for inventory, classification, filing-status, residence, no-double-counting, and same-valuation-for-both-regimes assertions. |
| `filing_status` | `single`, `married_separate`, or `married_joint`. |
| `residence` | `us` or `abroad`; not inferred from citizenship or an Indian address. |
| `qualifying_abroad_confirmed` | Must be `true` for `abroad`, `false` for `us`. User confirms the applicable qualifying abroad test. |
| `inventory_complete` | Must be `true`; partial-inventory screenings are rejected. |
| `no_double_counting_confirmed` | Must be `true`; IDs alone cannot detect duplicate real-world assets. |
| `same_valuation_for_both_regimes_confirmed` | Must be `true`; spouse-joint MFS ownership and other regime-specific valuations are unsupported. Root `source_ids` must support this assertion. |
| `fx_rates` | List of explicit yearend rates, one per used currency. Only USD and INR are supported. |
| `assets` | Complete inventory with explicit inclusion flags; may be empty only with the completeness confirmation. |

Each FX object has exactly `currency`, `date`, `local_per_usd`, and `source_ids`.
The date must be `"2025-12-31"`. A USD rate must explicitly be `"1"` (equivalent
decimal strings such as `"1.0"` are accepted); it is not silently inserted. Each
asset's currency needs a matching rate. Both local maxima and yearend values are
converted as `local_value / local_per_usd` using this yearend rate. Supply the
applicable official rate and its provenance; this application does not fetch or
verify rates or infer a daily maximum from transactions.

Each asset requires `id`, `description`, `asset_type`, `currency`, `maximum_local`,
`yearend_local`, `include_fbar`, `include_form8938`, and `source_ids`.
`asset_type` is `account` or `asset`. `include_fbar` may be true only for an
explicitly classified account; `include_form8938` may be true for either type.
The flags are independent: no inclusion is inferred from a name, country, type,
or PFIC label. `yearend_local` must not exceed `maximum_local`, including for
excluded assets. Account values must include the securities already inside them.

The same supplied valuation is used for each regime in which an asset is included.
For married filing separately (MFS), spouse-joint assets require half valuation for
Form 8938 threshold purposes but full valuation for FBAR. This worksheet does not
model that difference: spouse-joint MFS ownership and any other regime-specific
valuation requirements are outside scope. The mandatory
`same_valuation_for_both_regimes_confirmed: true` is an explicit user assertion,
supported by the root `source_ids`, that no such valuation differences apply.
Do not omit assets, change inclusion flags, or halve a shared input to bypass this
restriction; that would invalidate the complete-inventory or valuation assertion.

An asset already represented within an account may additionally specify
`included_in_account_id`, referencing an `account` in the same inventory. Only an
`asset` may use this field; both inclusion flags must then be false. Do not add
the underlying PFIC again to the brokerage-account total. Omit underlying assets
from this inventory entirely, or explicitly mark them this way. A separately
reported PFIC tax worksheet does not imply separate FBAR/Form 8938 inclusion.
The model cannot detect undisclosed economic duplication, so the explicit
no-double-counting confirmation remains necessary.

For each reporting regime, the module sums individual included maxima in USD as
a **conservative upper bound**, and separately sums included yearend USD values.
It does not claim that individual maxima occurred simultaneously. Threshold
comparisons are strictly `>` on exact fractions, without dollar rounding:

| Reporting regime | Residence/status | Yearend threshold | Any-time threshold |
| --- | --- | ---: | ---: |
| FBAR | All supported statuses | $10,000 (yearend is one observation) | $10,000 |
| Form 8938 | US single or married separate | $50,000 | $75,000 |
| Form 8938 | US married joint | $100,000 | $150,000 |
| Form 8938 | Qualifying abroad single or married separate | $200,000 | $300,000 |
| Form 8938 | Qualifying abroad married joint | $400,000 | $600,000 |

`screening.fbar.status` and `screening.form8938.status` each have one of:

- `yearend_threshold_crossed`: the supplied yearend aggregate strictly exceeds
  its threshold. This is definitive **arithmetic**, not a filing determination.
- `potential_threshold_crossed_review`: only the sum of individual maxima
  exceeds the any-time threshold. Review contemporaneous balances and eligibility;
  do not interpret this as "filing required."
- `known_not_exceeded`: yearend does not exceed its threshold and the maxima upper
  bound does not exceed the any-time threshold, conditional on complete, correctly
  classified and valued inputs. Equality is not a crossing.

Each screening also returns `filing_eligibility_determined: false`. A maximum-only
crossing is conservatively reported as potential even with one included account.
Neither a below-threshold status nor exclusion from one regime establishes the
absence of other tax or information-reporting obligations.

Fact IDs are `foreign.asset.<id>.maximum_usd` and
`foreign.asset.<id>.yearend_usd`, including excluded assets for audit. Aggregate
IDs are `foreign.<regime>.maximum_upper_bound_usd` and
`foreign.<regime>.yearend_usd`; threshold IDs are
`foreign.<regime>.maximum_threshold_usd` and
`foreign.<regime>.yearend_threshold_usd`. Here `<regime>` is `fbar` or `form8938`.
Aggregate operands contain only explicitly included assets, keyed by their
converted fact IDs. Each operand is an exact USD fraction string in
`"numerator/denominator"` form, such as `"5000/9"` for INR 50,000 at 90 INR/USD,
or `"5000/1"` for an integral USD amount. The aggregate formula sums these exact
fractions, not the displayed per-asset Decimal values. Eighteen accounts each
valued at INR 50,000 at 90 INR/USD total exactly USD 10,000 and do not cross the
FBAR threshold, even if summing displayed decimals would produce a tiny excess.

The synthetic example produces $80,000 as the maxima upper bound and $45,000 at
yearend for both regimes. FBAR has a yearend crossing; Form 8938 has only a
potential crossing for a US single filer. The underlying $15,000 yearend PFIC is
already inside the brokerage's $40,000 and is not added a second time.

## PFIC Schema

The complete working example is [`examples/pfic.json`](../examples/pfic.json).
In addition to the shared envelope with `kind: "pfic"`, the document requires
`method: "mtm"` and a nonempty `holdings` list. **Only section 1296 annual
mark-to-market is implemented.** Default section 1291 tax/interest and QEF are
explicitly rejected. Availability of a `pfic.qef.2025` registry rule does not
indicate that QEF calculations are implemented.

Each holding has exactly these fields:

| Field | Meaning |
| --- | --- |
| `id`, `description` | Unique holding identifier and human-readable description. |
| `adjusted_basis_usd` | Adjusted basis immediately before this annual mark-to-market adjustment, not necessarily original cost. |
| `yearend_fmv_usd` | Fair market value at the close of the tax year, in USD. |
| `prior_unreversed_inclusions_usd` | Prior section 1296 income inclusions less prior allowed section 1296 deductions, specific to this holding. |
| `eligibility` | Required explicit confirmations below. |
| `source_ids` | Provenance for basis, FMV, prior inclusions, PFIC status, and all eligibility assertions. |

The exact eligibility object is:

```json
{
  "directly_held": true,
  "held_at_yearend": true,
  "marketable_stock": true,
  "valid_election": true,
  "election_start": "prior_year",
  "no_section1291_taint": true,
  "no_dispositions": true,
  "no_distributions": true
}
```

Every confirmation must be explicitly `true`. `election_start` is `acquisition`
for a valid election from acquisition, or `prior_year` for an existing election
from a prior year. Both require no section 1291 taint. These assertions do not
make or validate an election. New late elections, purging/transition calculations,
indirect holdings, dispositions, distributions, and section 1291 coordination
are outside scope. Use separately identified homogeneous holdings; the module
does not reconstruct tax lots, allocate basis, or combine loss limitations.

Indian mutual funds are **not** presumed to be qualifying marketable stock.
Daily NAV publication or availability for redemption is not an eligibility
determination by this application. Eligibility and PFIC status need independent
review. USD basis and FMV must already be correctly established; this module
does not perform INR conversion or derive historical adjusted basis.

For each holding:

```text
change = yearend_fmv_usd - adjusted_basis_usd
ordinary_income = max(change, 0)
deductible_ordinary_loss = min(max(-change, 0), prior_unreversed_inclusions_usd)
unallowed_loss = max(-change, 0) - deductible_ordinary_loss
ending_basis = adjusted_basis_usd + ordinary_income - deductible_ordinary_loss
ending_unreversed_inclusions = prior_unreversed_inclusions_usd
                              + ordinary_income - deductible_ordinary_loss
```

The unallowed loss is not a separately deductible carryforward. Basis does **not**
automatically reset to FMV when a loss is limited. Prior inclusions and current
gains on another holding cannot unlock this holding's loss deduction.

Fact IDs are prefixed `pfic.<holding-id>.` and end in `fmv_change_usd`,
`ordinary_income_usd`, `deductible_ordinary_loss_usd`, `unallowed_loss_usd`,
`ending_basis_usd`, or `ending_unreversed_inclusions_usd`. Deductions are represented
as positive amounts; `fmv_change_usd` can be negative. There is no net tax or tax
rate calculation.

In the synthetic example, basis is $10,000, FMV is $7,000, and prior unreversed
inclusions are $1,000. The deductible ordinary loss is $1,000, unallowed loss is
$2,000, ending basis is **$9,000**, not $7,000, and remaining unreversed inclusions
are zero.

## Official References

- [`foreign.fbar.2025`, `foreign.fatca.2025`: IRS comparison of Form 8938 and FBAR
  requirements](https://www.irs.gov/businesses/comparison-of-form-8938-and-fbar-requirements).
  The threshold table above uses the supplied verified 2025 thresholds. Reporting
  eligibility and exceptions still require separate review.
- [`foreign.fx.2025`: IRS comparison, determining maximum account or asset value
  and converting foreign currency](https://www.irs.gov/businesses/comparison-of-form-8938-and-fbar-requirements).
  Supply the applicable yearend local-units-per-USD rate with provenance; maxima
  and yearend valuations must already follow the relevant valuation rules.
- [`pfic.mtm.2025`: 2025 Instructions for Form 8621](https://www.irs.gov/pub/irs-prior/i8621--2025.pdf),
  "Mark-to-Market Election," "Tax Consequences," "Basis adjustment," and Part IV,
  lines 10a through 12, including "Unreversed inclusions." These support the
  ordinary gain, limited loss, and direct-holder basis adjustment used here.

## Verification

Run the synthetic module regressions from the project root:

```sh
python3 -m unittest discover -s tests -p 'test_foreign.py' -v
python3 -m unittest discover -s tests -p 'test_pfic.py' -v
```

Tests cover all supported filing-status/residence thresholds, exact equality and
fractional crossings (including recurring-FX aggregates), mandatory same-valuation
confirmation, separate inclusion flags, noncontemporaneous maxima,
brokerage double counting, FX direction/provenance, limited-loss basis, holding-
specific inclusion limits, mandatory eligibility, strict numeric and boolean
inputs, duplicate IDs, and unknown/missing nested fields. Module tests supply
the engine's precision-60 context explicitly.
