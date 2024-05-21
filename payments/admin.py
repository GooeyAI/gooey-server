from django.contrib import admin

from .models import AutoRechargeSubscription, Subscription


class AutoRechargeAdmin(admin.ModelAdmin):
    pass


class SubscriptionAdmin(admin.ModelAdmin):
    pass


admin.site.register(AutoRechargeSubscription, AutoRechargeAdmin)
admin.site.register(Subscription, admin.ModelAdmin)
