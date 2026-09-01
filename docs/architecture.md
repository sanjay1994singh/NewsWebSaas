# Architecture

Press Nexa is one Django codebase serving many independent news tenants from a shared database. Tenant-owned data carries an explicit tenant foreign key and uses tenant-aware managers, forms, services, views, and API resolution.

Core modules:

- `accounts`: custom user and platform roles.
- `tenants`: tenant lifecycle and memberships.
- `domains`: domain validation, verification, tenant resolution.
- `news`, `categories`, `media_library`, `pages`: CMS.
- `themes`: branding and theme activation.
- `subscriptions`: plans, entitlements, Razorpay billing.
- `analytics`: privacy-conscious tenant/platform metrics.
- `api`: `/api/v1/` public app endpoints.
