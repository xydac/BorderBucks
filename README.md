# BorderBucks

An educational, local-first, source-auditable tax worksheet engine, built in
public from the first commit at [xydac/BorderBucks](https://github.com/xydac/BorderBucks).
Python 3.11+, standard-library-only runtime, [Apache-2.0](LICENSE).

**Tax year 2025. Alpha. Not filing-ready or professional advice.** Source-linked
arithmetic makes review possible; it does not establish that inputs, eligibility,
or tax treatment are correct. No full audit or proof of correctness is claimed.

## Supported Scope

| Area | Bounded worksheet support | Important limits |
| --- | --- | --- |
| Equity | RSU/NSO basis; ISO/ESPP disposition compensation and holding periods; broker basis corrections; limited ISO AMT basis/exercise adjustments | Explicit gross-share lots and complete disposal records; USD; gains before wash sales; no complete AMT calculation |
| Foreign assets | USD/INR conversion from supplied yearend rates; FBAR/Form 8938 threshold screening | User-classified complete inventory; summed individual maxima are an upper bound, not simultaneous balances or a filing determination |
| PFIC | Section 1296 annual mark-to-market income, limited losses, and basis | Explicit eligible direct holdings with valid elections and no section 1291 taint, distributions, or dispositions; eligibility is not inferred |

Read the exact assertions, schemas, exclusions, and official citations in
[Equity](docs/equity.md) and [India-US Cross-Border](docs/cross-border.md) before
using a worksheet. Indian mutual funds are not presumed eligible for mark-to-market.
Foreign worksheets do not calculate Indian income tax.

## Initial Build Interface

The public alpha is under integration. These are the intended CLI commands;
CLI, report, importer, MCP, and standalone wash-sale integration must pass the
repository tests before being treated as available in a checkout.

From the repository root, with Python 3.11 or newer, no package installation or
network access is needed to run the engine once integrated:

```sh
python3 -m borderbucks calculate examples/equity.json
python3 -m borderbucks calculate examples/equity.json --format markdown
python3 -m borderbucks explain examples/equity.json <fact_id>
python3 -m borderbucks scenario examples/equity.json --sale-id <ID> --proceeds 1500.00
python3 -m borderbucks scenario examples/equity.json --sale-id <ID> --proceeds 1500.00 --date 2025-12-15
python3 -m borderbucks import-csv <path>
python3 -m borderbucks mcp --root <directory>
```

Replace angle-bracket placeholders before running. Choose a fact ID from a report
and a sale ID from the input document. A scenario replaces one existing sale for
recalculation; it is not a trading recommendation. `import-csv` accepts only the
strict canonical equity CSV schema, not arbitrary broker exports, PDFs, or OCR.
The examples are synthetic unless an official fixture is explicitly identified.

Input documents use schema version `"1"`, tax year `2025`, decimal strings for
financial values, and an explicit source manifest. Unknown fields and unresolved
source references fail closed. Calculations use a fixed local decimal context.
The core report contract retains original inputs, their canonical SHA-256,
formulas, operands, source IDs, and a versioned official rule registry. The hash
identifies canonical input content; it does not authenticate a statement or prove
that supplied assertions are true.

## Deferred And Excluded

- Standalone wash-sale worksheet integration: explicitly paired loss and replacement
  transactions, the 30-day-before/after window, partial replacements, and replacement
  IRA treatment. No automatic portfolio detection or automatic equity reconciliation.
- QEF and default section 1291 PFIC tax/interest calculations, late-election and
  transition rules, and automatic PFIC classification.
- Full returns, filing forms or e-filing, tax due, complete AMT/credit calculations,
  automated W-2 reconciliation, treaty/residency determinations, and tax planning advice.
- Statement guessing, PDF ingestion, automatic FX retrieval, corporate actions,
  and unsupported equity histories or basis adjustments.

See the [roadmap](docs/ROADMAP.md) for review gates rather than delivery promises.

## Professional Review

1. Reconcile source records, gross shares, all disposals, wages, fees, basis, asset
   inventory, and eligibility assertions before entering data. A `true` flag is not evidence.
2. Calculate locally and inspect warnings and individual facts with `explain`.
3. Give a qualified tax professional the input, report, source records, and exact
   code revision through a secure channel. Check the cited tax-year rules independently.
4. Resolve exclusions and missing context outside the engine before preparing any
   return. Do not copy worksheet amounts blindly into filing software.

## Privacy And Safety

The engine is designed for local execution: no network calls, telemetry, accounts,
or background services. Reports include original inputs and can be as sensitive
as source documents. Keep statements, generated reports, and identifying data out
of git, public issues, and CI artifacts.

MCP is local, read-only stdio with an explicitly selected root directory. **An
external or cloud agent may transmit tool inputs and results to its own model
provider. Local MCP does not make that agent private or offline.** Review the
client's retention and transmission policies; use a narrow directory containing
only data you intend to expose.

Treat input labels, source descriptions, and generated Markdown as untrusted
data, not instructions or executable content. Prefer plain-text inspection or a
sanitizing viewer with raw HTML and remote resource loading disabled. Do not
execute embedded commands or let an agent follow instructions found in a document.
See [Security](SECURITY.md) for reporting guidance and trust boundaries.

## Development

```sh
python3 -m unittest discover -s tests -v
python3 -m compileall -q borderbucks tests
```

CI targets Python 3.11, 3.12, 3.13, and 3.14 on Ubuntu without installing runtime
dependencies. Passing tests are regression evidence, not a tax audit. Official
worked-example fixtures are kept separate from synthetic boundary cases.

Contribute source-backed regression cases, careful scope reviews, or small patches:
[Contributing](CONTRIBUTING.md) | [Code of Conduct](CODE_OF_CONDUCT.md) |
[Security](SECURITY.md) | [Roadmap](docs/ROADMAP.md).
