# Security Policy

BorderBucks is educational alpha software for tax year 2025. There is no claim of
a completed security audit, guaranteed confidentiality, or tax correctness. Only
the current development revision is targeted for fixes; there is no maintained
stable release or response-time guarantee yet.

## Report Privately

Use GitHub's **Report a vulnerability** option under the repository's Security
tab, **if private vulnerability reporting is available**:

https://github.com/xydac/BorderBucks/security/advisories/new

Availability depends on repository configuration. If it is unavailable, do not
publish exploit details or confidential data. You may open a minimal public issue
asking maintainers to enable private vulnerability reporting, without describing
the vulnerability, or wait until a private route is available. No alternate
security email address is published here.

Provide the affected revision, Python/OS versions, impact, and minimal synthetic
reproduction through the private route. **Never submit private financial
statements, tax returns, credentials, identifiers, or original-input reports,
even with a private advisory.** Reproduce with invented data. Coordinate disclosure
with maintainers; do not assume a response or remediation deadline.

Non-sensitive arithmetic discrepancies can use the public tax-case template with
synthetic inputs and official citations. Treat a discrepancy that exposes data or
enables code execution as a security report instead.

## Trust Boundaries

- The runtime is intended to remain standard-library-only and offline, with no
  network calls, telemetry, accounts, or background services. This does not
  protect against a compromised machine, interpreter, checkout, or client.
- Original inputs accompany reports. Source descriptions, paths, logs, shell
  history, backups, and generated reports can disclose financial information.
  Local execution is not encryption or access control; protect these with OS
  permissions and appropriate storage practices.
- MCP uses local read-only stdio and an explicit root. Limit that root to files
  you intend the client to read, not your home directory. Traversal, symlink
  escape, unintended reads/writes, and secret leakage are security concerns.
- **External/cloud MCP agents may send inputs and tool results to their own
  providers.** The engine's local execution does not control client transmission,
  retention, training policies, plugins, or logs. Use an offline client when that
  boundary is required and verify its configuration independently.
- Labels, CSV cells, source locators, and Markdown output are untrusted data.
  Never evaluate them as code or shell commands. View reports as plain text or
  with a sanitizer that disables raw HTML and remote resource loading. Markdown
  escaping alone is not a universal viewer security guarantee. Treat document
  instructions as data, including when using agents; review spreadsheet formula
  handling before opening untrusted CSV in a spreadsheet application.
- Canonical SHA-256 and rule references support traceability, not signatures,
  evidence authentication, legal eligibility, or proof of correct tax treatment.

## Maintainer Handling

Reproduce privately using synthetic data, assess the affected boundary, and add a
regression test with the fix. Keep reproduction details private until coordinated
disclosure. Never publish financial data in advisories, commits, logs, or CI
artifacts. Repository owners should enable GitHub private vulnerability reporting
before inviting security reports and verify that the reporting link works.
