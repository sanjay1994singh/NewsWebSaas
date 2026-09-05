from django.conf import settings
from django.core.mail import EmailMessage
from django.template.defaultfilters import date as date_filter
from django.utils import timezone

from .pricing import money_display
from .support import BASE_COMPANY_PROFILE, active_support_contact


COMPANY = {
    'brand': BASE_COMPANY_PROFILE['brand_name'],
    'legal_name': BASE_COMPANY_PROFILE['legal_name'],
    'cin': BASE_COMPANY_PROFILE['cin'],
    'pan': BASE_COMPANY_PROFILE['pan'],
    'address': '101 Govind Kund Tila, Radha Niwas, Vrindaban, Mathura, Uttar Pradesh, India',
}


def invoice_company():
    support = active_support_contact()
    return {
        **COMPANY,
        'email': support['support_email'],
        'whatsapp': support['whatsapp_number'],
    }


def invoice_number(record):
    return f"PNX-{record.created_at:%Y%m%d}-{record.id:05d}"


def invoice_filename(record):
    return f"{invoice_number(record)}.pdf"


def build_invoice_pdf(record):
    tenant = record.tenant
    subscription = record.subscription
    plan_name = subscription.plan.name if subscription else 'Press Nexa subscription'
    billing_months = record.billing_months or getattr(subscription, 'billing_months', 1) or 1
    cycle = f"{billing_months} month" if billing_months == 1 else f"{billing_months} months"
    list_amount = record.list_amount or record.amount
    discount_amount = record.discount_amount or 0
    issued_on = timezone.localtime(record.created_at)
    period_start = record.period_start or getattr(subscription, 'current_period_start', None) or getattr(subscription, 'start_at', None)
    period_end = record.period_end or getattr(subscription, 'current_period_end', None) or getattr(subscription, 'charge_at', None)
    return _invoice_pdf(
        {
            'number': invoice_number(record),
            'date': date_filter(issued_on, 'd M Y, h:i A'),
            'payment_reference': record.razorpay_payment_id or record.razorpay_invoice_id or '-',
            'status': record.status.title(),
            'publication': tenant.publication_name,
            'business_name': tenant.business_name,
            'email': tenant.email,
            'mobile': tenant.mobile or '-',
            'plan': plan_name,
            'cycle': cycle,
            'period_start': date_filter(timezone.localtime(period_start), 'd M Y') if period_start else '-',
            'period_end': date_filter(timezone.localtime(period_end), 'd M Y') if period_end else '-',
            'list_amount': money_display(list_amount, record.currency),
            'discount_percent': f"{record.discount_percent or 0}%",
            'discount_amount': money_display(discount_amount, record.currency),
            'amount': money_display(record.amount, record.currency),
        }
    )


def email_invoice(record):
    if not record.tenant.email:
        return False
    company = invoice_company()
    pdf = build_invoice_pdf(record)
    subject = f"Your Press Nexa invoice {invoice_number(record)}"
    body = (
        f"Hello {record.tenant.publication_name},\n\n"
        "Your Press Nexa payment has been received successfully. "
        "Please find the invoice PDF attached.\n\n"
        "Regards,\nPress Nexa"
    )
    message = EmailMessage(
        subject=subject,
        body=body,
        from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', company['email']),
        to=[record.tenant.email],
    )
    message.attach(invoice_filename(record), pdf, 'application/pdf')
    message.send(fail_silently=True)
    return True


