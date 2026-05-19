import threading

from django.db import transaction
from django.db.models.signals import pre_save
from django.dispatch import receiver

from .models import AIModelSpec, ModelProvider


@receiver(pre_save, sender=AIModelSpec)
def sync_fal_pricing_on_model_id_change(instance: AIModelSpec, **kwargs):
    """
    Sync fal pricing into ModelPricing whenever a fal-served AIModelSpec is
    created or its model_id changes.

    The old model_id is read from the DB before this save lands, then the
    actual sync is deferred to `transaction.on_commit` so the row is durable
    before we kick off the network call.
    """
    if instance.provider != ModelProvider.fal_ai:
        return
    if instance.pk:
        old_model_id = (
            AIModelSpec.objects.filter(pk=instance.pk)
            .values_list("model_id", flat=True)
            .first()
        )
    else:
        old_model_id = None
    if instance.model_id == old_model_id:
        return
    transaction.on_commit(
        lambda: _start_sync_fal_pricing_thread(
            pk=instance.pk, model_id=instance.model_id
        )
    )


def _start_sync_fal_pricing_thread(*, pk: int, model_id: str) -> None:
    """
    Spawn a daemon thread to call fal's pricing API and link the resulting
    ModelPricing row to the AIModelSpec. Runs out of band so save() never
    blocks on the network.
    """

    def _run():
        from daras_ai_v2.fal_ai import sync_fal_model_pricing

        pricing = sync_fal_model_pricing(model_id)
        if pricing is None:
            return
        # Use .update() so we don't re-enter this signal handler.
        AIModelSpec.objects.filter(pk=pk).update(pricing=pricing)

    threading.Thread(target=_run, daemon=True).start()
