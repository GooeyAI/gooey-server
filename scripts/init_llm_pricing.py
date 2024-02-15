from daras_ai_v2.language_model import LargeLanguageModels
from usage_costs.models import ModelSku, ModelCategory, ModelProvider, ModelPricing


def run():
    category = ModelCategory.LLM

    # GPT-4-Turbo

    for model in ["gpt-4-0125-preview", "gpt-4-1106-preview"]:
        ModelPricing.objects.create(
            model_id=model,
            model_name=LargeLanguageModels.gpt_4_turbo.name,
            sku=ModelSku.llm_prompt,
            unit_cost=0.01,
            unit_quantity=1000,
            category=category,
            provider=ModelProvider.openai,
            pricing_url="https://openai.com/pricing",
        )
        ModelPricing.objects.create(
            model_id=model,
            model_name=LargeLanguageModels.gpt_4_turbo.name,
            sku=ModelSku.llm_completion,
            unit_cost=0.03,
            unit_quantity=1000,
            category=category,
            provider=ModelProvider.openai,
            pricing_url="https://openai.com/pricing",
        )

    ModelPricing.objects.create(
        model_id="openai-gpt-4-turbo-prod-ca-1",
        model_name=LargeLanguageModels.gpt_4_turbo.name,
        sku=ModelSku.llm_prompt,
        unit_cost=0.01,
        unit_quantity=1000,
        category=category,
        provider=ModelProvider.azure_openai,
        pricing_url="https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/",
    )
    ModelPricing.objects.create(
        model_id="openai-gpt-4-turbo-prod-ca-1",
        model_name=LargeLanguageModels.gpt_4_turbo.name,
        sku=ModelSku.llm_completion,
        unit_cost=0.03,
        unit_quantity=1000,
        category=category,
        provider=ModelProvider.azure_openai,
        pricing_url="https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/",
    )

    #  GPT-4-Turbo-Vision

    ModelPricing.objects.create(
        model_id="gpt-4-vision-preview",
        model_name=LargeLanguageModels.gpt_4_vision.name,
        sku=ModelSku.llm_prompt,
        unit_cost=0.01,
        unit_quantity=1000,
        category=category,
        provider=ModelProvider.openai,
        pricing_url="https://openai.com/pricing",
    )
    ModelPricing.objects.create(
        model_id="gpt-4-vision-preview",
        model_name=LargeLanguageModels.gpt_4_vision.name,
        sku=ModelSku.llm_completion,
        unit_cost=0.03,
        unit_quantity=1000,
        category=category,
        provider=ModelProvider.openai,
        pricing_url="https://openai.com/pricing",
    )

    ModelPricing.objects.create(
        model_id="openai-gpt-4-turbo-vision-prod-ca-1",
        model_name=LargeLanguageModels.gpt_4_vision.name,
        sku=ModelSku.llm_prompt,
        unit_cost=0.01,
        unit_quantity=1000,
        category=category,
        provider=ModelProvider.azure_openai,
        pricing_url="https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/",
    )
    ModelPricing.objects.create(
        model_id="openai-gpt-4-turbo-vision-prod-ca-1",
        model_name=LargeLanguageModels.gpt_4_vision.name,
        sku=ModelSku.llm_completion,
        unit_cost=0.03,
        unit_quantity=1000,
        category=category,
        provider=ModelProvider.azure_openai,
        pricing_url="https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/",
    )

    # GPT-4

    ModelPricing.objects.create(
        model_id="gpt-4",
        model_name=LargeLanguageModels.gpt_4.name,
        sku=ModelSku.llm_prompt,
        unit_cost=0.03,
        unit_quantity=1000,
        category=category,
        provider=ModelProvider.openai,
        pricing_url="https://openai.com/pricing",
    )
    ModelPricing.objects.create(
        model_id="gpt-4",
        model_name=LargeLanguageModels.gpt_4.name,
        sku=ModelSku.llm_completion,
        unit_cost=0.06,
        unit_quantity=1000,
        category=category,
        provider=ModelProvider.openai,
        pricing_url="https://openai.com/pricing",
    )

    ModelPricing.objects.create(
        model_id="openai-gpt-4-prod-ca-1",
        model_name=LargeLanguageModels.gpt_4.name,
        sku=ModelSku.llm_prompt,
        unit_cost=0.03,
        unit_quantity=1000,
        category=category,
        provider=ModelProvider.azure_openai,
        pricing_url="https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/",
    )
    ModelPricing.objects.create(
        model_id="openai-gpt-4-prod-ca-1",
        model_name=LargeLanguageModels.gpt_4.name,
        sku=ModelSku.llm_completion,
        unit_cost=0.06,
        unit_quantity=1000,
        category=category,
        provider=ModelProvider.azure_openai,
        pricing_url="https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/",
    )

    # GPT-4-32k

    ModelPricing.objects.create(
        model_id="gpt-4-32k",
        model_name=LargeLanguageModels.gpt_4_32k.name,
        sku=ModelSku.llm_prompt,
        unit_cost=0.06,
        unit_quantity=1000,
        category=category,
        provider=ModelProvider.openai,
        pricing_url="https://openai.com/pricing",
    )
    ModelPricing.objects.create(
        model_id="gpt-4-32k",
        model_name=LargeLanguageModels.gpt_4_32k.name,
        sku=ModelSku.llm_completion,
        unit_cost=0.12,
        unit_quantity=1000,
        category=category,
        provider=ModelProvider.openai,
        pricing_url="https://openai.com/pricing",
    )

    ModelPricing.objects.create(
        model_id="openai-gpt-4-32k-prod-ca-1",
        model_name=LargeLanguageModels.gpt_4_32k.name,
        sku=ModelSku.llm_prompt,
        unit_cost=0.06,
        unit_quantity=1000,
        category=category,
        provider=ModelProvider.azure_openai,
        pricing_url="https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/",
    )
    ModelPricing.objects.create(
        model_id="openai-gpt-4-32k-prod-ca-1",
        model_name=LargeLanguageModels.gpt_4_32k.name,
        sku=ModelSku.llm_completion,
        unit_cost=0.12,
        unit_quantity=1000,
        category=category,
        provider=ModelProvider.azure_openai,
        pricing_url="https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/",
    )

    # GPT-3.5-Turbo

    ModelPricing.objects.create(
        model_id="gpt-3.5-turbo-0613",
        model_name=LargeLanguageModels.gpt_3_5_turbo.name,
        sku=ModelSku.llm_prompt,
        unit_cost=0.0015,
        unit_quantity=1000,
        category=category,
        provider=ModelProvider.openai,
        pricing_url="https://openai.com/pricing",
    )
    ModelPricing.objects.create(
        model_id="gpt-3.5-turbo-0613",
        model_name=LargeLanguageModels.gpt_3_5_turbo.name,
        sku=ModelSku.llm_completion,
        unit_cost=0.002,
        unit_quantity=1000,
        category=category,
        provider=ModelProvider.openai,
        pricing_url="https://openai.com/pricing",
    )

    ModelPricing.objects.create(
        model_id="openai-gpt-35-turbo-prod-ca-1",
        model_name=LargeLanguageModels.gpt_3_5_turbo.name,
        sku=ModelSku.llm_prompt,
        unit_cost=0.0015,
        unit_quantity=1000,
        category=category,
        provider=ModelProvider.azure_openai,
        pricing_url="https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/",
    )
    ModelPricing.objects.create(
        model_id="openai-gpt-35-turbo-prod-ca-1",
        model_name=LargeLanguageModels.gpt_3_5_turbo.name,
        sku=ModelSku.llm_completion,
        unit_cost=0.002,
        unit_quantity=1000,
        category=category,
        provider=ModelProvider.azure_openai,
        pricing_url="https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/",
    )

    # GPT-3.5-Turbo-16k

    ModelPricing.objects.create(
        model_id="gpt-3.5-turbo-16k-0613",
        model_name=LargeLanguageModels.gpt_3_5_turbo_16k.name,
        sku=ModelSku.llm_prompt,
        unit_cost=0.003,
        unit_quantity=1000,
        category=category,
        provider=ModelProvider.openai,
        pricing_url="https://openai.com/pricing",
    )
    ModelPricing.objects.create(
        model_id="gpt-3.5-turbo-16k-0613",
        model_name=LargeLanguageModels.gpt_3_5_turbo_16k.name,
        sku=ModelSku.llm_completion,
        unit_cost=0.004,
        unit_quantity=1000,
        category=category,
        provider=ModelProvider.openai,
        pricing_url="https://openai.com/pricing",
    )

    ModelPricing.objects.create(
        model_id="openai-gpt-35-turbo-16k-prod-ca-1",
        model_name=LargeLanguageModels.gpt_3_5_turbo_16k.name,
        sku=ModelSku.llm_prompt,
        unit_cost=0.003,
        unit_quantity=1000,
        category=category,
        provider=ModelProvider.azure_openai,
        pricing_url="https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/",
    )
    ModelPricing.objects.create(
        model_id="openai-gpt-35-turbo-16k-prod-ca-1",
        model_name=LargeLanguageModels.gpt_3_5_turbo_16k.name,
        sku=ModelSku.llm_completion,
        unit_cost=0.004,
        unit_quantity=1000,
        category=category,
        provider=ModelProvider.azure_openai,
        pricing_url="https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/",
    )

    # Palm2

    ModelPricing.objects.create(
        model_id="text-bison",
        model_name=LargeLanguageModels.palm2_text.name,
        sku=ModelSku.llm_prompt,
        unit_cost=0.00025,
        unit_quantity=1000,
        category=category,
        provider=ModelProvider.google,
        pricing_url="https://cloud.google.com/vertex-ai/docs/generative-ai/pricing#text_generation",
    )
    ModelPricing.objects.create(
        model_id="text-bison",
        model_name=LargeLanguageModels.palm2_text.name,
        sku=ModelSku.llm_completion,
        unit_cost=0.0005,
        unit_quantity=1000,
        category=category,
        provider=ModelProvider.google,
        pricing_url="https://cloud.google.com/vertex-ai/docs/generative-ai/pricing#text_generation",
    )

    ModelPricing.objects.create(
        model_id="chat-bison",
        model_name=LargeLanguageModels.palm2_chat.name,
        sku=ModelSku.llm_prompt,
        unit_cost=0.00025,
        unit_quantity=1000,
        category=category,
        provider=ModelProvider.google,
        pricing_url="https://cloud.google.com/vertex-ai/docs/generative-ai/pricing#text_generation",
    )
    ModelPricing.objects.create(
        model_id="chat-bison",
        model_name=LargeLanguageModels.palm2_chat.name,
        sku=ModelSku.llm_completion,
        unit_cost=0.0005,
        unit_quantity=1000,
        category=category,
        provider=ModelProvider.google,
        pricing_url="https://cloud.google.com/vertex-ai/docs/generative-ai/pricing#text_generation",
    )

    # Llama2

    ModelPricing.objects.create(
        model_id="togethercomputer/llama-2-70b-chat",
        model_name=LargeLanguageModels.llama2_70b_chat.name,
        sku=ModelSku.llm_prompt,
        unit_cost=0.9,
        unit_quantity=10**6,
        category=category,
        provider=ModelProvider.together_ai,
        pricing_url="https://www.together.ai/pricing",
    )
    ModelPricing.objects.create(
        model_id="togethercomputer/llama-2-70b-chat",
        model_name=LargeLanguageModels.llama2_70b_chat.name,
        sku=ModelSku.llm_completion,
        unit_cost=0.9,
        unit_quantity=10**6,
        category=category,
        provider=ModelProvider.together_ai,
        pricing_url="https://www.together.ai/pricing",
    )
