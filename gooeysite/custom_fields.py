from django.db import models


class CustomURLField(models.URLField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("max_length", 2048)
        super().__init__(*args, **kwargs)

    def clean(self, value, model_instance):
        if "://" not in value:
            value = "http://" + value
        return super().clean(value, model_instance)
