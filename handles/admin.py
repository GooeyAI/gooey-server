from django.contrib import admin

from .models import Handle


@admin.register(Handle)
class HandleAdmin(admin.ModelAdmin):
    pass
