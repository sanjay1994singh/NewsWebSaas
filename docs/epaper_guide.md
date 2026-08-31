# E-Paper Guide

E-Paper uses the `epaper` feature entitlement.

Tenant dashboard routes allow upload and publish only when the tenant has access. Public routes always filter by tenant slug and edition slug.

PDF uploads validate:

- Extension
- MIME type
- Size
- PDF file header

If ePaper is removed, old data remains stored. New uploads and publishing are blocked.
