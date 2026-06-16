from scripts import init_local_llm_models
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import IntegrityError

DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_EMAIL = "admin@localhost"
DEFAULT_ADMIN_PASSWORD = "admin"


def run():
    print("==> Running migrations...")
    call_command("migrate")

    print("==> Seeding local LLM models...")
    init_local_llm_models.run()

    print("==> Creating default Django admin user (admin / admin)...")
    ensure_default_admin_user()

    print("==> Done.")


def ensure_default_admin_user():
    User = get_user_model()
    try:
        User.objects.create_superuser(
            DEFAULT_ADMIN_USERNAME,
            DEFAULT_ADMIN_EMAIL,
            DEFAULT_ADMIN_PASSWORD,
        )
    except IntegrityError:
        print("Admin user already exists, skipping.")
        return
    else:
        print("Created admin user. Login at http://localhost:8000 with admin / admin")
