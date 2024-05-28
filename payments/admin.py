from django.contrib import admin

from .models import Subscription


class SubscriptionAdmin(admin.ModelAdmin):
    pass


admin.site.register(Subscription, admin.ModelAdmin)
