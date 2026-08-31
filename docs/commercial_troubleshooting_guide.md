# Commercial Troubleshooting Guide

Common checks:

- Missing feature: confirm `Feature.is_active` and `PlanFeature.is_enabled`.
- One tenant needs special access: create `TenantFeatureOverride`.
- Add-on not working: confirm `TenantAddOn.status=active` and provider reference.
- Tenant not created: confirm acquisition status and verified provider subscription ID.
- Site not public: confirm onboarding review status and explicit publish action.
- E-Paper blocked: confirm `tenant_has_feature(tenant, "epaper")`.
