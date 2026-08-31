# Theme, Builder, SEO, API, and Razorpay Architecture

Themes are server-rendered Django templates selected per tenant. Homepage layouts use draft and published records so draft changes do not alter the live site until publish.

SEO uses tenant primary verified domains for canonical URLs, tenant-aware robots and sitemaps, and structured data generated only from real model fields.

Razorpay integration keeps internal plan/pricing separate from provider plan IDs, verifies webhook signatures server-side, and stores processed events idempotently.

The `/api/v1/` API exposes safe public configuration and public content only, with pagination and throttling enabled.
