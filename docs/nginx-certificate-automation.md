# Nginx and Certificate Automation

Phase 4 prepares the application side of custom domains. Certificate issuance must run from infrastructure workers, not from web requests.

Recommended production architecture:

1. Tenant adds a domain in the dashboard.
2. The app generates a DNS TXT token at `_infosaas-verify.<domain>`.
3. The tenant publishes the TXT record.
4. The app verifies only the TXT record, never ownership by A-record alone.
5. A Celery task queues certificate provisioning and sets SSL status to `provisioning`.
6. The infrastructure worker renders an Nginx server block for the verified domain.
7. The infrastructure worker requests or renews the certificate using a locked-down ACME client account.
8. Nginx config is tested with `nginx -t`.
9. Nginx reload is executed by a restricted service account or deployment agent.
10. The app records SSL status as `active`, `failed`, or `renewing`.

Security rules:

- Never execute arbitrary shell commands from a Django request.
- Never use user-submitted hostnames directly in shell command strings.
- Only provision certificates for verified active domains stored in the database.
- Keep ACME credentials outside the Django database and source tree.
- Redirect secondary domains to the tenant primary domain only after both domains are verified.
- Use HSTS only after HTTPS works for all required subdomains.
