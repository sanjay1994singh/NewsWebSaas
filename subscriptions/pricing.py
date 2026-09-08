from dataclasses import dataclass

from .models import PlanPrice
from gst.services import configuration, tax_amount as calculate_tax


OFFER_DISCOUNT_PERCENT = 50
ALLOWED_BILLING_MONTHS = (1, 12, 24)


@dataclass(frozen=True)
class CheckoutPricing:
    billing_months: int
    list_amount: int
    discount_percent: int
    discount_amount: int
    taxable_amount: int
    tax_rate_percent: int
    tax_amount: int
    payable_amount: int
    currency: str

    @property
    def billing_label(self):
        if self.billing_months == 1:
            return "1 month"
        return f"{self.billing_months} months"


def normalize_billing_months(value):
    try:
        months = int(value)
    except (TypeError, ValueError):
        return 1
    return months if months in ALLOWED_BILLING_MONTHS else 1


def monthly_price_for_plan(plan):
    return (
        plan.prices.filter(billing_cycle=PlanPrice.BillingCycle.MONTHLY, is_active=True).first()
        or plan.prices.filter(is_active=True).order_by("id").first()
    )


def calculate_checkout_pricing(plan_price, billing_months=1, discount_percent=OFFER_DISCOUNT_PERCENT):
    months = normalize_billing_months(billing_months)
    if plan_price.billing_cycle == PlanPrice.BillingCycle.YEARLY and months == 12:
        list_amount = plan_price.amount
    elif plan_price.billing_cycle == PlanPrice.BillingCycle.YEARLY and months == 24:
        list_amount = plan_price.amount * 2
    else:
        list_amount = plan_price.amount * months
    discount_amount = round(list_amount * discount_percent / 100)
    taxable_amount = max(list_amount - discount_amount, 0)
    rate = configuration().rate_percent
    tax_amount = calculate_tax(taxable_amount, rate)
    payable_amount = taxable_amount + tax_amount
    return CheckoutPricing(
        billing_months=months,
        list_amount=list_amount,
        discount_percent=discount_percent,
        discount_amount=discount_amount,
        taxable_amount=taxable_amount,
        tax_rate_percent=rate,
        tax_amount=tax_amount,
        payable_amount=payable_amount,
        currency=plan_price.currency,
    )


def money_display(amount, currency="INR"):
    value = int(amount or 0) / 100
    value_text = f"{value:,.0f}" if value.is_integer() else f"{value:,.2f}"
    currency_text = "₹" if currency == "INR" else currency
    return f"{currency_text} {value_text}"
