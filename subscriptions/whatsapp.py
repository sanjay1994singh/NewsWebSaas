import json
import logging
import re
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.utils import timezone

from .pricing import money_display

logger = logging.getLogger(__name__)


def normalize_whatsapp_number(value):
    digits = re.sub(r'\D+', '', value or '')
    if not digits:
        return ''
    if len(digits) == 11 and digits.startswith('0'):
        digits = digits[1:]
    if len(digits) == 13 and digits.startswith('910'):
        digits = f'91{digits[3:]}'
    if len(digits) == 10:
        return f'91{digits}'
    return digits


def _template_component(values):
    return {
        'type': 'body',
        'parameters': [{'type': 'text', 'text': str(value or '-')} for value in values],
    }


def _fast2sms_message_id(template_name):
    template_ids = {
        settings.WHATSAPP_PAYMENT_SUCCESS_TEMPLATE: settings.WHATSAPP_PAYMENT_SUCCESS_MESSAGE_ID,
        settings.WHATSAPP_PAYMENT_FAILED_TEMPLATE: settings.WHATSAPP_PAYMENT_FAILED_MESSAGE_ID,
    }
    return template_ids.get(template_name, '')


def _request_json(*, url, payload=None, headers=None, method='POST'):
    data = json.dumps(payload).encode('utf-8') if payload is not None else None
    request = Request(url, data=data, headers=headers or {}, method=method)
    with urlopen(request, timeout=12) as response:
        response.read()


def _send_fast2sms_simple_template(*, to, template_name, values, api_key, phone_number_id, media_url='', document_filename=''):
    message_id = _fast2sms_message_id(template_name)
    if not message_id:
        return None
    query = urlencode(
        {
            'message_id': message_id,
            'phone_number_id': phone_number_id,
            'numbers': to,
            'variables_values': '|'.join(str(value or '-') for value in values),
            **({'media_url': media_url} if media_url else {}),
            **({'document_filename': document_filename} if document_filename else {}),
        }
    )
    _request_json(
        url=f'https://www.fast2sms.com/dev/whatsapp?{query}',
        headers={'Authorization': api_key},
        method='GET',
    )
    return True


def send_template_message(*, to, template_name, values, media_url='', document_filename=''):
    if not settings.WHATSAPP_NOTIFICATIONS_ENABLED:
        logger.info('WhatsApp template skipped because notifications are disabled.')
        return False
    phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
    recipient = normalize_whatsapp_number(to)
    provider = settings.WHATSAPP_PROVIDER.lower()
    api_key = settings.WHATSAPP_FAST2SMS_API_KEY if provider == 'fast2sms' else settings.WHATSAPP_CLOUD_API_TOKEN
    if not phone_number_id or not api_key or not recipient:
        logger.info('WhatsApp template skipped because configuration or recipient is missing.')
        return False

    try:
        if provider == 'fast2sms':
            sent = _send_fast2sms_simple_template(
                to=recipient,
                template_name=template_name,
                values=values,
                api_key=api_key,
                phone_number_id=phone_number_id,
                media_url=media_url,
                document_filename=document_filename,
            )
            if sent is not None:
                return sent
    except HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace')
        logger.warning('Fast2SMS simple template failed: %s %s', exc.code, body)
        return False
    except URLError as exc:
        logger.warning('Fast2SMS simple template failed: %s', exc)
        return False

    components = [_template_component(values)]
    if media_url:
        header_parameter = {
            'type': 'document',
            'document': {
                'link': media_url,
                'filename': document_filename or 'invoice.pdf',
            },
        }
        components.insert(0, {'type': 'header', 'parameters': [header_parameter]})
    payload = {
        'messaging_product': 'whatsapp',
        'to': recipient,
        'type': 'template',
        'template': {
            'name': template_name,
            'language': {'code': settings.WHATSAPP_TEMPLATE_LANGUAGE},
            'components': components,
        },
    }
    if provider == 'fast2sms':
        url = f'https://www.fast2sms.com/dev/whatsapp/{settings.WHATSAPP_FAST2SMS_VERSION}/{phone_number_id}/messages'
        authorization = api_key
    else:
        url = f'https://graph.facebook.com/v20.0/{phone_number_id}/messages'
        authorization = f'Bearer {api_key}'

    try:
        _request_json(url=url, payload=payload, headers={
            'Authorization': authorization,
            'Content-Type': 'application/json',
        })
        return True
    except HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace')
        logger.warning('WhatsApp template failed: %s %s', exc.code, body)
    except URLError as exc:
        logger.warning('WhatsApp template failed: %s', exc)
    return False


