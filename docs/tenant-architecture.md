# Tenant Architecture

Tenant resolution starts from the normalized request host and resolves `TenantDomain`, then attaches `request.tenant`. Mobile/API clients may use the immutable public tenant UUID, but host and UUID mismatches are rejected.

Tenant access is enforced through:

- `TenantAwareManager.for_tenant()`
- `TenantScopedFormMixin`
- `TenantScopedViewMixin`
- `user_can_access_tenant()`
- explicit service-level validation for incoming object IDs
