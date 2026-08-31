# Commercial Plan Management Guide

Use Django Admin to manage `Plan`, `PlanPrice`, `Feature`, and `PlanFeature`.

Rules:

- Do not hardcode access by plan name.
- Add or remove a capability through `PlanFeature`.
- Change billing price through `PlanPrice` and Razorpay mappings, not through feature edits.
- Use a new plan version when a change should apply only to future subscribers.

Seed initial data:

```bash
python manage.py seed_commercial_plans
```
