import pytest

from daras_ai_v2.language_model import (
    LargeLanguageModels,
    LLMApis,
    AZURE_OPENAI_MODEL_PREFIX,
)
from daras_ai_v2.text_splitter import default_length_function


models = []
for llm in LargeLanguageModels:
    if llm.llm_api not in [LLMApis.openai] or llm.is_deprecated:
        continue
    if isinstance(llm.model_id, str):
        models.append(llm.model_id)
        continue
    for model_id in llm.model_id:
        if model_id.startswith(AZURE_OPENAI_MODEL_PREFIX):
            continue
        models.append(model_id)


@pytest.mark.parametrize("model", models)
def test_default_length_function(model: str):
    assert default_length_function("Hello, World", model=model) > 0
