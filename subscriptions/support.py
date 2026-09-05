DEFAULT_SUPPORT_EMAIL = 'shriinfowaveprivatelimited@gmail.com'
DEFAULT_SUPPORT_WHATSAPP = '918279408396'


BASE_COMPANY_PROFILE = {
    'brand_name': 'Press Nexa',
    'legal_name': 'SHRI INFOWAVE PRIVATE LIMITED',
    'cin': 'U62012UW2026PTC257361',
    'pan': 'ABUCS7544P',
    'incorporated_on': '17 August 2026',
    'registered_office': '101 Govind Kund Tila, Radha Niwas, Vrindaban, Mathura, Mathura - 281121, Uttar Pradesh, India',
    'business_hours': 'Monday to Saturday, 10:00 AM to 6:00 PM IST',
}


def normalize_support_whatsapp(value):
    digits = ''.join(ch for ch in str(value or '') if ch.isdigit())
    if len(digits) == 10:
        digits = f'91{digits}'
    return digits or DEFAULT_SUPPORT_WHATSAPP


def active_support_contact():
    from .models import PlatformSupportContact

    contact = PlatformSupportContact.objects.filter(is_active=True).order_by('-updated_at', '-created_at').first()
    if contact:
        email = contact.support_email or DEFAULT_SUPPORT_EMAIL
        whatsapp = normalize_support_whatsapp(contact.whatsapp_number)
        business_hours = contact.business_hours or BASE_COMPANY_PROFILE['business_hours']
    else:
        email = DEFAULT_SUPPORT_EMAIL
        whatsapp = DEFAULT_SUPPORT_WHATSAPP
        business_hours = BASE_COMPANY_PROFILE['business_hours']
    return {
        'support_email': email,
        'whatsapp_number': whatsapp,
        'whatsapp_url': f'https://wa.me/{whatsapp}',
        'business_hours': business_hours,
    }


def company_profile():
    return {
        **BASE_COMPANY_PROFILE,
        **active_support_contact(),
    }
