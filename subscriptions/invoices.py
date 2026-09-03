from django.conf import settings
from django.core.mail import EmailMessage
from django.template.defaultfilters import date as date_filter
from django.utils import timezone


COMPANY = {
    'brand': 'Press Nexa',
    'legal_name': 'SHRI INFOWAVE PRIVATE LIMITED',
    'cin': 'U62012UW2026PTC257361',
    'pan': 'ABUCS7544P',
    'address': '101 Govind Kund Tila, Radha Niwas, Vrindaban, Mathura, Uttar Pradesh, India',
    'email': 'srbc500@gmail.com',
    'whatsapp': '8279408396',
}


def invoice_number(record):
    return f"PNX-{record.created_at:%Y%m%d}-{record.id:05d}"


def invoice_filename(record):
    return f"{invoice_number(record)}.pdf"


def build_invoice_pdf(record):
    tenant = record.tenant
    subscription = record.subscription
    plan_name = subscription.plan.name if subscription else 'Press Nexa subscription'
    cycle = subscription.get_billing_cycle_display() if subscription else '-'
    amount = record.amount / 100
    issued_on = timezone.localtime(record.created_at)
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
            'amount': f"{record.currency} {amount:,.2f}",
        }
    )


def email_invoice(record):
    if not record.tenant.email:
        return False
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
        from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', COMPANY['email']),
        to=[record.tenant.email],
    )
    message.attach(invoice_filename(record), pdf, 'application/pdf')
    message.send(fail_silently=True)
    return True


def _invoice_pdf(data):
    ops = [
        '1 1 1 rg',
        '0 0 595 842 re f',
        '0.063 0.184 0.161 rg',
        '44 806 507 4 re f',
        '0 0 0 rg',
        _text(44, 774, 24, 'Press Nexa', bold=True),
        '0.388 0.463 0.431 rg',
        _text(44, 754, 10, COMPANY['legal_name']),
        _text(44, 738, 9, f"CIN: {COMPANY['cin']}  |  PAN: {COMPANY['pan']}"),
        '0 0 0 rg',
        _text(405, 774, 26, 'INVOICE', bold=True),
        '0.388 0.463 0.431 rg',
        _text(405, 752, 9, f"No. {data['number']}"),
        _text(405, 736, 9, f"Date: {data['date']}"),
        '0.851 0.894 0.871 RG',
        '44 708 m 551 708 l S',
        '0.965 0.985 0.973 rg',
        '455 674 78 28 re f',
        '0.851 0.894 0.871 RG',
        '455 674 78 28 re S',
        '0.063 0.184 0.161 rg',
        _text(476, 684, 10, data['status'].upper(), bold=True),
        '0.851 0.894 0.871 RG',
        '44 508 236 140 re S',
        '315 508 225 140 re S',
        '44 336 496 126 re S',
        '0.063 0.184 0.161 rg',
        _text(60, 620, 11, 'BILL TO', bold=True),
        _text(331, 620, 11, 'PAYMENT DETAILS', bold=True),
        '0 0 0 rg',
        _text(60, 594, 17, _short(data['publication'], 28), bold=True),
        '0.388 0.463 0.431 rg',
        _text(60, 570, 9, _short(data['business_name'], 34)),
        _text(60, 552, 9, _short(data['email'], 36)),
        _text(60, 534, 9, f"Mobile: {_short(data['mobile'], 22)}"),
        _label_value(331, 594, 'Payment reference', _short(data['payment_reference'], 28)),
        _label_value(331, 560, 'Billing cycle', data['cycle']),
        _label_value(331, 526, 'Status', data['status']),
        '0.965 0.973 0.969 rg',
        '44 430 496 32 re f',
        '0.851 0.894 0.871 RG',
        '44 430 496 32 re S',
        '0 0 0 rg',
        _text(60, 441, 9, 'DESCRIPTION', bold=True),
        _text(322, 441, 9, 'CYCLE', bold=True),
        _text(440, 441, 9, 'AMOUNT', bold=True),
        '0 0 0 rg',
        _text(60, 398, 12, _short(data['plan'], 42), bold=True),
        _text(322, 398, 10, data['cycle']),
        _text(440, 398, 12, data['amount'], bold=True),
        '0.851 0.894 0.871 RG',
        '60 372 m 524 372 l S',
        '0.965 0.973 0.969 rg',
        '330 342 194 38 re f',
        '0.851 0.894 0.871 RG',
        '330 342 194 38 re S',
        '0.063 0.184 0.161 rg',
        _text(354, 356, 13, 'Total Paid', bold=True),
        _text(440, 356, 13, data['amount'], bold=True),
        '0.388 0.463 0.431 rg',
        _text(44, 270, 9, 'This invoice is generated electronically for the verified Press Nexa subscription payment.'),
        _text(44, 254, 9, 'For corrections, contact support with your invoice number and payment reference.'),
        '0.851 0.894 0.871 RG',
        '44 106 m 551 106 l S',
        '0.082 0.376 0.310 rg',
        _text(44, 82, 11, COMPANY['brand'], bold=True),
        '0.388 0.463 0.431 rg',
        _text(44, 66, 8, COMPANY['address']),
        _text(44, 52, 8, f"Support: {COMPANY['email']} | WhatsApp: {COMPANY['whatsapp']}"),
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
