import pytest

from ai_models.models import AIModelSpec, ModelProvider
from daras_ai_v2.language_model import (
    AZURE_OPENAI_MODEL_PREFIX,
)
from daras_ai_v2.text_splitter import default_length_function


def test_default_length_function():
    models = []
    for llm in AIModelSpec.objects.filter(
        category=AIModelSpec.Categories.llm, provider=ModelProvider.openai
    ).exclude_deprecated():
        if llm.model_id.startswith(AZURE_OPENAI_MODEL_PREFIX):
            continue
        models.append(llm.model_id)
        assert default_length_function("Hello, World", model=llm.model_id) > 0
