import json
import logging
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings

logger = logging.getLogger(__name__)


def normalize_whatsapp_number(value):
    digits = re.sub(r'\D+', '', value or '')
    if not digits:
        return ''
    if len(digits) == 10:
        return f'91{digits}'
    return digits


def _template_component(values):
    return {
        'type': 'body',
        'parameters': [{'type': 'text', 'text': str(value or '-')} for value in values],
    }


def send_template_message(*, to, template_name, values):
    phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
    recipient = normalize_whatsapp_number(to)
    provider = settings.WHATSAPP_PROVIDER.lower()
    api_key = settings.WHATSAPP_FAST2SMS_API_KEY if provider == 'fast2sms' else settings.WHATSAPP_CLOUD_API_TOKEN
    if not phone_number_id or not api_key or not recipient:
        logger.info('WhatsApp template skipped because configuration or recipient is missing.')
        return False

    payload = {
        'messaging_product': 'whatsapp',
        'to': recipient,
        'type': 'template',
        'template': {
            'name': template_name,
            'language': {'code': settings.WHATSAPP_TEMPLATE_LANGUAGE},
            'components': [_template_component(values)],
        },
    }
    if provider == 'fast2sms':
        url = f'https://www.fast2sms.com/dev/whatsapp/{settings.WHATSAPP_FAST2SMS_VERSION}/{phone_number_id}/messages'
        authorization = api_key
    else:
        url = f'https://graph.facebook.com/v20.0/{phone_number_id}/messages'
        authorization = f'Bearer {api_key}'

    request = Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Authorization': authorization,
            'Content-Type': 'application/json',
        },
        method='POST',
    )
    try:
        with urlopen(request, timeout=12) as response:
            response.read()
        return True
    except HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace')
        logger.warning('WhatsApp template failed: %s %s', exc.code, body)
    except URLError as exc:
        logger.warning('WhatsApp template failed: %s', exc)
    return False


def money_text(price):
    amount = price.amount / 100
    amount_text = f'{amount:,.0f}' if amount.is_integer() else f'{amount:,.2f}'
    return f'{price.currency} {amount_text}'


def notify_payment_success(*, acquisition, tenant, payment_reference, onboarding_url, profile_url):
    return send_template_message(
        to=acquisition.mobile,
        template_name=settings.WHATSAPP_PAYMENT_SUCCESS_TEMPLATE,
        values=[
            acquisition.publication_name,
            acquisition.user.username,
            acquisition.plan_price.plan.name,
            money_text(acquisition.plan_price),
            payment_reference,
            tenant.slug,
            onboarding_url,
            profile_url,
        ],
    )


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
