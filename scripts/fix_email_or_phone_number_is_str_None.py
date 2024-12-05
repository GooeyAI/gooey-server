from app_users.models import AppUser
from .migrate_workspaces import update_in_batches


def run():
    fix_email_is_str_None()
    fix_phone_number_is_str_None()


def fix_email_is_str_None():
    qs = AppUser.objects.filter(email="None")
    update_in_batches(qs, email=None)


def fix_phone_number_is_str_None():
    qs = AppUser.objects.filter(phone_number="None")
    update_in_batches(qs, phone_number=None)
