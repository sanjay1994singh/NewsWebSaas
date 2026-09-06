import hmac
import json
from hashlib import sha256
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from .models import WebhookEvent


@override_settings(RAZORPAY_WEBHOOK_SECRET='delivery-test-secret', RAZORPAY_ENVIRONMENT='test')
class RazorpayDeliveryTests(TestCase):
    def deliver(self, *, event_id='evt_delivery', signature=None):
        body = json.dumps({'entity': 'event', 'event': 'payment.captured',
                           'payload': {'payment': {'entity': {'id': 'pay_example'}}}}).encode()
        return self.client.post(
            reverse('subscriptions:razorpay_webhook'), data=body,
            content_type='application/json', HTTP_X_RAZORPAY_EVENT_ID=event_id,
            HTTP_X_RAZORPAY_SIGNATURE=signature or hmac.new(
                b'delivery-test-secret', body, sha256).hexdigest(),
        )

    @patch('subscriptions.services._sync_payment_from_webhook')
    def test_real_header_delivery_and_retry_process_once(self, sync):
        for _ in range(2):
            response = self.deliver()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['event_id'], 'evt_delivery')
            self.assertTrue(response.json()['processed'])
        self.assertEqual(WebhookEvent.objects.count(), 1)
        sync.assert_called_once()

    def test_invalid_signature_is_rejected(self):
        self.assertEqual(self.deliver(signature='invalid').status_code, 400)
        self.assertFalse(WebhookEvent.objects.exists())

    def test_missing_event_id_is_rejected(self):
        self.assertEqual(self.deliver(event_id='').status_code, 400)
        self.assertFalse(WebhookEvent.objects.exists())
