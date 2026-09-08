from django.core.validators import MaxValueValidator, RegexValidator
from django.db import models


class GSTSettings(models.Model):
    gstin = models.CharField(max_length=15, default='09ABUCS7544P1Z2', validators=[RegexValidator(r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$', 'Invalid GSTIN format.')])
    rate_percent = models.PositiveSmallIntegerField(default=18, validators=[MaxValueValidator(100)])
    supply_description = models.CharField(max_length=200, default='IT software product and services')

    class Meta:
        verbose_name_plural = 'GST configuration'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def __str__(self):
        return self.gstin