def _invoice_pdf(data):
    company = invoice_company()
    ops = [
        '1 1 1 rg',
        '0 0 595 842 re f',
        '0.063 0.184 0.161 rg',
        '44 806 507 3 re f',
        '0 0 0 rg',
        _text(44, 776, 18, 'Press Nexa', bold=True),
        '0.388 0.463 0.431 rg',
        _text(44, 756, 9, company['legal_name']),
        _text(44, 741, 8, f"CIN: {company['cin']}  |  PAN: {company['pan']}"),
        '0 0 0 rg',
        _text(421, 776, 20, 'INVOICE', bold=True),
        '0.388 0.463 0.431 rg',
        _text(405, 752, 9, f"No. {data['number']}"),
        _text(405, 736, 9, f"Date: {data['date']}"),
        '0.851 0.894 0.871 RG',
        '44 710 m 551 710 l S',
        '0.965 0.985 0.973 rg',
        '455 676 78 24 re f',
        '0.851 0.894 0.871 RG',
        '455 676 78 24 re S',
        '0.063 0.184 0.161 rg',
        _text(477, 685, 9, data['status'].upper(), bold=True),
        '0.851 0.894 0.871 RG',
        '44 512 236 132 re S',
        '315 512 225 132 re S',
        '44 314 496 142 re S',
        '0.063 0.184 0.161 rg',
        _text(60, 620, 9, 'BILL TO', bold=True),
        _text(331, 620, 9, 'PAYMENT DETAILS', bold=True),
        '0 0 0 rg',
        _text(60, 596, 13, _short(data['publication'], 34), bold=True),
        _compact_label_value(60, 575, 'Channel / Paper', _short(data['business_name'], 34)),
        _compact_label_value(60, 557, 'Email', _short(data['email'], 38)),
        _compact_label_value(60, 539, 'Mobile', _short(data['mobile'], 24)),
        _compact_label_value(331, 596, 'Payment ref', _short(data['payment_reference'], 28), value_x=424),
        _compact_label_value(331, 574, 'Billing cycle', data['cycle'], value_x=424),
        _compact_label_value(331, 552, 'Plan starts', data['period_start'], value_x=424),
        _compact_label_value(331, 530, 'Plan ends', data['period_end'], value_x=424),
        '0.965 0.973 0.969 rg',
        '44 426 496 30 re f',
        '0.851 0.894 0.871 RG',
        '44 426 496 30 re S',
        '0 0 0 rg',
        _text(60, 437, 8, 'DESCRIPTION', bold=True),
        _text(322, 437, 8, 'CYCLE', bold=True),
        _text(440, 437, 8, 'AMOUNT', bold=True),
        '0 0 0 rg',
        _text(60, 399, 10, _short(data['plan'], 46), bold=True),
        _text(322, 399, 9, data['cycle']),
        _text(440, 399, 10, data['list_amount'], bold=True),
        '0.851 0.894 0.871 RG',
        '60 378 m 524 378 l S',
        _text(60, 360, 9, 'Offer discount'),
        _text(322, 360, 9, data['discount_percent']),
        _text(440, 360, 9, f"-{data['discount_amount']}"),
        '60 342 m 524 342 l S',
        '0.965 0.973 0.969 rg',
        '340 314 184 34 re f',
        '0.851 0.894 0.871 RG',
        '340 314 184 34 re S',
        '0.063 0.184 0.161 rg',
        _text(358, 326, 10, 'Final Paid', bold=True),
        _text(440, 326, 10, data['amount'], bold=True),
        '0.388 0.463 0.431 rg',
        _text(44, 286, 8, 'This invoice is generated electronically for the verified Press Nexa subscription payment.'),
        _text(44, 272, 8, 'For corrections, contact support with your invoice number and payment reference.'),
        '0.851 0.894 0.871 RG',
        '44 106 m 551 106 l S',
        '0.082 0.376 0.310 rg',
        _text(44, 82, 10, company['brand'], bold=True),
        '0.388 0.463 0.431 rg',
        _text(44, 66, 7, company['address']),
        _text(44, 52, 7, f"Support: {company['email']} | WhatsApp: {company['whatsapp']}"),
    ]
    content = '\n'.join(ops).encode('latin-1', errors='replace')
    objects = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> /Contents 6 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>',
        b'<< /Length ' + str(len(content)).encode('ascii') + b' >>\nstream\n' + content + b'\nendstream',
    ]
    pdf = bytearray(b'%PDF-1.4\n')
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f'{index} 0 obj\n'.encode('ascii'))
        pdf.extend(obj)
        pdf.extend(b'\nendobj\n')
    xref_at = len(pdf)
    pdf.extend(f'xref\n0 {len(objects) + 1}\n'.encode('ascii'))
    pdf.extend(b'0000000000 65535 f \n')
    for offset in offsets[1:]:
        pdf.extend(f'{offset:010d} 00000 n \n'.encode('ascii'))
    pdf.extend(
        f'trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n'.encode('ascii')
    )
    return bytes(pdf)


def _pdf_text(value):
    return str(value).replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')


def _short(value, limit):
    value = str(value or '-')
    return value if len(value) <= limit else f"{value[:limit - 3]}..."


def _text(x, y, size, value, *, bold=False):
    font = 'F2' if bold else 'F1'
    return f"BT /{font} {size} Tf {x} {y} Td ({_pdf_text(value)}) Tj ET"


def _label_value(x, y, label, value):
    return '\n'.join(
        [
            '0.388 0.463 0.431 rg',
            _text(x, y, 8, label.upper(), bold=True),
            '0 0 0 rg',
            _text(x, y - 18, 11, value),
        ]
    )


def _compact_label_value(x, y, label, value, *, value_x=None):
    value_x = value_x if value_x is not None else x + 58
    return '\n'.join(
        [
            '0.388 0.463 0.431 rg',
            _text(x, y, 7, label.upper(), bold=True),
            '0 0 0 rg',
            _text(value_x, y, 8, value),
        ]
    )
