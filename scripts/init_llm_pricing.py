from daras_ai_v2.language_model import LargeLanguageModels
from usage_costs.models import ModelSku, ModelCategory, ModelProvider, ModelPricing

category = ModelCategory.LLM


def run():
    # GPT-4-Turbo

    for model in ["gpt-4-0125-preview", "gpt-4-1106-preview"]:
        ModelPricing.objects.get_or_create(
            model_id=model,
            sku=ModelSku.llm_prompt,
            defaults=dict(
                model_name=LargeLanguageModels.gpt_4_turbo.name,
                unit_cost=0.01,
                unit_quantity=1000,
                category=category,
                provider=ModelProvider.openai,
                pricing_url="https://openai.com/pricing",
            ),
        )
        ModelPricing.objects.get_or_create(
            model_id=model,
            sku=ModelSku.llm_completion,
            defaults=dict(
                model_name=LargeLanguageModels.gpt_4_turbo.name,
                unit_cost=0.03,
                unit_quantity=1000,
                category=category,
                provider=ModelProvider.openai,
                pricing_url="https://openai.com/pricing",
            ),
        )

    ModelPricing.objects.get_or_create(
        model_id="openai-gpt-4-turbo-prod-ca-1",
        sku=ModelSku.llm_prompt,
        defaults=dict(
            model_name=LargeLanguageModels.gpt_4_turbo.name,
            unit_cost=0.01,
            unit_quantity=1000,
            category=category,
            provider=ModelProvider.azure_openai,
            pricing_url="https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/",
        ),
    )
    ModelPricing.objects.get_or_create(
        model_id="openai-gpt-4-turbo-prod-ca-1",
        sku=ModelSku.llm_completion,
        defaults=dict(
            model_name=LargeLanguageModels.gpt_4_turbo.name,
            unit_cost=0.03,
            unit_quantity=1000,
            category=category,
            provider=ModelProvider.azure_openai,
            pricing_url="https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/",
        ),
    )

    #  GPT-4-Turbo with Vision

    ModelPricing.objects.get_or_create(
        model_id="gpt-4-turbo-2024-04-09",
        sku=ModelSku.llm_prompt,
        defaults=dict(
            model_name=LargeLanguageModels.gpt_4_turbo_vision.name,
            unit_cost=0.01,
            unit_quantity=1000,
            category=category,
            provider=ModelProvider.openai,
            pricing_url="https://openai.com/pricing",
        ),
    )
    ModelPricing.objects.get_or_create(
        model_id="gpt-4-turbo-2024-04-09",
        sku=ModelSku.llm_completion,
        defaults=dict(
            model_name=LargeLanguageModels.gpt_4_turbo_vision.name,
            unit_cost=0.03,
            unit_quantity=1000,
            category=category,
            provider=ModelProvider.openai,
            pricing_url="https://openai.com/pricing",
        ),
    )

    #  GPT-4-Vision

    ModelPricing.objects.get_or_create(
        model_id="gpt-4-vision-preview",
        sku=ModelSku.llm_prompt,
        defaults=dict(
            model_name=LargeLanguageModels.gpt_4_vision.name,
            unit_cost=0.01,
            unit_quantity=1000,
            category=category,
            provider=ModelProvider.openai,
            pricing_url="https://openai.com/pricing",
        ),
    )
    ModelPricing.objects.get_or_create(
        model_id="gpt-4-vision-preview",
        sku=ModelSku.llm_completion,
        defaults=dict(
            model_name=LargeLanguageModels.gpt_4_vision.name,
            unit_cost=0.03,
            unit_quantity=1000,
            category=category,
            provider=ModelProvider.openai,
            pricing_url="https://openai.com/pricing",
        ),
    )

    # GPT-4

    ModelPricing.objects.get_or_create(
        model_id="gpt-4",
        sku=ModelSku.llm_prompt,
        defaults=dict(
            model_name=LargeLanguageModels.gpt_4.name,
            unit_cost=0.03,
            unit_quantity=1000,
            category=category,
            provider=ModelProvider.openai,
            pricing_url="https://openai.com/pricing",
        ),
    )
    ModelPricing.objects.get_or_create(
        model_id="gpt-4",
        sku=ModelSku.llm_completion,
        defaults=dict(
            model_name=LargeLanguageModels.gpt_4.name,
            unit_cost=0.06,
            unit_quantity=1000,
            category=category,
            provider=ModelProvider.openai,
            pricing_url="https://openai.com/pricing",
        ),
    )

    ModelPricing.objects.get_or_create(
        model_id="openai-gpt-4-prod-ca-1",
        sku=ModelSku.llm_prompt,
        defaults=dict(
            model_name=LargeLanguageModels.gpt_4.name,
            unit_cost=0.03,
            unit_quantity=1000,
            category=category,
            provider=ModelProvider.azure_openai,
            pricing_url="https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/",
        ),
    )
    ModelPricing.objects.get_or_create(
        model_id="openai-gpt-4-prod-ca-1",
        sku=ModelSku.llm_completion,
        defaults=dict(
            model_name=LargeLanguageModels.gpt_4.name,
            unit_cost=0.06,
            unit_quantity=1000,
            category=category,
            provider=ModelProvider.azure_openai,
            pricing_url="https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/",
        ),
    )

    # GPT-4-32k

    ModelPricing.objects.get_or_create(
        model_id="gpt-4-32k",
        sku=ModelSku.llm_prompt,
        defaults=dict(
            model_name=LargeLanguageModels.gpt_4_32k.name,
            unit_cost=0.06,
            unit_quantity=1000,
            category=category,
            provider=ModelProvider.openai,
            pricing_url="https://openai.com/pricing",
        ),
    )
    ModelPricing.objects.get_or_create(
        model_id="gpt-4-32k",
        sku=ModelSku.llm_completion,
        defaults=dict(
            model_name=LargeLanguageModels.gpt_4_32k.name,
            unit_cost=0.12,
            unit_quantity=1000,
            category=category,
            provider=ModelProvider.openai,
            pricing_url="https://openai.com/pricing",
        ),
    )

    ModelPricing.objects.get_or_create(
        model_id="openai-gpt-4-32k-prod-ca-1",
        sku=ModelSku.llm_prompt,
        defaults=dict(
            model_name=LargeLanguageModels.gpt_4_32k.name,
            unit_cost=0.06,
            unit_quantity=1000,
            category=category,
            provider=ModelProvider.azure_openai,
            pricing_url="https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/",
        ),
    )
    ModelPricing.objects.get_or_create(
        model_id="openai-gpt-4-32k-prod-ca-1",
        sku=ModelSku.llm_completion,
        defaults=dict(
            model_name=LargeLanguageModels.gpt_4_32k.name,
            unit_cost=0.12,
            unit_quantity=1000,
            category=category,
            provider=ModelProvider.azure_openai,
            pricing_url="https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/",
        ),
    )

    # GPT-3.5 Turbo Instruct

    ModelPricing.objects.get_or_create(
        model_id="gpt-3.5-turbo-instruct",
        sku=ModelSku.llm_prompt,
        defaults=dict(
            model_name=LargeLanguageModels.gpt_3_5_turbo_instruct.name,
            unit_cost=0.0015,
            unit_quantity=1000,
            category=category,
            provider=ModelProvider.openai,
            pricing_url="https://openai.com/pricing",
        ),
    )
    ModelPricing.objects.get_or_create(
        model_id="gpt-3.5-turbo-instruct",
        sku=ModelSku.llm_completion,
        defaults=dict(
            model_name=LargeLanguageModels.gpt_3_5_turbo_instruct.name,
            unit_cost=0.0020,
            unit_quantity=1000,
            category=category,
            provider=ModelProvider.openai,
            pricing_url="https://openai.com/pricing",
        ),
    )

    # Updated GPT-3.5-Turbo

    ModelPricing.objects.get_or_create(
        model_id="gpt-3.5-turbo-0125",
        sku=ModelSku.llm_prompt,
        defaults=dict(
            model_name=LargeLanguageModels.gpt_3_5_turbo.name,
            unit_cost=0.0005,
            unit_quantity=1000,
            category=category,
            provider=ModelProvider.openai,
            pricing_url="https://openai.com/pricing",
        ),
    )
    ModelPricing.objects.get_or_create(
        model_id="gpt-3.5-turbo-0125",
        sku=ModelSku.llm_completion,
        defaults=dict(
            model_name=LargeLanguageModels.gpt_3_5_turbo.name,
            unit_cost=0.0015,
            unit_quantity=1000,
            category=category,
            provider=ModelProvider.openai,
            pricing_url="https://openai.com/pricing",
        ),
    )

    # GPT-3.5-Turbo

    ModelPricing.objects.get_or_create(
        model_id="gpt-3.5-turbo-0613",
        sku=ModelSku.llm_prompt,
        defaults=dict(
            model_name=LargeLanguageModels.gpt_3_5_turbo.name,
            unit_cost=0.0015,
            unit_quantity=1000,
            category=category,
            provider=ModelProvider.openai,
            pricing_url="https://openai.com/pricing",
        ),
    )
    ModelPricing.objects.get_or_create(
        model_id="gpt-3.5-turbo-0613",
        sku=ModelSku.llm_completion,
        defaults=dict(
            model_name=LargeLanguageModels.gpt_3_5_turbo.name,
            unit_cost=0.002,
            unit_quantity=1000,
            category=category,
            provider=ModelProvider.openai,
            pricing_url="https://openai.com/pricing",
        ),
    )

    ModelPricing.objects.get_or_create(
        model_id="openai-gpt-35-turbo-prod-ca-1",
        sku=ModelSku.llm_prompt,
        defaults=dict(
            model_name=LargeLanguageModels.gpt_3_5_turbo.name,
            unit_cost=0.0015,
            unit_quantity=1000,
            category=category,
            provider=ModelProvider.azure_openai,
            pricing_url="https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/",
        ),
    )
    ModelPricing.objects.get_or_create(
        model_id="openai-gpt-35-turbo-prod-ca-1",
        sku=ModelSku.llm_completion,
        defaults=dict(
            model_name=LargeLanguageModels.gpt_3_5_turbo.name,
            unit_cost=0.002,
            unit_quantity=1000,
            category=category,
            provider=ModelProvider.azure_openai,
            pricing_url="https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/",
        ),
    )

    # GPT-3.5-Turbo-16k

    ModelPricing.objects.get_or_create(
        model_id="gpt-3.5-turbo-16k-0613",
        sku=ModelSku.llm_prompt,
        defaults=dict(
            model_name=LargeLanguageModels.gpt_3_5_turbo_16k.name,
            unit_cost=0.003,
            unit_quantity=1000,
            category=category,
            provider=ModelProvider.openai,
            pricing_url="https://openai.com/pricing",
        ),
    )
    ModelPricing.objects.get_or_create(
        model_id="gpt-3.5-turbo-16k-0613",
        sku=ModelSku.llm_completion,
        defaults=dict(
            model_name=LargeLanguageModels.gpt_3_5_turbo_16k.name,
            unit_cost=0.004,
            unit_quantity=1000,
            category=category,
            provider=ModelProvider.openai,
            pricing_url="https://openai.com/pricing",
        ),
    )

    ModelPricing.objects.get_or_create(
        model_id="openai-gpt-35-turbo-16k-prod-ca-1",
        sku=ModelSku.llm_prompt,
        defaults=dict(
            model_name=LargeLanguageModels.gpt_3_5_turbo_16k.name,
            unit_cost=0.003,
            unit_quantity=1000,
            category=category,
            provider=ModelProvider.azure_openai,
            pricing_url="https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/",
        ),
    )
    ModelPricing.objects.get_or_create(
        model_id="openai-gpt-35-turbo-16k-prod-ca-1",
        sku=ModelSku.llm_completion,
        defaults=dict(
            model_name=LargeLanguageModels.gpt_3_5_turbo_16k.name,
            unit_cost=0.004,
            unit_quantity=1000,
            category=category,
            provider=ModelProvider.azure_openai,
            pricing_url="https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/",
        ),
    )

    # Gemini

    ModelPricing.objects.get_or_create(
        model_id="gemini-1.0-pro",
        sku=ModelSku.llm_prompt,
        defaults=dict(
            model_name=LargeLanguageModels.gemini_1_pro.name,
            unit_cost=0.000125,
            unit_quantity=1000,
            category=category,
            provider=ModelProvider.google,
            pricing_url="https://cloud.google.com/vertex-ai/docs/generative-ai/pricing#text_generation",
        ),
    )
    ModelPricing.objects.get_or_create(
        model_id="gemini-1.0-pro",
        sku=ModelSku.llm_completion,
        defaults=dict(
            model_name=LargeLanguageModels.gemini_1_pro.name,
            unit_cost=0.000375,
            unit_quantity=1000,
            category=category,
            provider=ModelProvider.google,
            pricing_url="https://cloud.google.com/vertex-ai/docs/generative-ai/pricing#text_generation",
        ),
    )

    ModelPricing.objects.get_or_create(
        model_id="gemini-1.0-pro-vision",
        sku=ModelSku.llm_prompt,
        defaults=dict(
            model_name=LargeLanguageModels.gemini_1_pro_vision.name,
            unit_cost=0.000125,
            unit_quantity=1000,
            category=category,
            provider=ModelProvider.google,
            pricing_url="https://cloud.google.com/vertex-ai/docs/generative-ai/pricing#text_generation",
        ),
    )
    ModelPricing.objects.get_or_create(
        model_id="gemini-1.0-pro-vision",
        sku=ModelSku.llm_completion,
        defaults=dict(
            model_name=LargeLanguageModels.gemini_1_pro_vision.name,
            unit_cost=0.000375,
            unit_quantity=1000,
            category=category,
            provider=ModelProvider.google,
            pricing_url="https://cloud.google.com/vertex-ai/docs/generative-ai/pricing#text_generation",
        ),
    )

    # Palm2

    ModelPricing.objects.get_or_create(
        model_id="text-bison",
        sku=ModelSku.llm_prompt,
        defaults=dict(
            model_name=LargeLanguageModels.palm2_text.name,
            unit_cost=0.00025,
            unit_quantity=1000,
            category=category,
            provider=ModelProvider.google,
            pricing_url="https://cloud.google.com/vertex-ai/docs/generative-ai/pricing#text_generation",
        ),
    )
    ModelPricing.objects.get_or_create(
        model_id="text-bison",
        sku=ModelSku.llm_completion,
        defaults=dict(
            model_name=LargeLanguageModels.palm2_text.name,
            unit_cost=0.0005,
            unit_quantity=1000,
            category=category,
            provider=ModelProvider.google,
            pricing_url="https://cloud.google.com/vertex-ai/docs/generative-ai/pricing#text_generation",
        ),
    )

    ModelPricing.objects.get_or_create(
        model_id="chat-bison",
        sku=ModelSku.llm_prompt,
        defaults=dict(
            model_name=LargeLanguageModels.palm2_chat.name,
            unit_cost=0.00025,
            unit_quantity=1000,
            category=category,
            provider=ModelProvider.google,
            pricing_url="https://cloud.google.com/vertex-ai/docs/generative-ai/pricing#text_generation",
        ),
    )
    ModelPricing.objects.get_or_create(
        model_id="chat-bison",
        sku=ModelSku.llm_completion,
        defaults=dict(
            model_name=LargeLanguageModels.palm2_chat.name,
            unit_cost=0.0005,
            unit_quantity=1000,
            category=category,
            provider=ModelProvider.google,
            pricing_url="https://cloud.google.com/vertex-ai/docs/generative-ai/pricing#text_generation",
        ),
    )

    # Llama2

    ModelPricing.objects.get_or_create(
        model_id="togethercomputer/llama-2-70b-chat",
        sku=ModelSku.llm_prompt,
        defaults=dict(
            model_name=LargeLanguageModels.llama2_70b_chat.name,
            unit_cost=0.9,
            unit_quantity=10**6,
            category=category,
            provider=ModelProvider.together_ai,
            pricing_url="https://www.together.ai/pricing",
        ),
    )
    ModelPricing.objects.get_or_create(
        model_id="togethercomputer/llama-2-70b-chat",
        sku=ModelSku.llm_completion,
        defaults=dict(
            model_name=LargeLanguageModels.llama2_70b_chat.name,
            unit_cost=0.9,
            unit_quantity=10**6,
            category=category,
            provider=ModelProvider.together_ai,
            pricing_url="https://www.together.ai/pricing",
        ),
    )

    # Claude

    llm_pricing_create(
        model_id="claude-3-opus-20240229",
        model_name=LargeLanguageModels.claude_3_opus.name,
        unit_cost_input=15,
        unit_cost_output=75,
        unit_quantity=10**6,
        provider=ModelProvider.anthropic,
        pricing_url="https://docs.anthropic.com/claude/docs/models-overview#model-comparison",
    )
    llm_pricing_create(
        model_id="claude-3-sonnet-20240229",
        model_name=LargeLanguageModels.claude_3_sonnet.name,
        unit_cost_input=3,
        unit_cost_output=15,
        unit_quantity=10**6,
        provider=ModelProvider.anthropic,
        pricing_url="https://docs.anthropic.com/claude/docs/models-overview#model-comparison",
    )
    llm_pricing_create(
        model_id="claude-3-haiku-20240307",
        model_name=LargeLanguageModels.claude_3_haiku.name,
        unit_cost_input=0.25,
        unit_cost_output=1.25,
        unit_quantity=10**6,
        provider=ModelProvider.anthropic,
        pricing_url="https://docs.anthropic.com/claude/docs/models-overview#model-comparison",
    )


def llm_pricing_create(
    model_id: str,
    model_name: str,
    unit_cost_input: float,
    unit_cost_output: float,
    unit_quantity: int,
    provider: ModelProvider,
    pricing_url: str,
):
    ModelPricing.objects.get_or_create(
        model_id=model_id,
        sku=ModelSku.llm_prompt,
        defaults=dict(
            model_name=model_name,
            unit_cost=unit_cost_input,
            unit_quantity=unit_quantity,
            category=category,
            provider=provider,
            pricing_url=pricing_url,
        ),
    )
    ModelPricing.objects.get_or_create(
        model_id=model_id,
        sku=ModelSku.llm_completion,
        defaults=dict(
            model_name=model_name,
            unit_cost=unit_cost_output,
            unit_quantity=unit_quantity,
            category=category,
            provider=provider,
            pricing_url=pricing_url,
        ),
    )
