# Security

Hospital EMR handles hospital information. Treat this repository as source code, not as a place to store secrets or clinical records.

## Do not commit

- Passwords, API keys, access tokens, private keys, certificates, or session cookies
- Populated `.env` files (use the `*.example` templates)
- Real patient data, clinical notes, results, invoices, or database dumps
- Backups, SQLite audit copies, or exported OpenMRS / OpenELIS / Odoo data

Credentials belong in local environment files (mode `0600`) or the deployment secret mechanism. They must never be added under a `VITE_*` name (those values are embedded in the browser bundle).

## Development and test data

Use synthetic development records only. Do not copy live hospital charts into the repository.

## Reporting

If you find a committed secret or real patient information, do not open a public issue with the value. Rotate the credential, remove it from the working tree, and tell the repository maintainers. History rewriting is a separate, coordinated task — do not rewrite Git history without that review.
