from django.db import models, transaction
from bots.custom_fields import CustomURLField
import uuid
from asgiref.sync import sync_to_async


class GlossaryResources(models.Model):
    f_url = CustomURLField(unique=True)
    uses = models.IntegerField(default=0)
    last_used = models.DateTimeField(auto_now=True)
    times_locked_for_read = models.IntegerField(default=0)
    glossary_name = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)

    class Meta:
        ordering = ["uses", "last_used"]

    def get_clean_name(self):
        return str(self.glossary_name).lower()


class AsyncAtomic(transaction.Atomic):
    def __init__(self, using=None, savepoint=True, durable=False):
        super().__init__(using, savepoint, durable)

    async def __aenter__(self):
        await sync_to_async(super().__enter__)()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        await sync_to_async(super().__exit__)(exc_type, exc_value, traceback)