def send_session_document(*, to, document_url, filename='invoice.pdf'):
    if not settings.WHATSAPP_NOTIFICATIONS_ENABLED:
        logger.info('WhatsApp document skipped because notifications are disabled.')
        return False
    phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
    api_key = settings.WHATSAPP_FAST2SMS_API_KEY
    recipient = normalize_whatsapp_number(to)
    if not phone_number_id or not api_key or not recipient or not document_url:
        logger.info('WhatsApp document skipped because configuration, recipient, or URL is missing.')
        return False
    query = urlencode(
        {
            'phone_number_id': phone_number_id,
            'to': recipient,
            'type': 'document',
            'url': document_url,
            'document_filename': filename,
        }
    )
    try:
        _request_json(
            url=f'https://www.fast2sms.com/dev/whatsapp-session?{query}',
            headers={'Authorization': api_key},
            method='POST',
        )
        return True
    except HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace')
        logger.warning('Fast2SMS document failed: %s %s', exc.code, body)
    except URLError as exc:
        logger.warning('Fast2SMS document failed: %s', exc)
    return False


def money_text(price):
    amount = price.amount / 100
    amount_text = f'{amount:,.0f}' if amount.is_integer() else f'{amount:,.2f}'
    return f'{price.currency} {amount_text}'


def _account_display_name(user):
    full_name = (user.get_full_name() or '').strip()
    return full_name or user.username


def _date_text(value):
    if not value:
        return '-'
    local_value = timezone.localtime(value) if timezone.is_aware(value) else value
    return local_value.strftime('%d %b %Y')


def notify_payment_success(*, acquisition, tenant, payment_reference, dashboard_url, profile_url, invoice_document_url=''):
    from .services import tenant_public_site_url

    workspace_url = tenant_public_site_url(tenant)
    tenant_profile_url = f"{workspace_url.rstrip('/')}/account/profile/"
    billing_months = acquisition.billing_months or 1
    duration = '1 month' if billing_months == 1 else f'{billing_months} months'
    paid_amount = acquisition.payable_amount or acquisition.plan_price.amount
    subscription = getattr(tenant, 'subscription', None)
    invoice_filename = f'pressnexa-invoice-{payment_reference or tenant.slug}.pdf'
    sent = send_template_message(
        to=acquisition.mobile,
        template_name=settings.WHATSAPP_PAYMENT_SUCCESS_TEMPLATE,
        media_url=invoice_document_url,
        document_filename=invoice_filename,
        values=[
            _account_display_name(acquisition.user),
            tenant.business_name or acquisition.publication_name,
            workspace_url,
            acquisition.plan_price.plan.name,
            duration,
            _date_text(getattr(subscription, 'current_period_start', None)),
            _date_text(getattr(subscription, 'current_period_end', None)),
            money_display(paid_amount, acquisition.plan_price.currency),
            payment_reference,
            tenant_profile_url,
        ],
    )
    if invoice_document_url and not sent:
        send_session_document(
            to=acquisition.mobile,
            document_url=invoice_document_url,
            filename=invoice_filename,
        )
    return sent


def notify_payment_failed(*, acquisition, payment_reference, checkout_url, profile_url):
    return send_template_message(
        to=acquisition.mobile,
        template_name=settings.WHATSAPP_PAYMENT_FAILED_TEMPLATE,
        values=[
            acquisition.publication_name,
            acquisition.user.username,
            acquisition.plan_price.plan.name,
            money_text(acquisition.plan_price),
            payment_reference,
            checkout_url,
            profile_url,
            '8279408396',
        ],
    )
