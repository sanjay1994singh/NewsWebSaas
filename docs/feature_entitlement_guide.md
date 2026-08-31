# Feature Entitlement Guide

Feature access is centralized in `subscriptions.entitlements`.

Use:

```python
tenant_has_feature(tenant, "epaper")
tenant_feature_limit(tenant, "news_articles")
get_effective_entitlements(tenant)
```

Precedence:

1. Tenant feature override
2. Purchased add-on
3. Plan feature
4. Default deny

Disabled features must be blocked in views, APIs, forms, admin actions, imports, and background jobs.
