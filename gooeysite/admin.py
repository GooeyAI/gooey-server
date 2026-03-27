from django.contrib import admin
from django.contrib.admin.utils import unquote
from django.db import models
from django.http import Http404
from django.shortcuts import redirect
from django.urls import path, reverse
from safedelete.admin import SafeDeleteAdmin


class DuplicateObjectAdminMixin:
    change_form_template = "admin/duplicate_change_form.html"
    duplicate_param = "_duplicate"

    def get_urls(self):
        urls = super().get_urls()
        opts = self.model._meta
        duplicate_url = [
            path(
                "<path:object_id>/duplicate/",
                self.admin_site.admin_view(self.duplicate_view),
                name=f"{opts.app_label}_{opts.model_name}_duplicate",
            )
        ]
        return duplicate_url + urls

    def duplicate_view(self, request, object_id):
        obj = self.get_object(request, unquote(object_id))
        if obj is None:
            raise Http404
        if not self.has_add_permission(request):
            raise Http404
        add_url = reverse(
            f"admin:{self.model._meta.app_label}_{self.model._meta.model_name}_add"
        )
        return redirect(f"{add_url}?{self.duplicate_param}={obj.pk}")

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        object_id = request.GET.get(self.duplicate_param)
        if not object_id:
            return initial

        obj = self.get_object(request, unquote(object_id))
        if obj is None:
            return initial

        initial.update(self.get_duplicate_initial_data(obj))
        return initial

    def get_duplicate_initial_data(self, obj):
        initial = {}

        for field in self.model._meta.fields:
            if (
                field.primary_key
                or not field.editable
                or isinstance(field, models.FileField)
            ):
                continue
            if isinstance(field, models.ForeignKey):
                initial[field.name] = getattr(obj, field.attname)
            else:
                initial[field.name] = field.value_from_object(obj)

        for field in self.model._meta.many_to_many:
            if not field.editable:
                continue
            initial[field.name] = [
                str(pk) for pk in getattr(obj, field.name).values_list("pk", flat=True)
            ]

        return initial


class GooeyModelAdmin(DuplicateObjectAdminMixin, admin.ModelAdmin):
    pass


class GooeySafeDeleteAdmin(DuplicateObjectAdminMixin, SafeDeleteAdmin):
    pass
