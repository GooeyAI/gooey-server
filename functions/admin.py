from django.contrib import admin

from functions.models import CalledFunction
from gooeysite.admin import GooeyModelAdmin


# Register your models here.
@admin.register(CalledFunction)
class CalledFunctionAdmin(GooeyModelAdmin):
    autocomplete_fields = ["saved_run", "function_run"]
