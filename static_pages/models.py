from django.db import models
from django.utils import timezone
import uuid


def zip_file_upload_to(instance, filename):
    # Use the instance's uid to generate the file path
    return f"{instance.uid}/zips/{filename}"


class StaticPage(models.Model):
    uid = models.CharField(default=uuid.uuid1(), editable=False, unique=True)
    name = models.CharField(max_length=100)
    path = models.CharField(max_length=100)
    zip_file = models.FileField(upload_to=zip_file_upload_to, default=None)
    created_at = models.DateTimeField(editable=False, blank=True, default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    disable_page_wrapper = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if not self.uid:
            self.uid = uuid.uuid1()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name
