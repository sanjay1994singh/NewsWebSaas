from django.conf import settings
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.template.loader import render_to_string
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
            'list_amount': _pdf_money_display(list_amount, record.currency),
            'discount_percent': f"{record.discount_percent or 0}%",
            'discount_amount': _pdf_money_display(discount_amount, record.currency),
            'amount': _pdf_money_display(record.amount, record.currency),
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


def agreement_filename(acceptance):
    return f"Plan-Purchase-Agreement-{acceptance.acquisition.uuid}.txt"


def build_agreement_text(acceptance):
    return (
        f"{acceptance.agreement_title}\n"
        f"{'=' * len(acceptance.agreement_title)}\n\n"
        f"Accepted by: {acceptance.user.get_username()}\n"
        f"Plan: {acceptance.plan_name or '-'}\n"
        f"Billing duration: {acceptance.billing_months} month{'s' if acceptance.billing_months != 1 else ''}\n"
        f"Accepted at: {date_filter(timezone.localtime(acceptance.accepted_at), 'd M Y, h:i A')}\n"
        f"IP address: {acceptance.ip_address or '-'}\n\n"
        f"Checkbox text:\n{acceptance.checkbox_label}\n\n"
        f"Agreement content:\n{acceptance.agreement_content}\n"
    )


def email_purchase_success(record, *, plain_password=''):
    tenant = record.tenant
    if not tenant.email:
        return False
    company = invoice_company()
    subscription = record.subscription
    user = tenant.owner
    plan_name = subscription.plan.name if subscription else 'Press Nexa subscription'
    acceptance = (
        user.purchase_agreement_acceptances
        .filter(acquisition__tenant=tenant)
        .select_related('acquisition')
        .order_by('-accepted_at', '-created_at')
        .first()
    )
    primary_domain = tenant.domains.filter(is_primary=True).first()
    context = {
        'company': company,
        'tenant': tenant,
        'user': user,
        'record': record,
        'subscription': subscription,
        'plan_name': plan_name,
        'invoice_number': invoice_number(record),
        'amount': money_display(record.amount, record.currency),
        'list_amount': money_display(record.list_amount or record.amount, record.currency),
        'discount_amount': money_display(record.discount_amount or 0, record.currency),
        'period_start': record.period_start,
        'period_end': record.period_end,
        'dashboard_url': f"{settings.SITE_BASE_URL}/dashboard/",
        'profile_url': f"{settings.SITE_BASE_URL}/account/profile/",
        'site_url': f"https://{primary_domain.domain}/" if primary_domain else settings.SITE_BASE_URL,
        'plain_password': plain_password,
        'acceptance': acceptance,
    }
    subject = f"Press Nexa plan activated - {tenant.publication_name}"
    text_body = render_to_string('subscriptions/emails/purchase_success.txt', context)
    html_body = render_to_string('subscriptions/emails/purchase_success.html', context)
    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', company['email']),
        to=[tenant.email],
    )
    message.attach_alternative(html_body, 'text/html')
    message.attach(invoice_filename(record), build_invoice_pdf(record), 'application/pdf')
    if acceptance:
        message.attach(agreement_filename(acceptance), build_agreement_text(acceptance), 'text/plain')
    message.send(fail_silently=True)
    return True


