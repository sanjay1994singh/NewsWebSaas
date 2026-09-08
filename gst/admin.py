from django.contrib import admin
from .models import GSTSettings


@admin.register(GSTSettings)
class GSTSettingsAdmin(admin.ModelAdmin):
    list_display = ('gstin', 'rate_percent', 'supply_description')

    def has_add_permission(self, request):
        return super().has_add_permission(request) and not GSTSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
