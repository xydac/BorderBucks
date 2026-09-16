# Provenance and Numeric Reproducibility

BorderBucks produces educational 2025 worksheets, not filing-ready returns,
professional advice, or a final tax liability. Provenance makes a calculation
inspectable. It does not certify that a statement, user assertion, classification,
election, or legal conclusion is correct.

## Public Pipeline

Use `borderbucks.engine.loads` to decode JSON and `borderbucks.engine.calculate`
to validate and calculate a document. Calling a calculator module directly bypasses
the public engine's shared input bounds, source-reference checks, fixed Decimal
context, output validation, and report envelope.

The public engine accepts schema version `"1"` and integer tax year `2025` only.
It validates the source manifest and recursively checks every `source_ids` list,
including records that do not contribute to arithmetic. Unknown fields, duplicate
manifest IDs, unresolved references, malformed inputs, and unsupported scope must
fail with `TaxInputError`, rather than return a partial worksheet. An unused but
valid manifest entry is allowed; its presence is still part of the input hash.

`loads` rejects duplicate JSON keys, including escaped spellings of the same key,
and non-JSON constants such as `NaN` and `Infinity`. It limits raw input to 2 MiB,
measured in UTF-8 bytes for text or actual bytes for byte input. Parsing alone is
not financial validation: a JSON number can parse successfully but is not an
acceptable financial amount. `calculate` separately bounds canonical input to
2 MiB. Both entry points enforce a maximum nesting depth of 30, counting from the
root at zero. Do not treat `loads` alone as a financial schema validator.

## Input Hash

The report includes `inputs`, a detached JSON copy of the supplied document, and
`input_sha256`, the lowercase hexadecimal SHA-256 of that document serialized as:

```python
encoded = json.dumps(
    document,
    sort_keys=True,
    separators=(",", ":"),
    ensure_ascii=True,
    allow_nan=False,
).encode("ascii")
input_sha256 = hashlib.sha256(encoded).hexdigest()
```

This is the engine's Python JSON canonicalization convention, not a claim of
compliance with an external canonical JSON standard. Object insertion order and
original JSON whitespace do not affect the digest. Array order does affect it,
including source-manifest and `source_ids` array order. Numeric strings are not
normalized in the input: `"1500"` and `"1500.00"` hash differently even when their
arithmetic results agree. Unicode is ASCII-escaped; Unicode normalization is not
performed. Original JSON formatting and escape spellings are not retained.

The digest covers all document fields, source descriptions, locators, scope
assertions, and unused manifest entries. It does **not** hash the contents of
external documents identified by those entries, the calculated report, bundled
rule text, or executable engine code. Preserve `engine_version`, `rules`, and the
report alongside the input digest when comparing results across releases.

A matching digest establishes equality of canonicalized input content, not
authenticity, authorship, completeness, a trusted timestamp, or integrity against
someone able to replace both the input and its digest. It is not a digital
signature. It is not anonymization: reports retain the full input, and hashes of
guessable inputs are not a privacy boundary.

## Sources and Rules

Each manifest entry has an `id`, `document`, and `locator`. Input records explicitly
name their evidence with `source_ids`. The engine checks references, not the
truthfulness of that evidence. It does not open the named document, fetch a URL,
verify a supplied FX rate, infer citations from filenames, or infer tax eligibility
from a descriptive label. A source called "IRS" is not thereby authenticated.

Every fact has a unique `id`, decimal-string `value`, `unit`, `formula`, `inputs`
(operands), nonempty `source_ids`, and nonempty `rule_ids`. The source IDs resolve
against the included input manifest. Rule IDs resolve against the bundled registry
and include the applicable year, for example `equity.basis.2025`. The report
includes exactly the used rules, with title, URL, locator, authority, revision,
and any `additional_urls`. A rule's applicable year need not equal its publication
date: `wash.ira.2025` cites Revenue Ruling 2008-5 as applicable to 2025.

Source propagation follows dependencies, not simply all manifest entries. Equity
sale facts include lot and sale evidence; remaining-share facts accumulate prior
sale evidence. Foreign conversions include asset and FX evidence, while totals
also include inventory assertions and exclude assets not included in that regime.
PFIC facts retain their holding's evidence. Wash facts conservatively include the
scope review, sale, and all supplied replacement evidence because matching depends
on the reviewed inventory and acquisition order. These links do not claim that
every source independently proves every operand or that a cited rule endorses a
user assertion.

`explain(document, fact_id)` recalculates through the public pipeline and returns
the complete fact, the exact referenced manifest entries, full referenced rule
records, warnings, disclaimer, and input digest. Unknown fact IDs fail. Formulas
are explanatory text, not executable tax law; operands may also include dates,
booleans, nested matching data, or exact rational strings. Consumers should respect
each fact's `unit`; boolean facts use `"0"` and `"1"`, not dollar amounts.

