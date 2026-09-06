"""New-account welcome mail, dispatched after the signup transaction commits."""
import logging
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from .models import CustomerAcquisition
from .pricing import money_display

logger = logging.getLogger(__name__)


def send_signup_welcome(acquisition_id):
    try:
        acquisition = CustomerAcquisition.objects.select_related('user', 'plan_price__plan').get(pk=acquisition_id)
        if not acquisition.email:
            return False
        base = settings.SITE_BASE_URL.rstrip('/')
        context = {
            'acquisition': acquisition,
            'username': acquisition.user.username,
            'plan_name': acquisition.plan_price.plan.name,
            'amount': money_display(acquisition.payable_amount, acquisition.plan_price.currency),
            'login_url': base + reverse('accounts:login'),
            'checkout_url': base + reverse('subscriptions:checkout', kwargs={'acquisition_id': acquisition.uuid}),
        }
        message = EmailMultiAlternatives(
            subject='Welcome to Press Nexa - account created',
            body=render_to_string('subscriptions/emails/signup_welcome.txt', context),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[acquisition.email],
        )
        message.attach_alternative(render_to_string('subscriptions/emails/signup_welcome.html', context), 'text/html')
        sent = message.send(fail_silently=False) == 1
        if not sent:
            logger.warning('Welcome email not sent for acquisition %s', acquisition_id)
        return sent
    except Exception:
        # A mail failure must not turn an already committed signup into an error.
        logger.exception('Welcome email failed for acquisition %s', acquisition_id)
        return False
