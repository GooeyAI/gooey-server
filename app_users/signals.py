# from django.db import transaction
# from django.db.models.signals import post_delete
# from django.dispatch import receiver
# from firebase_admin import auth
#
# from app_users.models import AppUser
#
#
# @receiver(post_delete, sender=AppUser)
# def profile_post_delete(instance: AppUser, **kwargs):
#     if not instance.uid:
#         return
#
#     @transaction.on_commit
#     def _():
#         try:
#             auth.delete_user(instance.uid)
#         except auth.UserNotFoundError:
#             pass

from django.db.models.signals import post_save
from django.dispatch import receiver

from app_users.models import AppUser


@receiver(post_save, sender=AppUser)
def on_AppUser_save(instance: AppUser, **kwargs):
    AppUser.objects.filter(balance__gt=1000, is_paying=False).update(is_paying=True)
