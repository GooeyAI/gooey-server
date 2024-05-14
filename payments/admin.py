from django.contrib import admin

from .models import AutoRechargeSubscription


class AutoRechargeAdmin(admin.ModelAdmin):
    pass


admin.site.register(AutoRechargeSubscription, AutoRechargeAdmin)
