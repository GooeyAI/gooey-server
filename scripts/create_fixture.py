from django.core.management import call_command

from bots.models import SavedRun


def run():
    qs = SavedRun.objects.filter(run_id__isnull=True).values_list("pk", flat=True)
    pks = ",".join(map(str, qs))
    call_command("dumpdata", "bots.SavedRun", "--pks", pks, "--output", "fixture.json")
