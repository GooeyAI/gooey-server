import sys

from django.core import serializers

from bots.models import SavedRun


def run():
    qs = SavedRun.objects.filter(run_id__isnull=True)
    with open("fixture.json", "w") as f:
        serializers.serialize(
            "json",
            get_objects(qs),
            indent=2,
            stream=f,
            progress_output=sys.stdout,
            object_count=qs.count(),
        )


def get_objects(qs):
    for obj in qs:
        obj.parent = None
        yield obj
