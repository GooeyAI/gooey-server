from django.contrib import admin

from .models import ApiKey


@admin.register(ApiKey)
class ApiKeyAdmin(admin.ModelAdmin):
    pass
