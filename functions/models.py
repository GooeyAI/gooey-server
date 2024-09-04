import typing

from django.db import models
from pydantic import BaseModel, Field

from daras_ai_v2.custom_enum import GooeyEnum
from daras_ai_v2.pydantic_validation import FieldHttpUrl


class _TriggerData(typing.NamedTuple):
    label: str
    db_value: int


class FunctionTrigger(_TriggerData, GooeyEnum):
    pre = _TriggerData(label="Before", db_value=1)
    post = _TriggerData(label="After", db_value=2)


class RecipeFunction(BaseModel):
    url: FieldHttpUrl = Field(
        title="URL",
        description="The URL of the [function](https://gooey.ai/functions) to call.",
    )
    trigger: FunctionTrigger.api_choices = Field(
        title="Trigger",
        description="When to run this function. `pre` runs before the recipe, `post` runs after the recipe.",
    )


class CalledFunctionResponse(BaseModel):
    url: str
    trigger: FunctionTrigger.api_choices
    return_value: typing.Any

    @classmethod
    def from_db(cls, called_fn: "CalledFunction") -> "CalledFunctionResponse":
        return cls(
            url=called_fn.function_run.get_app_url(),
            trigger=FunctionTrigger.from_db(called_fn.trigger).name,
            return_value=called_fn.function_run.state.get("return_value"),
        )


class CalledFunction(models.Model):
    saved_run = models.ForeignKey(
        "bots.SavedRun",
        on_delete=models.CASCADE,
        related_name="called_functions",
    )
    function_run = models.ForeignKey(
        "bots.SavedRun",
        on_delete=models.CASCADE,
        related_name="called_by_runs",
    )
    trigger = models.IntegerField(
        choices=FunctionTrigger.db_choices(),
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.saved_run} -> {self.function_run} ({self.trigger})"
