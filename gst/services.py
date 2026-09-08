from .models import GSTSettings


def configuration():
    return GSTSettings.objects.filter(pk=1).first() or GSTSettings()


def tax_amount(amount, rate):
    # Round integer paise half-up without floating point arithmetic.
    return (int(amount) * int(rate) + 50) // 100


def invoice_snapshot():
    config = configuration()
    return {'gstin': config.gstin, 'supply_description': config.supply_description}
