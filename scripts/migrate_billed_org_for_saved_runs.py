from django.db.models import F, Subquery, OuterRef
from django.db import transaction

from bots.models import SavedRun
from orgs.models import Org


def run():
    # Start a transaction to ensure atomicity
    with transaction.atomic():
        # Perform the update where 'uid' matches a valid 'org_id' in the 'Org' table
        SavedRun.objects.filter(
            billed_org_id__isnull=True, uid__in=Org.objects.values("org_id")
        ).update(
            billed_org_id=Subquery(
                Org.objects.filter(org_id=OuterRef("uid")).values("id")[:1]
            )
        )
