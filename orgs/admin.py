from django.contrib import admin

from .models import Org, OrgQuerySet, OrgInvitation, OrgMembership


@admin.register(Org)
class OrgAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        return OrgQuerySet(self.model).all()


@admin.register(OrgMembership)
class OrgMembershipAdmin(admin.ModelAdmin):
    pass


@admin.register(OrgInvitation)
class OrgInvitationAdmin(admin.ModelAdmin):
    pass
