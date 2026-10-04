# Secure development

## code-review — Code review
Every change to production code requires review and approval by an engineer other than its
author. Direct pushes to the main branch are blocked.

## scanning — Dependency and code scanning
Dependencies are scanned for known vulnerabilities on every build. Critical vulnerabilities
in dependencies must be fixed or mitigated within 7 days of disclosure.

## pentest — Penetration testing
An independent firm performs a penetration test of the product once a year. Customers on the
Enterprise plan can request an executive summary of the latest report under NDA.

## environments — Environments
Production, staging and development environments are separated. Customer data is never copied
into staging or development environments.
