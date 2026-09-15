# Press Nexa editorial campaign

## Schedule
365 days, 8 September 2026 through 7 September 2027 inclusive.
Four total posts daily: 08:00 Hindi, 13:00 English, 17:00 Hindi, 20:00 English.
All editorial times use Asia/Kolkata. There are 1,460 calendar slots, not 1,460 completed articles.
The first four original articles are in content/pressnexa. No AI API key is needed.

The server timer checks each minute and publishes only complete ready posts whose time has arrived.
Publication stops at the end of the campaign. Reruns cannot duplicate publication.
Paused campaigns do not publish. Published articles remain accessible after campaign completion.
A missed slot may publish late when content arrives during the campaign; empty slots never go public.
The timestamp shown is the actual publication time, never a fabricated earlier date.

## Deployment
Server: root@103.168.19.9, SSH port 22.
Application: /var/www/NewsWebSaas; runtime: venv/bin/python.
Web service: newswebsaas.service; worker user: www-data.
New files are additive. Run migration before restarting the web service.

    python manage.py migrate
    python manage.py blog_campaign init --start 2026-09-08
    python manage.py seed_blog_articles
    python manage.py publish_blog --dry-run

Install deploy/pressnexa-blog.service and deploy/pressnexa-blog.timer into /etc/systemd/system.
Run systemctl daemon-reload and systemctl enable --now pressnexa-blog.timer.
Inspect systemctl status pressnexa-blog.timer and journalctl -u pressnexa-blog.service.

## Ongoing writing without an API
The Codex recurring task now runs hourly and writes up to eight empty slots per run until all 1,460 articles are complete. This follows the user request to finish the entire backlog, however long it takes. It then pauses the writing automation; the independent server publication timer remains active.
It needs the Codex host available, account usage available and working SSH access.
The independent server timer continues to publish prepared articles even while Codex is offline.
If writing misses a run, there may be a content gap; do not invent successful publication.
Keep at least the following day ready. Prefer extending the buffer when capacity allows.

    python manage.py blog_campaign pending --limit 4
    python manage.py blog_campaign import --file /path/to/articles.json
    python manage.py blog_campaign status

Import format: a JSON array of objects containing slug, title, description, content (sanitized HTML).
Use the exact pending slug. Imports are transactional and refuse to overwrite ready, held or published posts.
Read existing articles before writing to avoid repeating advice. Calendar topics are suggested briefs:
adapt the angle to add a distinct useful example, process or decision. Do not spin an existing article.
Save each authored source locally under content/pressnexa and back up the import artifact.
Copy only the import JSON to the server and run the import as www-data. Never copy .env or secrets.

## Editorial requirements
Every body must contain 900–1,200 whitespace-delimited words after HTML removal.
Hindi must be natural Devanagari; English should be independently readable.
Cover all current plans, their actual enabled features and realistic publisher needs.
Verify current plan data from the public pricing page before writing price/feature claims.
Date any price snapshot and link the current plans page. Do not imply domain registration is included.
Future features are proposals, not confirmed roadmap, availability, price or release commitments.
No invented delivery SLA, ranking promises, AdSense approval guarantees, earnings claims or customers.
Use original practical examples explicitly framed as examples; never fabricate research or testimonials.
Do not copy the reference Infowave blogs. Add real editorial value instead of keyword repetition.
Separate general best practice from a feature included in a Press Nexa subscription.
Use meaningful title, description, headings, attribution and links to verified primary sources when relevant.
No ad code has been added; policy-conscious writing does not establish AdSense approval.
Do not publish content if factual uncertainties cannot be resolved. Put the slot on hold and report why.

Official policy references consulted on 7 September 2026:
- https://support.google.com/adsense/answer/10502938
- https://developers.google.com/search/docs/essentials/spam-policies

Google Publisher Policies restrict low-value and replicated-content inventory.
Google Search spam policies address scaled content created to manipulate rankings without helping people.
Word count is this campaign's editorial requirement, not a Google approval requirement.

## Operations
/admin/publisher_blog/ provides campaign pause and article review/editing.
Changing the campaign start after seeding does not reschedule existing slots; do not change it.
Future, empty and held posts are excluded from public pages and sitemap.
/blog/, /blog/hi/, /blog/en/ are platform-only; tenant blogs remain separate.
The platform sitemap includes published blog posts. BlogPosting structured data identifies Press Nexa.
Do not add alternate-language hreflang for unrelated articles just because they share a day.

Validation: python manage.py test publisher_blog

