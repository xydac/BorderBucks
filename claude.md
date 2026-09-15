# Project Learnings

- BorderBucks is a Python 3.11+ standard-library-only runtime, Apache-2.0.
- Start with `python3 -m borderbucks`; test with `python3 -m unittest discover -s tests -v`.
- All financial input numbers are decimal strings. Core calculations run inside a fixed local decimal context, never ambient process precision.
- Documents use schema_version `1`, tax_year `2025`, a kind, and a source manifest. Unknown fields and unresolved source references must fail closed.
- Facts carry formulas, operands, source IDs, and versioned official rule references. Raw inputs and their canonical SHA-256 accompany reports.
- No network calls, telemetry, accounts, background services, or automatic statement guessing. MCP is local stdio, read-only, rooted to an explicitly selected directory.
- Tax worksheets are educational alpha software, never filing-ready or professional advice. Do not widen tax scope without official citations and regression cases.
- Keep official worked-example fixtures distinct from synthetic boundary/regression fixtures. Never describe synthetic arithmetic as an IRS example.
- Do not commit private financial statements. Examples must be synthetic or from official public sources.
