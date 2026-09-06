# Press Nexa visitors and enquiries

## Use

- Log in with a super admin or support admin account; choose **Visitors & enquiries** from the Account menu, or open `/saas-admin/visitors/`.
- The report defaults to the last 30 days. Filter dates, click a browser ID to inspect its history, and review daily page views, sources, popular pages and returning sessions.
- The public `/contact-us/` form saves name, email, optional phone, message and contact-consent timestamp. Admins can mark enquiries New, Contacted or Closed and keep internal notes.
- Login/signup events include the authenticated account. Earlier page views remain anonymous and can be connected through the same browser ID. Existing account/signup records remain the source for registration details.

## Coverage and limits

Tracking covers successful HTML GET requests on platform home, pricing, signup, login, about, contact and policy routes, plus successful login/signup redirects. Tenant domains, tenant preview sites, admin dashboards, APIs, checkout pages, errors and known bot user agents are excluded. Existing tenant article analytics is separate.

Signed, HttpOnly, SameSite=Lax first-party cookies identify a browser for up to one year and a session for 30 minutes after activity. HTTPS requests use Secure cookies. Different browsers and cleared/blocked cookies produce different identities. Returning sessions require an earlier recorded session for that browser; this is an estimate, not a count of identifiable people. Referrers may be unavailable. No IP-based location lookup is performed.

Platform visit records store path (without query string), timestamp, referrer hostname, browser/device category and optional authenticated user reference. They never store raw IP, raw user-agent, credentials or full referring URLs. Do Not Track / Global Privacy Control opt out of this tracking. Enquiries still work with tracking disabled or opted out.

Enquiry POSTs require CSRF protection, explicit contact agreement and validation; a honeypot and five attempts per minute per directly connected IP limit basic spam. The rate-limit cache key is an HMAC, not the raw address. Configure Django with a shared cache for a consistent limit across application workers. Behind a proxy, the direct IP may be the proxy; adapt trusted-proxy handling before relying on per-client rate limits at scale.

Only platform admins/support admins can see the report or change enquiry status. Ordinary accounts and tenant domains cannot access it. These models are not registered in the generic Django admin.

## Installation

Run `python manage.py migrate analytics` when deploying these changes, then restart the Django application. The migration adds platform visitor, visit and enquiry tables. Set `PLATFORM_VISITOR_TRACKING_ENABLED=False` to disable visitor tracking while retaining the enquiry form. Tracking storage failures are logged and do not break public page responses.

Visitor-specific responses are private and no-store. Configure any CDN/reverse proxy to honor these headers; a proxy serving cached pages without contacting Django cannot be counted by this middleware.

This change does not publish the application or configure a production backup/retention service. Records remain in the application database until explicitly removed. Include this database in the existing backup policy and choose a retention period appropriate for operations. No historical visitor data is reconstructed.

## Verification

`python manage.py test analytics accounts --noinput`

Tests cover repeat sessions, cookie tampering, opt-outs, bots, tenant exclusions, malformed referrers, failure isolation, login/signup linkage, enquiry validation/CSRF/throttling, report filters and authorization.

Validated locally on 2026-09-06: 19 analytics/account tests pass, Django system checks pass, and no model changes are missing migrations. Both contact and report pages render against the migrated local database. The broader tenant/subscription suite passes 90 of 92 tests; the existing about-page redirect expectation and purchase-agreement signup test also fail with the new visitor middleware removed. Logs are in `output/visitor-tests.log`, `output/visitor-regression.log` and `output/visitor-baseline.log`. Browser screenshot verification was unavailable because the browser tool could not initialize.
