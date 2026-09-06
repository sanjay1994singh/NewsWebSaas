# Press Nexa Google Analytics

The supplied GA4 measurement ID is `G-7839WK8E1T`. The shared HTML head includes the Google tag once on public Press Nexa pages. The existing database visitor report continues separately; this change does not import Google reports into the admin dashboard.

## Configuration

- `GOOGLE_ANALYTICS_MEASUREMENT_ID=G-7839WK8E1T`
- `GOOGLE_ANALYTICS_ENABLED=True`
- `SITE_BASE_URL=https://pressnexa.live-app.in` must match the production platform hostname.

These defaults already configure the supplied property. Set the ID to empty or ENABLED to False to disable. No database migration is needed for this integration. Restart the app after changing environment settings.

The tag loads on public home, pricing, signup/login, contact/about and policy pages. It is excluded from tenant sites, previews on other hosts, admin/dashboard, checkout/billing and non-GET responses. Do Not Track and Global Privacy Control prevent loading. A JavaScript guard also prevents a second initialization and respects browser-side privacy signals.

The Google configuration strips page query strings and sends only the referrer origin. Google signals and ad personalization are disabled. No account identifiers or enquiry contents are explicitly sent. Campaign parameters such as UTM queries are not forwarded by this integration. Google Analytics can still collect its standard browser/device/network metadata and enabled enhanced-measurement events; review those settings in the property when choosing what to measure.

## Verify after deployment

1. Deploy the updated code and restart the application. Collect static files through the normal deployment process if needed; the tag itself is inline.
2. Open the production public home page, with an ordinary browser and no analytics blocker or tracking opt-out. Localhost intentionally does not send to the live property.
3. In the browser Network panel check for `gtag/js?id=G-7839WK8E1T` and Analytics collection requests. Check that the loader occurs once in the page head.
4. In the existing Google Analytics setup screen choose **Test installation**, then check the property's **Realtime** report.

The repository integration does not publish the website or verify receipt inside the Google account. Browser blockers and privacy choices can prevent reporting; Google totals will not necessarily equal the server-side visitor report.

## Tests

`python manage.py test analytics accounts --noinput`

Tests cover public/private routes, platform/tenant/development hosts, ID validation, opt-out/disable settings, single shared-head inclusion and query-data exclusion.

Google references:
- https://developers.google.com/analytics/devguides/collection/ga4/reference/config
- https://developers.google.com/tag-platform/security/guides/privacy
