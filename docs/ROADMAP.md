# Roadmap

BorderBucks is a public-from-first-commit, Apache-2.0 educational tax engine.
This is a sequence of review gates, not a delivery schedule or a claim that
planned features already work. Current tax scope is 2025 alpha only.

## Documented Worksheet Baseline

- Explicit RSU/NSO/ISO/ESPP lots and sales, basis corrections, holding periods,
  and limited ISO AMT adjustments within [equity scope](equity.md).
- Foreign USD/INR valuations and conservative FBAR/Form 8938 threshold screening,
  not eligibility or filing determinations, within [cross-border scope](cross-border.md).
- Section 1296 annual PFIC mark-to-market with explicit eligibility assertions,
  holding-specific loss limits, and basis adjustments. No QEF or section 1291
  tax/interest implementation is implied by entries in a rule registry.

## Initial Integration Gates

- Complete the Python 3.11+ standard-library CLI: `calculate`, Markdown output,
  `explain`, single-sale `scenario`, strict canonical equity `import-csv`, and
  local read-only `mcp --root`. No arbitrary statement or PDF ingestion.
- Verify original-input retention, canonical SHA-256, fact formulas and operands,
  resolved source IDs, versioned official rules, strict schemas, and independence
  from ambient decimal precision through the public engine entry point.
- Integrate a standalone wash-sale worksheet for explicitly paired transactions:
  inclusive 30-day-before/after window, partial replacement matching, and replacement
  IRA loss treatment. Require official citations and boundary regressions. Do not
  claim automatic substantially-identical-security detection, portfolio scanning,
  or automatic adjustments to equity reports.
- Exercise CLI smoke tests and unittest on Python 3.11/3.12/3.13/3.14 on Ubuntu.
  Test renderer hostile text, MCP path boundaries, malformed inputs, and source
  resolution; never execute or unsafely render document text.
- Enable and verify GitHub private vulnerability reporting. Keep all examples,
  issues, fixtures, and CI output free of private financial data.

## Review Before Expansion

Invite independent tax-professional review of supported assumptions, formulas,
official citations, and exclusions, and security review of input/output and MCP
boundaries. Record findings and limitations without calling regression tests a
full audit. Keep official worked examples separate from synthetic tests and
explicitly identify adapted dates and derived expectations.

Publish schema and rule changes with reproducible regression cases. Any new tax
year needs its own verified sources and boundary tests; changing a year constant
is not sufficient. Preserve the offline, local-first runtime and make external
agent transmission risks explicit in integration documentation.

## Outside This Roadmap

Full returns, e-filing, tax liability, complete AMT and credit calculations,
automatic wage reconciliation, residency/treaty advice, Indian income-tax returns,
QEF/default section 1291 calculations, late-election coordination, PDF/OCR parsing,
automatic portfolio wash detection, and cloud accounts are not promised.

Propose scope changes through a source-backed tax case and discussion before
implementation. See [Contributing](../CONTRIBUTING.md).
