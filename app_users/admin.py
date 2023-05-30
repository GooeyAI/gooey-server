from django.contrib import admin

from app_users import models
from bots.admin_links import open_in_new_tab


# Register your models here.


@admin.register(models.AppUser)
class AppUserAdmin(admin.ModelAdmin):
    list_display = [
        "uid",
        "display_name",
        "email",
        "phone_number",
        "balance",
        "is_anonymous",
        "is_disabled",
        "created_at",
    ]
    list_filter = [
        "is_anonymous",
        "is_disabled",
        "created_at",
    ]
    readonly_fields = [
        "created_at",
        "upgraded_from_anonymous_at",
        "open_in_firebase",
        "open_in_stripe",
    ]

    def open_in_firebase(self, user: models.AppUser):
        path = f"users/{user.uid}"
        return open_in_new_tab(
            f"https://console.firebase.google.com/u/0/project/dara-c1b52/firestore/data/{path}",
            label=path,
        )

    open_in_firebase.short_description = "Open in Firebase"

    def open_in_stripe(self, user: models.AppUser):
        if not user.stripe_customer_id:
            # Try to find the customer ID.
            user.search_stripe_customer()
        if not user.stripe_customer_id:
            # If we still don't have a customer ID, return None.
            raise AttributeError("No Stripe customer ID found.")
        return open_in_new_tab(
            f"https://dashboard.stripe.com/customers/{user.stripe_customer_id}",
            label=user.stripe_customer_id,
        )

    open_in_stripe.short_description = "Open in Stripe"
