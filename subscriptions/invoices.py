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
    lines = [
        'Press Nexa Tax Invoice',
        COMPANY['legal_name'],
        f"CIN: {COMPANY['cin']} | PAN: {COMPANY['pan']}",
        COMPANY['address'],
        f"Support: {COMPANY['email']} | WhatsApp: {COMPANY['whatsapp']}",
        '',
        f"Invoice number: {invoice_number(record)}",
        f"Invoice date: {date_filter(issued_on, 'd M Y, h:i A')}",
        f"Payment reference: {record.razorpay_payment_id or record.razorpay_invoice_id or '-'}",
        f"Payment status: {record.status.title()}",
        '',
        'Bill To',
        f"Publication: {tenant.publication_name}",
        f"Business name: {tenant.business_name}",
        f"Email: {tenant.email}",
        f"Mobile: {tenant.mobile or '-'}",
        '',
        'Items',
        f"{plan_name} ({cycle})",
        f"Total paid: {record.currency} {amount:,.2f}",
        '',
        'This invoice is generated electronically for the verified Press Nexa subscription payment.',
        'For correction requests, contact support with your invoice number and payment reference.',
    ]
    return _simple_pdf(lines)


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


def _simple_pdf(lines):
    content_lines = ['BT', '/F1 18 Tf', '72 790 Td', f"({_pdf_text(lines[0])}) Tj"]
    for line in lines[1:]:
        if line:
            content_lines.append('/F1 10 Tf')
            content_lines.append(f"0 -18 Td ({_pdf_text(line)}) Tj")
        else:
            content_lines.append("0 -18 Td")
    content_lines.append('ET')
    content = '\n'.join(content_lines).encode('latin-1', errors='replace')
    objects = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
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
