# Security Notes

Security controls implemented:

- Custom user model and role foundation.
- Tenant-scoped models, managers, forms, services, dashboards, and API.
- DNS TXT domain ownership verification.
- Razorpay webhook signature verification and idempotency.
- HTML sanitization for rich content.
- File extension and size validation.
- Tenant-aware cache key helper.
- Production security settings via environment variables.

Do not log passwords, secret keys, tokens, Razorpay secrets, or sensitive payment data.
