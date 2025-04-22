from daras_ai_v2.language_model import LargeLanguageModels
from usage_costs.models import ModelSku, ModelCategory, ModelProvider, ModelPricing

category = ModelCategory.LLM


def run():
    # gpt-4.1
    llm_pricing_create(
        model_id="gpt-4.1-2025-04-14",
        model_name=LargeLanguageModels.gpt_4_1.name,
        unit_cost_input=2.0,
        unit_cost_output=8.0,
        unit_quantity=10**6,
        provider=ModelProvider.openai,
        pricing_url="https://platform.openai.com/docs/models/gpt-4.1",
    )
    llm_pricing_create(
        model_id="gpt-4.1-mini-2025-04-14",
        model_name=LargeLanguageModels.gpt_4_1_mini.name,
        unit_cost_input=0.4,
        unit_cost_output=1.6,
        unit_quantity=10**6,
        provider=ModelProvider.openai,
        pricing_url="https://platform.openai.com/docs/models/gpt-4.1-mini",
    )
    llm_pricing_create(
        model_id="gpt-4.1-nano-2025-04-14",
        model_name=LargeLanguageModels.gpt_4_1_nano.name,
        unit_cost_input=0.1,
        unit_cost_output=0.4,
        unit_quantity=10**6,
        provider=ModelProvider.openai,
        pricing_url="https://platform.openai.com/docs/models/gpt-4.1-nano",
    )

    # gpt-4.5

    llm_pricing_create(
        model_id="gpt-4.5-preview-2025-02-27",
        model_name=LargeLanguageModels.gpt_4_5.name,
        unit_cost_input=75.00,
        unit_cost_output=37.50,
        unit_quantity=10**6,
        provider=ModelProvider.openai,
        pricing_url="https://openai.com/api/pricing/",
    )

    # o3
    llm_pricing_create(
        model_id="o3-2025-04-16",
        model_name=LargeLanguageModels.o3.name,
        unit_cost_input=10.00,
        unit_cost_output=40.00,
        unit_quantity=10**6,
        provider=ModelProvider.openai,
        pricing_url="https://platform.openai.com/docs/models/o3",
    )

    # o3-mini

    llm_pricing_create(
        model_id="openai-o3-mini-prod-eastus2-1",
        model_name=LargeLanguageModels.o3_mini.name,
        unit_cost_input=1.10,
        unit_cost_output=4.4,
        unit_quantity=10**6,
        provider=ModelProvider.azure_openai,
        pricing_url="https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/",
    )
    llm_pricing_create(
        model_id="o3-mini-2025-01-31",
        model_name=LargeLanguageModels.o3_mini.name,
        unit_cost_input=1.10,
        unit_cost_output=4.4,
        unit_quantity=10**6,
        provider=ModelProvider.openai,
        pricing_url="https://openai.com/api/pricing/",
    )

    # o1

    llm_pricing_create(
        model_id="openai-o1-prod-eastus2-1",
        model_name=LargeLanguageModels.o1.name,
        unit_cost_input=15,
        unit_cost_output=60,
        unit_quantity=10**6,
        provider=ModelProvider.azure_openai,
        pricing_url="https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/",
    )
    llm_pricing_create(
        model_id="o1-2024-12-17",
        model_name=LargeLanguageModels.o1.name,
        unit_cost_input=15,
        unit_cost_output=60,
        unit_quantity=10**6,
        provider=ModelProvider.openai,
        pricing_url="https://openai.com/api/pricing/",
    )

    # o1-preview

    llm_pricing_create(
        model_id="o1-preview-2024-09-12",
        model_name=LargeLanguageModels.o1_preview.name,
        unit_cost_input=15,
        unit_cost_output=60,
        unit_quantity=10**6,
        provider=ModelProvider.openai,
        pricing_url="https://openai.com/api/pricing/",
    )

    # o1-mini

    llm_pricing_create(
        model_id="openai-o1-mini-prod-eastus2-1",
        model_name=LargeLanguageModels.o1_mini.name,
        unit_cost_input=3,
        unit_cost_output=12,
        unit_quantity=10**6,
        provider=ModelProvider.openai,
        pricing_url="https://openai.com/api/pricing/",
    )
    llm_pricing_create(
        model_id="o1-mini-2024-09-12",
        model_name=LargeLanguageModels.o1_mini.name,
        unit_cost_input=3,
        unit_cost_output=12,
        unit_quantity=10**6,
        provider=ModelProvider.openai,
        pricing_url="https://openai.com/api/pricing/",
    )

    # GPT-4o-mini

    llm_pricing_create(
        model_id="openai-gpt-4o-mini-prod-eastus2-1",
        model_name=LargeLanguageModels.gpt_4_o_mini.name,
        unit_cost_input=0.150,
        unit_cost_output=0.600,
        unit_quantity=10**6,
        provider=ModelProvider.openai,
        pricing_url="https://openai.com/api/pricing",
    )
    llm_pricing_create(
        model_id="gpt-4o-mini-2024-07-18",
        model_name=LargeLanguageModels.gpt_4_o_mini.name,
        unit_cost_input=0.150,
        unit_cost_output=0.600,
        unit_quantity=10**6,
        provider=ModelProvider.openai,
        pricing_url="https://openai.com/api/pricing",
    )
    llm_pricing_create(
        model_id="gpt-4o-mini-realtime-preview-2024-12-17",
        model_name=LargeLanguageModels.gpt_4_o_mini_audio.name,
        unit_cost_input=0.150,
        unit_cost_output=0.600,
        unit_quantity=10**6,
        provider=ModelProvider.openai,
        pricing_url="https://platform.openai.com/docs/pricing",
    )

    # GPT-4o

    llm_pricing_create(
        model_id="chatgpt-4o-latest",
        model_name=LargeLanguageModels.chatgpt_4_o.name,
        unit_cost_input=5,
        unit_cost_output=15,
        unit_quantity=10**6,
        provider=ModelProvider.openai,
        pricing_url="https://openai.com/api/pricing",
    )

    llm_pricing_create(
        model_id="openai-gpt-4o-prod-eastus2-1",
        model_name=LargeLanguageModels.gpt_4_o.name,
        unit_cost_input=5,
        unit_cost_output=15,
        unit_quantity=10**6,
        provider=ModelProvider.azure_openai,
        pricing_url="https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/",
    )
    llm_pricing_create(
        model_id="gpt-4o-2024-08-06",
        model_name=LargeLanguageModels.gpt_4_o.name,
        unit_cost_input=2.5,
        unit_cost_output=10,
        unit_quantity=10**6,
        provider=ModelProvider.openai,
        pricing_url="https://openai.com/api/pricing",
    )
    llm_pricing_create(
        model_id="gpt-4o-realtime-preview-2024-12-17",
        model_name=LargeLanguageModels.gpt_4_o_audio.name,
        unit_cost_input=2.5,
        unit_cost_output=10,
        unit_quantity=10**6,
        provider=ModelProvider.openai,
        pricing_url="https://openai.com/api/pricing",
    )

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
                pricing_url="https://openai.com/api/pricing",
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
                pricing_url="https://openai.com/api/pricing",
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
            pricing_url="https://openai.com/api/pricing",
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
            pricing_url="https://openai.com/api/pricing",
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
            pricing_url="https://openai.com/api/pricing",
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
            pricing_url="https://openai.com/api/pricing",
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
            pricing_url="https://openai.com/api/pricing",
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
            pricing_url="https://openai.com/api/pricing",
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
            pricing_url="https://openai.com/api/pricing",
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
            pricing_url="https://openai.com/api/pricing",
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
            pricing_url="https://openai.com/api/pricing",
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
            pricing_url="https://openai.com/api/pricing",
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
            pricing_url="https://openai.com/api/pricing",
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
            pricing_url="https://openai.com/api/pricing",
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
            pricing_url="https://openai.com/api/pricing",
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
            pricing_url="https://openai.com/api/pricing",
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
            pricing_url="https://openai.com/api/pricing",
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
            pricing_url="https://openai.com/api/pricing",
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

    llm_pricing_create(
        model_id="gemini-2.5-pro-preview-03-25",
        model_name=LargeLanguageModels.gemini_2_5_pro_preview.name,
        unit_cost_input=1.25,  # actually 2.5 when len(input) >= 200K
        unit_cost_output=10,  # actually 15 when len(input) >= 200K
        unit_quantity=10**6,
        provider=ModelProvider.google,
        pricing_url="https://ai.google.dev/gemini-api/docs/pricing#gemini-2.5-pro-preview",
    )
    llm_pricing_create(
        model_id="gemini-2.0-flash-lite",
        model_name=LargeLanguageModels.gemini_2_flash_lite.name,
        unit_cost_input=0.075,
        unit_cost_output=0.30,
        unit_quantity=10**6,
        provider=ModelProvider.google,
        pricing_url="https://ai.google.dev/gemini-api/docs/pricing#gemini-2.0-flash-lite",
    )
    llm_pricing_create(
        model_id="gemini-2.0-flash-001",
        model_name=LargeLanguageModels.gemini_2_flash.name,
        unit_cost_input=0.1,
        unit_cost_output=0.4,
        unit_quantity=10**6,
        provider=ModelProvider.google,
        pricing_url="https://ai.google.dev/pricing",
    )
    llm_pricing_create(
        model_id="gemini-1.5-flash",
        model_name=LargeLanguageModels.gemini_1_5_flash.name,
        unit_cost_input=0.075,
        unit_cost_output=0.30,
        unit_quantity=10**6,
        provider=ModelProvider.google,
        pricing_url="https://ai.google.dev/pricing",
    )
    llm_pricing_create(
        model_id="gemini-1.5-pro",
        model_name=LargeLanguageModels.gemini_1_5_pro.name,
        unit_cost_input=3.50,
        unit_cost_output=10.50,
        unit_quantity=10**6,
        provider=ModelProvider.google,
        pricing_url="https://ai.google.dev/pricing",
    )

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

    # groq

    llm_pricing_create(
        model_id="llama-3.3-70b-versatile",
        model_name=LargeLanguageModels.llama3_2_90b_vision.name,
        unit_cost_input=0.59,
        unit_cost_output=0.79,
        unit_quantity=10**6,
        provider=ModelProvider.groq,
        pricing_url="https://groq.com/pricing/",
    )
    llm_pricing_create(
        model_id="llama-3.2-90b-vision-preview",
        model_name=LargeLanguageModels.llama3_2_90b_vision.name,
        unit_cost_input=0.90,
        unit_cost_output=0.90,
        unit_quantity=10**6,
        provider=ModelProvider.groq,
        pricing_url="https://groq.com/pricing/",
    )
    llm_pricing_create(
        model_id="llama-3.2-11b-vision-preview",
        model_name=LargeLanguageModels.llama3_2_11b_vision.name,
        unit_cost_input=0.18,
        unit_cost_output=0.18,
        unit_quantity=10**6,
        provider=ModelProvider.groq,
        pricing_url="https://groq.com/pricing/",
    )

    llm_pricing_create(
        model_id="llama-3.2-3b-preview",
        model_name=LargeLanguageModels.llama3_2_3b.name,
        unit_cost_input=0.06,
        unit_cost_output=0.06,
        unit_quantity=10**6,
        provider=ModelProvider.groq,
        pricing_url="https://groq.com/pricing/",
    )
    llm_pricing_create(
        model_id="llama-3.2-1b-preview",
        model_name=LargeLanguageModels.llama3_2_1b.name,
        unit_cost_input=0.04,
        unit_cost_output=0.04,
        unit_quantity=10**6,
        provider=ModelProvider.groq,
        pricing_url="https://groq.com/pricing/",
    )

    llm_pricing_create(
        model_id="llama-3.1-70b-versatile",
        model_name=LargeLanguageModels.llama3_1_70b.name,
        unit_cost_input=0.59,
        unit_cost_output=0.79,
        unit_quantity=10**6,
        provider=ModelProvider.groq,
        pricing_url="https://groq.com/pricing/",
    )
    llm_pricing_create(
        model_id="llama-3.1-8b-instant",
        model_name=LargeLanguageModels.llama3_1_8b.name,
        unit_cost_input=0.05,
        unit_cost_output=0.08,
        unit_quantity=10**6,
        provider=ModelProvider.groq,
        pricing_url="https://groq.com/pricing/",
    )

    llm_pricing_create(
        model_id="llama3-70b-8192",
        model_name=LargeLanguageModels.llama3_70b.name,
        unit_cost_input=0.59,
        unit_cost_output=0.79,
        unit_quantity=10**6,
        provider=ModelProvider.groq,
        pricing_url="https://wow.groq.com/",
    )
    llm_pricing_create(
        model_id="llama3-groq-70b-8192-tool-use-preview",
        model_name=LargeLanguageModels.llama_3_groq_70b_tool_use.name,
        unit_cost_input=0.59,
        unit_cost_output=0.79,
        unit_quantity=10**6,
        provider=ModelProvider.groq,
        pricing_url="https://wow.groq.com/",
    )
    llm_pricing_create(
        model_id="llama3-8b-8192",
        model_name=LargeLanguageModels.llama3_8b.name,
        unit_cost_input=0.05,
        unit_cost_output=0.1,
        unit_quantity=10**6,
        provider=ModelProvider.groq,
        pricing_url="https://wow.groq.com/",
    )
    llm_pricing_create(
        model_id="llama3-groq-8b-8192-tool-use-preview",
        model_name=LargeLanguageModels.llama_3_groq_8b_tool_use.name,
        unit_cost_input=0.05,
        unit_cost_output=0.1,
        unit_quantity=10**6,
        provider=ModelProvider.groq,
        pricing_url="https://wow.groq.com/",
    )
    llm_pricing_create(
        model_id="llama2-70b-4096",
        model_name=LargeLanguageModels.llama2_70b_chat.name,
        unit_cost_input=0.7,
        unit_cost_output=0.8,
        unit_quantity=10**6,
        provider=ModelProvider.groq,
        pricing_url="https://wow.groq.com/",
    )
    llm_pricing_create(
        model_id="mixtral-8x7b-32768",
        model_name=LargeLanguageModels.mixtral_8x7b_instruct_0_1.name,
        unit_cost_input=0.27,
        unit_cost_output=0.27,
        unit_quantity=10**6,
        provider=ModelProvider.groq,
        pricing_url="https://wow.groq.com/",
    )
    llm_pricing_create(
        model_id="gemma2-9b-it",
        model_name=LargeLanguageModels.gemma_2_9b_it.name,
        unit_cost_input=0.20,
        unit_cost_output=0.20,
        unit_quantity=10**6,
        provider=ModelProvider.groq,
        pricing_url="https://wow.groq.com/",
    )
    llm_pricing_create(
        model_id="gemma-7b-it",
        model_name=LargeLanguageModels.gemma_7b_it.name,
        unit_cost_input=0.1,
        unit_cost_output=0.1,
        unit_quantity=10**6,
        provider=ModelProvider.groq,
        pricing_url="https://wow.groq.com/",
    )

    # Claude

    llm_pricing_create(
        model_id="claude-3-7-sonnet-20250219",
        model_name=LargeLanguageModels.claude_3_7_sonnet.name,
        unit_cost_input=3,
        unit_cost_output=15,
        unit_quantity=10**6,
        provider=ModelProvider.anthropic,
        pricing_url="https://docs.anthropic.com/claude/docs/models-overview#model-comparison",
    )
    llm_pricing_create(
        model_id="claude-3-5-sonnet-20241022",
        model_name=LargeLanguageModels.claude_3_5_sonnet.name,
        unit_cost_input=3,
        unit_cost_output=15,
        unit_quantity=10**6,
        provider=ModelProvider.anthropic,
        pricing_url="https://docs.anthropic.com/claude/docs/models-overview#model-comparison",
    )
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

    # AfroLlama3

    llm_pricing_create(
        model_id="Jacaranda/AfroLlama_V1",
        model_name=LargeLanguageModels.afrollama_v1.name,
        unit_cost_input=5,
        unit_cost_output=15,
        unit_quantity=10**6,
        provider=ModelProvider.aks,
        notes="Same as GPT-4o. Note that the actual cost of this model is in GPU Milliseconds",
    )

    # SEA-LION

    llm_pricing_create(
        model_id="aisingapore/sea-lion-7b-instruct",
        model_name=LargeLanguageModels.sea_lion_7b_instruct.name,
        unit_cost_input=5,
        unit_cost_output=15,
        unit_quantity=10**6,
        provider=ModelProvider.aks,
        notes="Same as GPT-4o. Note that the actual cost of this model is in GPU Milliseconds",
    )
    llm_pricing_create(
        model_id="aisingapore/llama3-8b-cpt-sea-lionv2-instruct",
        model_name=LargeLanguageModels.llama3_8b_cpt_sea_lion_v2_instruct.name,
        unit_cost_input=5,
        unit_cost_output=15,
        unit_quantity=10**6,
        provider=ModelProvider.aks,
        notes="Same as GPT-4o. Note that the actual cost of this model is in GPU Milliseconds",
    )
    llm_pricing_create(
        model_id="aisingapore/llama3-8b-cpt-sea-lionv2.1-instruct",
        model_name=LargeLanguageModels.llama3_8b_cpt_sea_lion_v2_1_instruct.name,
        unit_cost_input=5,
        unit_cost_output=15,
        unit_quantity=10**6,
        provider=ModelProvider.aks,
        notes="Same as GPT-4o. Note that the actual cost of this model is in GPU Milliseconds",
    )

    llm_pricing_create(
        model_id="sarvamai/sarvam-2b-v0.5",
        model_name=LargeLanguageModels.sarvam_2b.name,
        unit_cost_input=5,
        unit_cost_output=15,
        unit_quantity=10**6,
        provider=ModelProvider.aks,
        notes="Same as GPT-4o. Note that the actual cost of this model is in GPU Milliseconds",
    )

    # fireworks

    llm_pricing_create(
        model_id="accounts/fireworks/models/deepseek-r1",
        model_name=LargeLanguageModels.deepseek_r1.name,
        unit_cost_input=3,
        unit_cost_output=8,
        unit_quantity=10**6,
        provider=ModelProvider.groq,
        pricing_url="https://fireworks.ai/pricing",
    )

    llm_pricing_create(
        model_id="accounts/fireworks/models/mistral-small-24b-instruct-2501",
        model_name=LargeLanguageModels.mistral_small_24b_instruct.name,
        unit_cost_input=0.90,
        unit_cost_output=0.90,
        unit_quantity=10**6,
        provider=ModelProvider.fireworks,
        pricing_url="https://fireworks.ai/pricing",
    )

    llm_pricing_create(
        model_id="accounts/fireworks/models/llama4-scout-instruct-basic",
        model_name=LargeLanguageModels.llama4_scout_17b_16e.name,
        unit_cost_input=0.15,
        unit_cost_output=0.60,
        unit_quantity=10**6,
        provider=ModelProvider.fireworks,
        pricing_url="https://fireworks.ai/pricing",
    )
    llm_pricing_create(
        model_id="accounts/fireworks/models/llama4-maverick-instruct-basic",
        model_name=LargeLanguageModels.llama4_maverick_17b_128e.name,
        unit_cost_input=0.22,
        unit_cost_output=0.88,
        unit_quantity=10**6,
        provider=ModelProvider.fireworks,
        pricing_url="https://fireworks.ai/pricing",
    )

    llm_pricing_create(
        model_id="accounts/fireworks/models/llama-v3p1-405b-instruct",
        model_name=LargeLanguageModels.llama3_1_405b.name,
        unit_cost_input=3,
        unit_cost_output=3,
        unit_quantity=10**6,
        provider=ModelProvider.fireworks,
        pricing_url="https://fireworks.ai/pricing",
    )

    # mistral

    llm_pricing_create(
        model_id="pixtral-large-2411",
        model_name=LargeLanguageModels.pixtral_large.name,
        unit_cost_input=2,
        unit_cost_output=6,
        unit_quantity=10**6,
        provider=ModelProvider.mistral,
        pricing_url="https://mistral.ai/en/products/la-plateforme#pricing",
    )
    llm_pricing_create(
        model_id="mistral-large-2411",
        model_name=LargeLanguageModels.mistral_large.name,
        unit_cost_input=2,
        unit_cost_output=6,
        unit_quantity=10**6,
        provider=ModelProvider.mistral,
        pricing_url="https://mistral.ai/en/products/la-plateforme#pricing",
    )
    llm_pricing_create(
        model_id="mistral-small-2501",
        model_name=LargeLanguageModels.mistral_small_24b_instruct.name,
        unit_cost_input=0.1,
        unit_cost_output=0.3,
        unit_quantity=10**6,
        provider=ModelProvider.mistral,
        pricing_url="https://mistral.ai/en/products/la-plateforme#pricing",
    )


def llm_pricing_create(
    model_id: str,
    model_name: str,
    unit_cost_input: float,
    unit_cost_output: float,
    unit_quantity: int,
    provider: ModelProvider,
    pricing_url: str = "",
    notes: str = "",
):
    obj, created = ModelPricing.objects.get_or_create(
        model_id=model_id,
        sku=ModelSku.llm_prompt,
        defaults=dict(
            model_name=model_name,
            unit_cost=unit_cost_input,
            unit_quantity=unit_quantity,
            category=category,
            provider=provider,
            pricing_url=pricing_url,
            notes=notes,
        ),
    )
    if created:
        print("created", obj)
    obj, created = ModelPricing.objects.get_or_create(
        model_id=model_id,
        sku=ModelSku.llm_completion,
        defaults=dict(
            model_name=model_name,
            unit_cost=unit_cost_output,
            unit_quantity=unit_quantity,
            category=category,
            provider=provider,
            pricing_url=pricing_url,
            notes=notes,
        ),
    )
    if created:
        print(f"created {obj}")
