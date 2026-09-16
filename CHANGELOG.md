# Changelog

## 0.1.0 - 2026-09-15

Educational alpha for **tax year 2025**, not a filing product or tax advice.

### Core

- Deterministic, offline Python library with strict decimal-string input,
  isolated arithmetic context, source manifests, formulas, versioned official
  rule locators, retained inputs, and canonical SHA-256.
- Explicit RSU/NSO/ISO/ESPP lot and sale worksheets, basis corrections,
  disposition compensation, holding periods, and bounded ISO AMT adjustments.
- Isolated wash-sale worksheets with partial matching and IRA loss denial.
- USD/INR foreign-asset threshold screening with exact rational comparisons.
- Narrow section 1296 PFIC annual mark-to-market calculations.
- Four verified official numerical examples from IRS Publications 525 and 550,
  with adapted dates and derived expectations separately labeled.

Interface integration and release verification are in progress. See the
[build note](docs/releases/0.1.0.md) for final scope and review findings.
