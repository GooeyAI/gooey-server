import threading

from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from usage_costs.models import ModelCategory

from .models import AIModelSpec, ModelProvider


@receiver(pre_save, sender=AIModelSpec)
def detect_fal_model_id_change(instance: AIModelSpec, **kwargs):
    """Stash whether this save changes the fal-served model_id so the matching
    post_save handler can fire the pricing sync. The old model_id is read from
    the DB before this save lands."""
    instance._fal_model_id_changed = False
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
    instance._fal_model_id_changed = instance.model_id != old_model_id


@receiver(post_save, sender=AIModelSpec)
def sync_fal_pricing_on_model_id_change(instance: AIModelSpec, **kwargs):
    """Sync fal pricing into ModelPricing when pre_save flagged a model_id
    change. Deferred to `transaction.on_commit` so the spec row is durable
    (and `instance.pk` is set) before we hit the network. NOTE: on_commit
    must run from post_save, not pre_save — outside an active transaction it
    fires synchronously, so calling it from pre_save would kick the thread off
    before the INSERT/UPDATE lands."""
    if not getattr(instance, "_fal_model_id_changed", False):
        return
    transaction.on_commit(
        lambda: _start_sync_fal_pricing_thread(
            pk=instance.pk,
            model_id=instance.model_id,
            model_name=instance.name,
            category=_model_pricing_category(instance.category),
        )
    )


def _model_pricing_category(spec_category: int | None) -> int:
    """Map an `AIModelSpec.Categories` value to a `ModelCategory` for the
    `ModelPricing` display column. Falls back to IMAGE_GENERATION when the
    spec category is unset or doesn't map cleanly (display-only field, so a
    soft default is fine)."""
    match spec_category:
        case AIModelSpec.Categories.video:
            return ModelCategory.VIDEO_GENERATION
        case AIModelSpec.Categories.audio:
            return ModelCategory.AUDIO_GENERATION
        case AIModelSpec.Categories.llm:
            return ModelCategory.LLM
        case _:
            return ModelCategory.IMAGE_GENERATION


def _start_sync_fal_pricing_thread(
    *, pk: int, model_id: str, model_name: str, category: int
) -> None:
    """
    Spawn a daemon thread to call fal's pricing API and link the resulting
    ModelPricing row to the AIModelSpec. Runs out of band so save() never
    blocks on the network.
    """

    def _run():
        from daras_ai_v2.fal_ai import sync_fal_model_pricing

        pricing = sync_fal_model_pricing(
            model_id=model_id, model_name=model_name, category=category
        )
        if pricing is None:
            return
        # Use .update() so we don't re-enter this signal handler.
        AIModelSpec.objects.filter(pk=pk).update(pricing=pricing)

    threading.Thread(target=_run, daemon=True).start()
