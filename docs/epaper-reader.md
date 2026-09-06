# Fast public E-Paper reader

Visitors open /epaper/ on the publication domain and see the latest published edition directly. City, edition and date filters are server-side; /epaper/<slug>/?page=N is a permanent edition/page link. Tenant entitlements and published status are checked on every reader request. Existing /p/<tenant>/epaper/ links remain supported.

## Deployment

1. Install requirements, including PyMuPDF.
2. Run `python manage.py migrate`.
3. Run `python manage.py collectstatic --noinput` (the reader uses versioned manifest assets).
4. Run `python manage.py prepare_epapers` once to prepare existing editions. Published editions keep their published status. Inspect errors; `--retry-failed` retries failed uploads after the source issue is resolved.
5. Keep `python manage.py prepare_epapers --watch` running as a separate supervised service under the same application environment/user. It polls the database every five seconds and processes new uploads; no Redis broker is needed. Restart on failure. Do not run it inside Gunicorn or a web request. On Linux, use systemd with the application WorkingDirectory, virtualenv Python in ExecStart, EnvironmentFile and Restart=always. On Windows, run it with the existing application service manager.
6. Worker and web processes must share the same media storage. Serve /media/epaper/pages/ directly through the media server/CDN with `Cache-Control: public, max-age=31536000, immutable`. Paths contain a generation UUID so replacements never reuse cache keys. If media is on a separate origin, allow the publication origins with CORS so clipping can use canvas. Do not apply these cache rules to reader HTML or entitlement responses.

Uploads stay Processing until the worker has saved a complete page set. Conversion failures mark the edition Failed rather than publishing partial pages. Publish requires Ready plus generated pages. The worker is required; without it new uploads will stay Processing.

## Loading strategy

- Pre-render four WebP variants: 240px thumbnails, 1000px mobile, 1800px normal and up to 3000px zoom (4500px height cap).
- First page is in the server HTML with responsive srcset and high fetch priority.
- Only the next normal/mobile page is prefetched, and not when Save-Data/2G is reported.
- Thumbnails are created only when All pages opens, with lazy loading.
- Zoom detail loads only when requested. Keep no more than five decoded image promises in the JS cache.
- Bookmark keys include tenant and edition; share links include the selected page.
- Clip/download actions respect allow_download. Images inherently remain viewable by public readers.

Do not promise an absolute opening time without measuring the production origin/CDN, real editions and mobile networks. Check LCP, first-page bytes and next-page latency using a cold browser cache and throttled 4G. Higher-detail tiles and text/OCR search can be future improvements for very large pages; the current reader uses whole-page images, not a text layer.
