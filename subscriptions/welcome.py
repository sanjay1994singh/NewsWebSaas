"""New-account welcome mail, dispatched after the signup transaction commits."""
import logging
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from .models import CustomerAcquisition
from .pricing import money_display

logger = logging.getLogger(__name__)


def send_signup_welcome(acquisition_id, *, signup_password=''):
    try:
        acquisition = CustomerAcquisition.objects.select_related('user', 'plan_price__plan').get(pk=acquisition_id)
        if not acquisition.email:
            return False
        base = settings.SITE_BASE_URL.rstrip('/')
        context = {
            'acquisition': acquisition,
            'username': acquisition.user.username,
            'full_name': acquisition.user.get_full_name(),
            'signup_password': signup_password,
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


def send_profile_details(user_id):
    """Send current account information when an email-less owner adds an email."""
    from django.contrib.auth import get_user_model
    from tenants.models import Tenant
    from .models import TenantSubscription
    try:
        user = get_user_model().objects.get(pk=user_id)
        if not user.email:
            return False
        workspaces = []
        for tenant in Tenant.objects.filter(owner=user):
            subscription = TenantSubscription.objects.select_related('plan').filter(tenant=tenant).first()
            rows = [('Channel / paper', tenant.business_name), ('Publication', tenant.publication_name),
                    ('Mobile', tenant.mobile), ('Workspace status', tenant.get_status_display())]
            if subscription:
                rows += [('Plan', subscription.plan.name), ('Subscription status', subscription.get_status_display()),
                         ('Duration', f'{subscription.billing_months} month(s)'),
                         ('Period start', subscription.current_period_start or 'Not set'),
                         ('Period end', subscription.current_period_end or 'Not set')]
            workspaces.append(rows)
        pending = []
        base = settings.SITE_BASE_URL.rstrip('/')
        for acquisition in CustomerAcquisition.objects.filter(user=user, tenant__isnull=True).select_related('plan_price__plan'):
            pending.append({
                'rows': [('Channel / paper', acquisition.business_name), ('Publication', acquisition.publication_name),
                         ('Mobile', acquisition.mobile), ('Plan', acquisition.plan_price.plan.name),
                         ('Duration', f'{acquisition.billing_months} month(s)'),
                         ('Offer payable amount', money_display(acquisition.payable_amount, acquisition.plan_price.currency)),
                         ('Status', acquisition.get_status_display())],
                'checkout_url': base + reverse('subscriptions:checkout', kwargs={'acquisition_id': acquisition.uuid})
                    if acquisition.status == CustomerAcquisition.Status.PAYMENT_PENDING else '',
            })
        context = {'account_name': user.get_full_name(), 'username': user.username, 'email': user.email,
                   'workspaces': workspaces, 'pending': pending,
                   'login_url': base + reverse('accounts:login'),
                   'profile_url': base + reverse('accounts:profile')}
        message = EmailMultiAlternatives(
            subject='Welcome to Press Nexa - your account details',
            body=render_to_string('subscriptions/emails/profile_details.txt', context),
            from_email=settings.DEFAULT_FROM_EMAIL, to=[user.email])
        message.attach_alternative(render_to_string('subscriptions/emails/profile_details.html', context), 'text/html')
        return message.send(fail_silently=False) == 1
    except Exception:
        logger.exception('Profile details email failed for user %s', user_id)
        return False
