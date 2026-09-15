# Contributing

BorderBucks is being built in public as an educational, local-first, source-auditable
tax engine. The current scope is tax year 2025 alpha worksheets, not filing-ready
software. Contributions are under [Apache-2.0](LICENSE). Follow the
[Code of Conduct](CODE_OF_CONDUCT.md).

## Start Small

Read [equity scope](docs/equity.md), [cross-border scope](docs/cross-border.md),
and the [roadmap](docs/ROADMAP.md). Open an issue before expanding tax scope or
changing document semantics. Good first contributions include clearer exclusions,
official citation corrections, and minimal synthetic regression cases.

Never upload private statements, returns, account numbers, tax identifiers, names,
or reports containing original inputs. Use invented values and identifiers. Merely
removing a name from an otherwise real statement is not sufficient. Security
vulnerabilities belong in the private route described in [SECURITY.md](SECURITY.md),
not a public bug report.

## Local Checks

Use Python 3.11 or newer from the repository root. The runtime and tests use the
standard library; no dependency installation is required.

```sh
python3 -m unittest discover -s tests -v
python3 -m compileall -q borderbucks tests
python3 -m borderbucks --help
python3 -m borderbucks calculate examples/equity.json
python3 -m borderbucks calculate examples/equity.json --format markdown
```

The CLI smoke checks are integration gates for the initial build. CI runs these
checks on Ubuntu with Python 3.11, 3.12, 3.13, and 3.14. Do not skip failing checks
to describe an unfinished interface as supported.

## Tax Changes

1. State the tax year, supported assumptions, excluded cases, and expected result.
2. Cite an official publication or statute with URL, year/version, and precise
   section, page, or example locator. Explain how the rule supports the formula.
3. Add a regression test, including relevant equality, anniversary, partial-sale,
   loss-limit, or rejection boundaries. Test invalid and out-of-scope inputs too.
4. Keep official worked examples in `fixtures/official` distinct from synthetic
   cases. Label adapted dates, derived expectations, and assumptions explicitly;
   do not attribute invented arithmetic to the IRS.
5. Update scope documentation and versioned rule references alongside code.
   Passing tests and citations do not replace independent professional review.

## Engineering Rules

- Keep the runtime standard-library-only, offline, deterministic, and free of
  telemetry, account requirements, or background services.
- Accept financial values as decimal strings. Use the engine's fixed local
  decimal context, never binary floating point or ambient precision.
- Reject unknown fields, unresolved sources, contradictory assertions, and
  unsupported cases rather than guessing missing facts.
- Preserve original inputs, canonical SHA-256, fact formulas, operands, source
  IDs, and versioned rule references in the report contract. A hash is not proof
  that source evidence is genuine.
- Treat all document text as untrusted data. Escape Markdown/HTML metacharacters
  as appropriate for the output context, including table and code-fence boundaries.
  Never evaluate formulas or labels as code, execute input commands, or render
  user HTML unsanitized. Add hostile-text regression cases for renderer changes.
- Keep MCP read-only and rooted to an explicit directory. Test traversal and
  symlink escapes, malformed requests, and data boundaries when changing it.
- Do not add private files, generated financial reports, or sensitive logs to
  commits or CI artifacts. Use only synthetic or suitable official public examples.

## Pull Requests

Describe the problem, bounded change, citations, tests run, and remaining risks.
Keep patches focused and distinguish supported behavior from planned features.
Do not claim an audit, proof of tax correctness, or full return readiness. Review
the diff for private data and accidental generated files before submitting.
