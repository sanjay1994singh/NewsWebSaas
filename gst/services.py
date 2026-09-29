from .models import GSTSettings


def configuration():
    return GSTSettings.objects.filter(pk=1).first() or GSTSettings()


def tax_amount(amount, rate):
    # Round integer paise half-up without floating point arithmetic.
    return (int(amount) * int(rate) + 50) // 100


def split_inclusive_tax(gross_amount, rate):
    gross_amount = int(gross_amount or 0)
    rate = int(rate or 0)
    if rate <= 0:
        return gross_amount, 0
    taxable = round(gross_amount * 100 / (100 + rate))
    return taxable, gross_amount - taxable


def invoice_snapshot():
    config = configuration()
    return {'gstin': config.gstin, 'supply_description': config.supply_description, 'price_tax_mode': config.price_tax_mode}
