# Press Nexa WhatsApp Templates

Use these approved WhatsApp Business templates with Fast2SMS WhatsApp API. Keep the template names exactly as configured in `.env`, or update the `.env` names to match the approved templates.

## Environment Variables

```text
WHATSAPP_PROVIDER=fast2sms
WHATSAPP_NOTIFICATIONS_ENABLED=false
WHATSAPP_FAST2SMS_API_KEY=
WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_FAST2SMS_VERSION=v26.0
WHATSAPP_TEMPLATE_LANGUAGE=hi
WHATSAPP_PAYMENT_SUCCESS_TEMPLATE=pressnexa_payment_success
WHATSAPP_PAYMENT_FAILED_TEMPLATE=pressnexa_payment_failed
WHATSAPP_PAYMENT_SUCCESS_MESSAGE_ID=31349
WHATSAPP_PAYMENT_FAILED_MESSAGE_ID=
```

Fast2SMS sends template messages through:

```text
POST https://www.fast2sms.com/dev/whatsapp/{version}/{phone_number_id}/messages
Authorization: YOUR_FAST2SMS_API_KEY
```

If the Fast2SMS dashboard shows numeric Message IDs for the approved templates, set `WHATSAPP_PAYMENT_SUCCESS_MESSAGE_ID` and `WHATSAPP_PAYMENT_FAILED_MESSAGE_ID`. The app will then use the simple Fast2SMS template API:

```text
GET https://www.fast2sms.com/dev/whatsapp?message_id=...&phone_number_id=...&numbers=...&variables_values=...
Authorization: YOUR_FAST2SMS_API_KEY
```

For invoice PDF/session documents, the app supports this Fast2SMS endpoint:

```text
POST https://www.fast2sms.com/dev/whatsapp-session?phone_number_id=...&to=...&type=document&url=...&document_filename=invoice.pdf
Authorization: YOUR_FAST2SMS_API_KEY
```

## Template: pressnexa_payment_success

Category: Utility

Approved Hindi Body:

```text
नमस्ते {{1}},

आपका Press Nexa भुगतान सफलतापूर्वक प्राप्त हो गया है।

ब्रांड नाम: {{2}}
वर्कस्पेस: {{3}}
प्लान: {{4}}
अवधि: {{5}}
प्लान राशि: {{6}}
डिस्काउंट: {{7}}
डिस्काउंट राशि: {{8}}
भुगतान राशि: {{9}}
पेमेंट आईडी: {{10}}
```

Variables:

```text
{{1}} Account/customer name
{{2}} Tenant brand/channel name
{{3}} Tenant public website URL
{{4}} Plan name
{{5}} Purchase duration
{{6}} Original/list amount
{{7}} Discount percent
{{8}} Discount amount
{{9}} Final paid amount
{{10}} Razorpay payment reference
```

After this template, the app sends the paid invoice PDF as a WhatsApp document using a signed invoice URL.

## Template: pressnexa_payment_failed

Category: Utility

English Body:

```text
Payment failed for {{1}}.

Username: {{2}}
Plan: {{3}}
Amount: {{4}}
Reference: {{5}}

Retry payment: {{6}}
Update profile: {{7}}
WhatsApp support: {{8}}

If money was deducted, please share the reference with support.
```

Hindi Body:

```text
{{1}} के लिए भुगतान असफल हो गया है।

Username: {{2}}
प्लान: {{3}}
राशि: {{4}}
रेफरेंस: {{5}}

भुगतान दोबारा करें: {{6}}
प्रोफाइल अपडेट करें: {{7}}
WhatsApp support: {{8}}

अगर पैसे कट गए हैं, तो कृपया रेफरेंस सपोर्ट टीम के साथ शेयर करें।
```

Variables:

```text
{{1}} Publication name
{{2}} Username
{{3}} Plan name
{{4}} Amount with currency
{{5}} Razorpay payment/order reference
{{6}} Checkout URL
{{7}} Profile URL
{{8}} Support WhatsApp number
```
