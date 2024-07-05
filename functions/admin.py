from django.contrib import admin

from functions.models import CalledFunction


# Register your models here.
@admin.register(CalledFunction)
class CalledFunctionAdmin(admin.ModelAdmin):
    autocomplete_fields = ["saved_run", "function_run"]
