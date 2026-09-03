# Press Nexa WhatsApp Templates

Use these approved WhatsApp Business templates with Fast2SMS WhatsApp API. Keep the template names exactly as configured in `.env`, or update the `.env` names to match the approved templates.

## Environment Variables

```text
WHATSAPP_PROVIDER=fast2sms
WHATSAPP_FAST2SMS_API_KEY=
WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_FAST2SMS_VERSION=v26.0
WHATSAPP_TEMPLATE_LANGUAGE=en_US
WHATSAPP_PAYMENT_SUCCESS_TEMPLATE=pressnexa_payment_success
WHATSAPP_PAYMENT_FAILED_TEMPLATE=pressnexa_payment_failed
```

Fast2SMS sends template messages through:

```text
POST https://www.fast2sms.com/dev/whatsapp/{version}/{phone_number_id}/messages
Authorization: YOUR_FAST2SMS_API_KEY
```

## Template: pressnexa_payment_success

Category: Utility

Body:

```text
Payment successful for {{1}}.

Username: {{2}}
Plan: {{3}}
Amount paid: {{4}}
Payment ID: {{5}}
Tenant slug: {{6}}

Start onboarding: {{7}}
Update profile: {{8}}

Your Press Nexa tenant workspace is now active for onboarding.
```

Variables:

```text
{{1}} Publication name
{{2}} Username
{{3}} Plan name
{{4}} Amount with currency
{{5}} Razorpay payment reference
{{6}} Tenant slug
{{7}} Onboarding URL
{{8}} Profile URL
```

## Template: pressnexa_payment_failed

Category: Utility

Body:

```text
Payment failed for {{1}}.

Username: {{2}}
Plan: {{3}}
Amount: {{4}}
Reference: {{5}}

Retry payment: {{6}}
WhatsApp support: {{7}}

If money was deducted, please share the reference with support.
```

Variables:

```text
{{1}} Publication name
{{2}} Username
{{3}} Plan name
{{4}} Amount with currency
{{5}} Razorpay payment/order reference
{{6}} Checkout URL
{{7}} Support WhatsApp number
```