## Numeric Precision

Financial input values must be decimal strings, with at most 18 integer digits
and 12 fractional digits. JSON floats, integers in financial fields, exponent
notation, `NaN`, and infinities are rejected. Fields separately enforce positivity
or nonnegativity as appropriate. Schema year and acquisition-order fields are
integers; scope confirmations are literal JSON booleans, not numeric substitutes.

The public engine runs arithmetic in a fresh Decimal context with precision 60
and `ROUND_HALF_EVEN`. Caller precision, rounding, exponent limits, traps, and
sticky flags do not control the calculation and must remain unchanged. Fact
values are formatted without exponent notation and with trailing fractional zeros
removed. That formatting does not change the preserved input spellings.

Precision 60 is an arithmetic/presentation policy, not a claim that every output
is an exact finite decimal or that source measurements have 60 significant digits.
Recurring quotients require a finite presentation. There is no final tax rounding
to cents or whole dollars and no computed final tax liability. Do not use these
worksheets as already rounded entries for a tax return.

### Foreign Assets

Foreign conversions divide local amounts by the explicitly supplied yearend
`local_per_usd` rate. The engine uses exact rational arithmetic for aggregation
and threshold comparisons, not sums of displayed recurring Decimal quotients.
Aggregate operands map asset conversion fact IDs to reduced
`"numerator/denominator"` strings; conversion facts retain the original numeric
local-value and rate operands. Thus eighteen synthetic INR 50,000 accounts at
90 INR/USD total exactly USD 10,000 even though each displayed quotient recurs.
This is a synthetic regression example, not an official worked example or rate.

Thresholds use strict greater-than comparisons. The sum of annual individual
maxima is an upper bound, not necessarily a contemporaneous balance. A maximum-only
crossing calls for review; a yearend crossing establishes an arithmetic threshold,
not filing eligibility. Complete inventory, classifications, qualifying-abroad
status, and identical valuation treatment for both regimes remain user assertions.

### Wash Allocations

For a cumulative matched quantity, `floor40(x)` means
`floor(x * 10**40) / 10**40`. The engine computes the exact rational cumulative
disallowed loss, floors it to 40 decimal places, then subtracts the prior cumulative
allocation to determine each replacement's allocation. It does not independently
round each lot's exact fraction. The differences telescope, preserving the final
residual when all sold shares are matched.

Each replacement retains its exact loss numerator and denominator, also recorded
in its allocation fact's operands. A synthetic USD 1 loss split across three equal
matches therefore has two allocations ending in repeating 3s at 40 places and a
final residual ending in 4; the allocations sum to exactly USD 1. These are not
filing-rounded amounts. Taxable matches defer loss through basis; IRA matches deny
loss permanently without increasing IRA basis. Holding-period carry applies only
to matched taxable shares and does not rewrite acquisition dates.

## Hypothetical Scenarios

`scenario(document, sale_id, proceeds, date=None)` first validates the baseline,
then replaces proceeds and optionally the date of one existing equity sale in a
detached copy. It does not add a trade or modify the caller's document. The modified
sale gains an explicit hypothetical source, normally `scenario-assumption`; name
collisions add `-new` suffixes rather than overwrite existing evidence.

The returned report hashes the modified input and includes
`scenario.baseline_input_sha256`, the targeted `sale_id`, and `hypothetical: true`.
Even an unchanged proceeds override changes the digest because the added assumption
changes provenance. Dependent facts carry that source; unrelated sale facts do not.
The baseline remains reproducible. Invalid overrides, missing sales, non-equity
documents, and invalid baselines fail rather than yield a partial scenario.

## Fixtures and Privacy

`fixtures/official/*.json` separates `official_expected_facts` from
`derived_expected_facts`. Its provenance records identify the official locator,
quoted example, date adaptations, and synthetic schema assumptions. Derived AMT
basis, assigned calendar dates, holding-period days, zero fees, and eligibility
assertions must not be relabeled as IRS-stated facts. Documents in `examples/` and
mutations used for boundary regressions are synthetic, not additional IRS examples.

`tests/test_engine.py` exercises these fixtures through public loading, calculation,
and explanation, and tests reproducibility, source resolution, fail-closed scope,
and numeric presentation. Calculator-specific suites cover additional legal-scope
boundaries. Tests document software behavior, not legal certification.

Keep private statements and generated reports out of commits, public issue reports,
and test fixtures. Invalid-input tests use synthetic markers only. Error messages
should not disclose raw financial content; do not assume every diagnostic is safe
to publish. Duplicate-key diagnostics omit the user-controlled key name, which
can itself contain sensitive text. CLI schema diagnostics may still contain
identifiers or field names; review them before sharing. MCP tool failures are
generic and do not expose exception details.
