# Database and Model Overview

Every business object that belongs to a customer includes `tenant`.

Important constraints:

- Category, article, tag, author, page, video, Live TV, and gallery slugs are unique per tenant.
- Domains are globally unique.
- One active membership per tenant/user pair.
- Webhook events are idempotent per provider, environment, and event ID.

Indexes are added around tenant/status/date and tenant/content lookup paths used by dashboards, APIs, and sitemaps.