def _invoice_pdf(data):
    """Render every billing record with the same print-friendly A4 layout."""
    from io import BytesIO
    from xml.sax.saxutils import escape
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, HRFlowable

    company = invoice_company()
    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=(595, 842), rightMargin=50,
                            leftMargin=50, topMargin=55, bottomMargin=55,
                            title=f"Invoice {data['number']}", author=company['brand'],
                            pageCompression=0)
    styles = {
        'body': ParagraphStyle('body', fontName='Helvetica', fontSize=9, leading=14, textColor=colors.HexColor('#555555')),
        'bold': ParagraphStyle('bold', fontName='Helvetica-Bold', fontSize=10, leading=15),
        'brand': ParagraphStyle('brand', fontName='Helvetica-Bold', fontSize=19, leading=25),
        'title': ParagraphStyle('title', fontName='Helvetica-Bold', fontSize=25, leading=31, alignment=2),
        'right': ParagraphStyle('right', fontName='Helvetica', fontSize=9, leading=15, alignment=2),
        'label': ParagraphStyle('label', fontName='Helvetica-Bold', fontSize=8, leading=13),
    }

    def text(value, style='body'):
        return Paragraph(escape(str(value or '-')), styles[style])

    def table(rows, widths, extra=()):
        result = Table(rows, colWidths=widths, hAlign='LEFT')
        result.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            *extra,
        ]))
        return result

    seller = [text(company['brand'], 'brand'), text(company['legal_name']),
              text(company['address']), text(f"CIN: {company['cin']}"),
              text(f"PAN: {company['pan']}"), text(company['email']),
              text(f"WhatsApp: {company['whatsapp']}")]
    metadata = [text('INVOICE', 'title'), Spacer(1, 10),
                text(f"INVOICE NO:  {data['number']}", 'right'),
                text(f"ISSUE DATE:  {data['date']}", 'right'),
                text(f"STATUS:  {data['status'].upper()}", 'right')]
    story = [table([[seller, metadata]], [285, 210]), Spacer(1, 22),
             HRFlowable(width='100%', thickness=1, color=colors.black), Spacer(1, 14),
             text('BILLED TO', 'label'), text(data['publication'], 'bold'),
             text(f"Channel: {data['business_name']}"), text(data['email']),
             text(f"Mobile: {data['mobile']}"), Spacer(1, 24)]
    description = [text(data['plan'], 'bold'),
                   text(f"Subscription - {data['cycle']}"),
                   text(f"Period: {data['period_start']} to {data['period_end']}")]
    story.append(table([
        [text('#', 'label'), text('DESCRIPTION', 'label'), text('QTY', 'label'), text('RATE', 'label'), text('AMOUNT', 'label')],
        [text('01'), description, text('1'), text(data['list_amount'], 'right'), text(data['list_amount'], 'right')],
    ], [24, 251, 30, 90, 100], [
        ('LINEABOVE', (0, 0), (-1, 0), 1, colors.black),
        ('LINEBELOW', (0, 0), (-1, 0), 1, colors.black),
        ('LINEBELOW', (0, 1), (-1, 1), .5, colors.HexColor('#dddddd')),
        ('TOPPADDING', (0, 1), (-1, 1), 12),
        ('BOTTOMPADDING', (0, 1), (-1, 1), 14),
    ]))
    story.append(Spacer(1, 22))
    payment = [text('PAYMENT DETAILS', 'label'), text('Reference'), text(data['payment_reference']),
               Spacer(1, 14), text('SUPPORT', 'label'),
               text('For billing corrections, contact support with your invoice number and payment reference.')]
    totals = table([
        [text('Subtotal'), text(data['list_amount'], 'right')],
        [text('Discount / credit'), text(data['discount_amount'], 'right')],
        [text('Total', 'bold'), text(data['amount'], 'right')],
        [text('Payment status'), text(data['status'].upper(), 'right')],
    ], [105, 120], [('LINEABOVE', (0, 2), (-1, 2), 1, colors.black),
                   ('LINEBELOW', (0, 2), (-1, 2), 1, colors.black)])
    story.append(table([[payment, totals]], [270, 225]))
    story.extend([Spacer(1, 38), HRFlowable(width='100%', thickness=.5, color=colors.HexColor('#dddddd')),
                  Spacer(1, 10), text('Thank you for choosing Press Nexa. This invoice is generated electronically.')])
    doc.build(story)
    return output.getvalue()


def _pdf_money_display(amount, currency='INR'):
    if currency == 'INR':
        value = int(amount or 0) / 100
        value_text = f"{value:,.0f}" if value.is_integer() else f"{value:,.2f}"
        return f"Rs {value_text}"
    return money_display(amount, currency)
