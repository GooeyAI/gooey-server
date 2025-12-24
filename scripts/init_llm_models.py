import typing
from enum import Enum
from django.db import transaction
from ai_models.models import AIModelSpec, ModelProvider


@transaction.atomic
def run():
    agrillm_qwen3_30b = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="agrillm_qwen3_30b",
        label="AgriLLM Qwen-3 30B • ai71",
        model_id="AI71ai/agrillm-Qwen3-30B-A3B",
        provider=ModelProvider.openai,
        llm_context_window=32_768,
        llm_max_output_tokens=4_096,
        llm_supports_json=True,
    )

    # https://platform.publicai.co/api/~endpoints
    apertus_70b_instruct = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="apertus_70b_instruct",
        label="Apertus 70B Instruct • SwissAI via PublicAI",
        model_id="swiss-ai/apertus-70b-instruct",
        provider=ModelProvider.openai,
        llm_context_window=65_536,
        llm_max_output_tokens=4_096,
        llm_supports_json=True,
    )

    # https://docs.sea-lion.ai/models/sea-lion-v4/gemma-sea-lion-v4-27b#usage
    sea_lion_v4_gemma_3_27b_it = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="sea_lion_v4_gemma_3_27b_it",
        label="SEA-LION v4 • aisingapore",
        model_id="aisingapore/Gemma-SEA-LION-v4-27B-IT",
        provider=ModelProvider.openai,
        llm_context_window=128_000,
        llm_max_output_tokens=8_192,
        llm_is_vision_model=True,
        llm_supports_json=True,
    )

    # https://platform.openai.com/docs/models/gpt-5.2
    gpt_5_2 = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="gpt_5_2",
        label="GPT-5.2 • openai",
        model_id="gpt-5.2-2025-12-11",
        provider=ModelProvider.openai,
        llm_context_window=400_000,
        llm_max_output_tokens=128_000,
        llm_is_vision_model=True,
        llm_is_thinking_model=True,
        llm_supports_json=True,
        llm_supports_temperature=False,
        version=5.2,
    )
    # https://platform.openai.com/docs/models/gpt-5.1
    gpt_5_1 = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="gpt_5_1",
        label="GPT-5.1 • openai",
        model_id="gpt-5.1-2025-11-13",
        provider=ModelProvider.openai,
        llm_context_window=400_000,
        llm_max_output_tokens=128_000,
        llm_is_vision_model=True,
        llm_is_thinking_model=True,
        llm_supports_json=True,
        llm_supports_temperature=False,
        version=5.1,
    )
    # https://platform.openai.com/docs/models/gpt-5
    gpt_5 = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="gpt_5",
        label="GPT-5 • openai",
        model_id="gpt-5-2025-08-07",
        provider=ModelProvider.openai,
        llm_context_window=400_000,
        llm_max_output_tokens=128_000,
        llm_is_vision_model=True,
        llm_is_thinking_model=True,
        llm_supports_json=True,
        llm_supports_temperature=False,
        version=5,
    )
    # https://platform.openai.com/docs/models/gpt-5-mini
    gpt_5_mini = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="gpt_5_mini",
        label="GPT-5 Mini • openai",
        model_id="gpt-5-mini-2025-08-07",
        provider=ModelProvider.openai,
        llm_context_window=400_000,
        llm_max_output_tokens=128_000,
        llm_is_vision_model=True,
        llm_is_thinking_model=True,
        llm_supports_json=True,
        llm_supports_temperature=False,
    )
    # https://platform.openai.com/docs/models/gpt-5-nano
    gpt_5_nano = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="gpt_5_nano",
        label="GPT-5 Nano • openai",
        model_id="gpt-5-nano-2025-08-07",
        provider=ModelProvider.openai,
        llm_context_window=400_000,
        llm_max_output_tokens=128_000,
        llm_is_vision_model=True,
        llm_is_thinking_model=True,
        llm_supports_json=True,
        llm_supports_temperature=False,
    )
    # https://platform.openai.com/docs/models/gpt-5-chat-latest
    gpt_5_chat = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="gpt_5_chat",
        label="GPT-5 Chat • openai",
        model_id="gpt-5-chat-latest",
        provider=ModelProvider.openai,
        llm_context_window=128_000,
        llm_max_output_tokens=16_384,
        llm_is_vision_model=True,
        llm_supports_json=True,
        llm_supports_temperature=False,
    )

    # https://platform.openai.com/docs/models/gpt-4-1
    gpt_4_1 = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="gpt_4_1",
        label="GPT-4.1 • openai",
        model_id="gpt-4.1-2025-04-14",
        provider=ModelProvider.openai,
        llm_context_window=1_047_576,
        llm_max_output_tokens=32_768,
        llm_is_vision_model=True,
        llm_supports_json=True,
    )
    gpt_4_1_mini = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="gpt_4_1_mini",
        label="GPT-4.1 Mini • openai",
        model_id="gpt-4.1-mini-2025-04-14",
        provider=ModelProvider.openai,
        llm_context_window=1_047_576,
        llm_max_output_tokens=32_768,
        llm_is_vision_model=True,
        llm_supports_json=True,
    )
    gpt_4_1_nano = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="gpt_4_1_nano",
        label="GPT-4.1 Nano • openai",
        model_id="gpt-4.1-nano-2025-04-14",
        provider=ModelProvider.openai,
        llm_context_window=1_047_576,
        llm_max_output_tokens=32_768,
        llm_is_vision_model=True,
        llm_supports_json=True,
    )

    # https://platform.openai.com/docs/models#gpt-4-5
    gpt_4_5 = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="gpt_4_5",
        label="GPT-4.5 • openai [Redirects to GPT-4.1]",
        model_id="gpt-4.5-preview-2025-02-27",
        provider=ModelProvider.openai,
        llm_context_window=128_000,
        llm_is_vision_model=True,
        llm_supports_json=True,
        is_deprecated=True,
        redirect_to=gpt_4_1,
    )

    # https://platform.openai.com/docs/models/o4-mini
    o4_mini = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="o4_mini",
        label="o4-mini • openai",
        model_id="o4-mini-2025-04-16",
        provider=ModelProvider.openai,
        llm_context_window=200_000,
        llm_max_output_tokens=100_000,
        llm_is_vision_model=True,
        llm_is_thinking_model=True,
        llm_supports_json=True,
        llm_supports_temperature=False,
    )

    # https://platform.openai.com/docs/models/o3
    o3 = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="o3",
        label="o3 • openai",
        model_id="o3-2025-04-16",
        provider=ModelProvider.openai,
        llm_context_window=200_000,
        llm_max_output_tokens=100_000,
        llm_is_vision_model=True,
        llm_is_thinking_model=True,
        llm_supports_json=True,
        llm_supports_temperature=False,
    )

    # https://platform.openai.com/docs/models/o3-mini
    o3_mini = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="o3_mini",
        label="o3-mini • openai",
        model_id=("openai-o3-mini-prod-eastus2-1", "o3-mini-2025-01-31"),
        provider=ModelProvider.openai,
        llm_context_window=200_000,
        llm_max_output_tokens=100_000,
        llm_is_vision_model=False,
        llm_is_thinking_model=True,
        llm_supports_json=True,
        llm_supports_temperature=False,
    )

    # https://platform.openai.com/docs/models#o1
    o1 = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="o1",
        label="o1 • openai [Redirects to o3]",
        model_id=("openai-o1-prod-eastus2-1", "o1-2024-12-17"),
        provider=ModelProvider.openai,
        llm_context_window=200_000,
        llm_max_output_tokens=100_000,
        llm_is_vision_model=True,
        llm_is_thinking_model=True,
        llm_supports_json=True,
        llm_supports_temperature=False,
        is_deprecated=True,
        redirect_to=o3,
    )

    # https://platform.openai.com/docs/models#o1
    o1_preview = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="o1_preview",
        label="o1-preview • openai [Redirects to o3-mini]",
        model_id="o1-preview-2024-09-12",
        provider=ModelProvider.openai,
        llm_context_window=128_000,
        llm_max_output_tokens=32_768,
        llm_is_vision_model=False,
        llm_supports_json=False,
        llm_supports_temperature=False,
        is_deprecated=True,
        redirect_to=o3,
    )

    # https://platform.openai.com/docs/models#o1
    o1_mini = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="o1_mini",
        label="o1-mini • openai [Redirects to o3-mini]",
        model_id=("openai-o1-mini-prod-eastus2-1", "o1-mini-2024-09-12"),
        provider=ModelProvider.openai,
        llm_context_window=128_000,
        llm_max_output_tokens=65_536,
        llm_is_vision_model=False,
        llm_is_thinking_model=True,
        llm_supports_json=False,
        llm_supports_temperature=False,
        is_deprecated=True,
        redirect_to=o3_mini,
    )

    # https://platform.openai.com/docs/models#gpt-4o
    gpt_4_o = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="gpt_4_o",
        label="GPT-4o • openai",
        model_id=("openai-gpt-4o-prod-eastus2-1", "gpt-4o-2024-08-06"),
        provider=ModelProvider.openai,
        llm_context_window=128_000,
        llm_max_output_tokens=16_384,
        llm_is_vision_model=True,
        llm_supports_json=True,
    )
    # https://platform.openai.com/docs/models#gpt-4o-mini
    gpt_4_o_mini = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="gpt_4_o_mini",
        label="GPT-4o-mini • openai",
        model_id=("openai-gpt-4o-mini-prod-eastus2-1", "gpt-4o-mini-2024-07-18"),
        provider=ModelProvider.openai,
        llm_context_window=128_000,
        llm_max_output_tokens=16_384,
        llm_is_vision_model=True,
        llm_supports_json=True,
    )

    # https://platform.openai.com/docs/models/gpt-4o-realtime-preview
    gpt_4_o_audio = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="gpt_4_o_audio",
        label="GPT-4o Audio • openai",
        model_id="gpt-4o-realtime-preview-2025-06-03",
        provider=ModelProvider.openai_audio,
        llm_context_window=128_000,
        llm_max_output_tokens=4_096,
        llm_is_audio_model=True,
        llm_supports_input_audio=True,
    )
    # https://platform.openai.com/docs/models/gpt-4o-realtime-preview
    gpt_realtime = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="gpt_realtime",
        label="GPT-Realtime • openai",
        model_id="gpt-realtime-2025-08-28",
        provider=ModelProvider.openai_audio,
        llm_context_window=32_000,
        llm_max_output_tokens=4_096,
        llm_is_audio_model=True,
        llm_supports_input_audio=True,
        llm_supports_temperature=False,
    )
    # https://platform.openai.com/docs/models/gpt-4o-mini-realtime-preview
    gpt_4_o_mini_audio = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="gpt_4_o_mini_audio",
        label="GPT-4o-mini Audio • openai",
        model_id="gpt-4o-mini-realtime-preview-2024-12-17",
        provider=ModelProvider.openai_audio,
        llm_context_window=128_000,
        llm_max_output_tokens=4_096,
        llm_is_audio_model=True,
        llm_supports_input_audio=True,
    )

    chatgpt_4_o = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="chatgpt_4_o",
        label="ChatGPT-4o • openai 🧪 [Redirects to GPT-4o]",
        model_id="chatgpt-4o-latest",
        provider=ModelProvider.openai,
        llm_context_window=128_000,
        llm_max_output_tokens=16_384,
        llm_is_vision_model=True,
        is_deprecated=True,
        redirect_to=gpt_4_o,
    )
    # https://platform.openai.com/docs/models/gpt-4-turbo-and-gpt-4
    gpt_4_turbo_vision = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="gpt_4_turbo_vision",
        label="GPT-4 Turbo with Vision • openai [Redirects to GPT-4o]",
        model_id=(
            "openai-gpt-4-turbo-2024-04-09-prod-eastus2-1",
            "gpt-4-turbo-2024-04-09",
        ),
        provider=ModelProvider.openai,
        llm_context_window=128_000,
        llm_max_output_tokens=4096,
        llm_is_vision_model=True,
        llm_supports_json=True,
        is_deprecated=True,
        redirect_to=gpt_4_o,
    )
    gpt_4_vision = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="gpt_4_vision",
        label="GPT-4 Vision • openai [Redirects to GPT-4o]",
        model_id="gpt-4-vision-preview",
        provider=ModelProvider.openai,
        llm_context_window=128_000,
        llm_max_output_tokens=4096,
        llm_is_vision_model=True,
        is_deprecated=True,
        redirect_to=gpt_4_o,
    )

    # https://help.openai.com/en/articles/8555510-gpt-4-turbo
    gpt_4_turbo = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="gpt_4_turbo",
        label="GPT-4 Turbo • openai [Redirects to GPT-4o]",
        model_id=("openai-gpt-4-turbo-prod-ca-1", "gpt-4-1106-preview"),
        provider=ModelProvider.openai,
        llm_context_window=128_000,
        llm_max_output_tokens=4096,
        llm_supports_json=True,
        is_deprecated=True,
        redirect_to=gpt_4_o,
    )

    # https://platform.openai.com/docs/models/gpt-4
    gpt_4 = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="gpt_4",
        label="GPT-4 • openai [Redirects to GPT-4o]",
        model_id=("openai-gpt-4-prod-ca-1", "gpt-4"),
        provider=ModelProvider.openai,
        llm_context_window=8192,
        llm_max_output_tokens=8192,
        is_deprecated=True,
        redirect_to=gpt_4_o,
    )
    gpt_4_32k = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="gpt_4_32k",
        label="GPT-4 32K • openai [Redirects to GPT-4o]",
        model_id="openai-gpt-4-32k-prod-ca-1",
        provider=ModelProvider.openai,
        llm_context_window=32_768,
        llm_max_output_tokens=8192,
        is_deprecated=True,
        redirect_to=gpt_4_o,
    )

    # https://platform.openai.com/docs/models/gpt-3-5
    gpt_3_5_turbo = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="gpt_3_5_turbo",
        label="ChatGPT • openai [Redirects to GPT-4o-mini]",
        model_id=("openai-gpt-35-turbo-prod-ca-1", "gpt-3.5-turbo-0613"),
        provider=ModelProvider.openai,
        llm_context_window=4096,
        llm_supports_json=True,
        is_deprecated=True,
        redirect_to=gpt_4_o_mini,
    )
    gpt_3_5_turbo_16k = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="gpt_3_5_turbo_16k",
        label="ChatGPT 16k • openai [Redirects to GPT-4o-mini]",
        model_id=("openai-gpt-35-turbo-16k-prod-ca-1", "gpt-3.5-turbo-16k-0613"),
        provider=ModelProvider.openai,
        llm_context_window=16_384,
        llm_max_output_tokens=4096,
        is_deprecated=True,
        redirect_to=gpt_4_o_mini,
    )
    gpt_3_5_turbo_instruct = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="gpt_3_5_turbo_instruct",
        label="GPT-3.5 Instruct • openai [Redirects to GPT-4o-mini]",
        model_id="gpt-3.5-turbo-instruct",
        provider=ModelProvider.openai,
        llm_context_window=4096,
        llm_is_chat_model=False,
        is_deprecated=True,
        redirect_to=gpt_4_o_mini,
    )

    deepseek_v3p2 = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="deepseek_v3p2",
        label="DeepSeek V3.2 • DeepSeek [Redirects to DeepSeek V3.3]",
        model_id="accounts/fireworks/models/deepseek-v3p2",
        provider=ModelProvider.fireworks,
        llm_context_window=163_800,
        llm_max_output_tokens=20_500,
        llm_supports_json=True,
        llm_is_thinking_model=True,
    )

    deepseek_r1 = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="deepseek_r1",
        label="DeepSeek R1 [Redirects to DeepSeek V3.2]",
        model_id="accounts/fireworks/models/deepseek-r1",
        provider=ModelProvider.fireworks,
        llm_context_window=128_000,
        llm_max_output_tokens=8192,
        llm_supports_json=True,
        is_deprecated=True,
        redirect_to=deepseek_v3p2,
    )

    deepseek_v3p1 = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="deepseek_v3p1",
        label="DeepSeek V3.1 • DeepSeek [Redirects to DeepSeek V3.2]",
        model_id="accounts/fireworks/models/deepseek-v3p1",
        provider=ModelProvider.fireworks,
        llm_context_window=163_800,
        llm_max_output_tokens=20_500,
        llm_supports_json=True,
        llm_is_thinking_model=True,
        is_deprecated=True,
        redirect_to=deepseek_v3p2,
    )
    # https://console.groq.com/docs/models
    llama4_maverick_17b_128e = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="llama4_maverick_17b_128e",
        label="Llama 4 Maverick Instruct • Meta AI [Redirects to Llama 4.2 17B Instruct]",
        model_id="accounts/fireworks/models/llama4-maverick-instruct-basic",
        provider=ModelProvider.fireworks,
        llm_context_window=1_000_000,
        llm_max_output_tokens=16_384,
        llm_supports_json=True,
        llm_is_vision_model=True,
    )
    llama4_scout_17b_16e = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="llama4_scout_17b_16e",
        label="Llama 4 Scout Instruct • Meta AI [Redirects to Llama 4.2 17B Instruct]",
        model_id="accounts/fireworks/models/llama4-scout-instruct-basic",
        provider=ModelProvider.fireworks,
        llm_context_window=128_000,
        llm_max_output_tokens=16_384,
        llm_supports_json=True,
        llm_is_vision_model=True,
    )
    llama3_3_70b = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="llama3_3_70b",
        label="Llama 3.3 70B • Meta AI [Redirects to Llama 4.2 17B Instruct]",
        model_id="llama-3.3-70b-versatile",
        provider=ModelProvider.groq,
        llm_context_window=128_000,
        llm_max_output_tokens=32_768,
        llm_supports_json=True,
        is_deprecated=True,
        redirect_to=llama4_maverick_17b_128e,
    )
    llama3_2_90b_vision = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="llama3_2_90b_vision",
        label="Llama 3.2 90B + Vision • Meta AI [Redirects to Llama 4.2 17B Instruct]",
        model_id="llama-3.2-90b-vision-preview",
        provider=ModelProvider.groq,
        llm_context_window=128_000,
        llm_max_output_tokens=8192,
        llm_supports_json=True,
        llm_is_vision_model=True,
        is_deprecated=True,
        redirect_to=llama4_maverick_17b_128e,
    )
    llama3_2_11b_vision = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="llama3_2_11b_vision",
        label="Llama 3.2 11B + Vision • Meta AI [Redirects to Llama 4.2 17B Instruct]",
        model_id="llama-3.2-11b-vision-preview",
        provider=ModelProvider.groq,
        llm_context_window=128_000,
        llm_max_output_tokens=8192,
        llm_supports_json=True,
        llm_is_vision_model=True,
        is_deprecated=True,
        redirect_to=llama4_maverick_17b_128e,
    )

    llama3_2_3b = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="llama3_2_3b",
        label="Llama 3.2 3B • Meta AI [Redirects to Llama 4.2 17B Instruct]",
        model_id="llama-3.2-3b-preview",
        provider=ModelProvider.groq,
        llm_context_window=128_000,
        llm_max_output_tokens=8192,
        llm_supports_json=True,
        is_deprecated=True,
        redirect_to=llama4_maverick_17b_128e,
    )
    llama3_2_1b = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="llama3_2_1b",
        label="Llama 3.2 1B • Meta AI [Redirects to Llama 4.2 17B Instruct]",
        model_id="llama-3.2-1b-preview",
        provider=ModelProvider.groq,
        llm_context_window=128_000,
        llm_max_output_tokens=8192,
        llm_supports_json=True,
        is_deprecated=True,
        redirect_to=llama4_maverick_17b_128e,
    )

    llama3_1_405b = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="llama3_1_405b",
        label="Llama 3.1 405B • Meta AI [Redirects to Llama 4.2 17B Instruct]",
        model_id="accounts/fireworks/models/llama-v3p1-405b-instruct",
        provider=ModelProvider.fireworks,
        llm_context_window=128_000,
        llm_max_output_tokens=4096,
        llm_supports_json=True,
        is_deprecated=True,
        redirect_to=llama4_maverick_17b_128e,
    )
    llama3_1_70b = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="llama3_1_70b",
        label="Llama 3.1 70B • Meta AI [Redirects to Llama 4.2 17B Instruct]",
        model_id="llama-3.1-70b-versatile",
        provider=ModelProvider.groq,
        llm_context_window=128_000,
        llm_max_output_tokens=4096,
        llm_supports_json=True,
        is_deprecated=True,
        redirect_to=llama4_maverick_17b_128e,
    )
    llama3_1_8b = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="llama3_1_8b",
        label="Llama 3.1 8B • Meta AI [Redirects to Llama 4.2 17B Instruct]",
        model_id="llama-3.1-8b-instant",
        provider=ModelProvider.groq,
        llm_context_window=128_000,
        llm_max_output_tokens=8192,
        llm_supports_json=True,
        is_deprecated=True,
        redirect_to=llama4_maverick_17b_128e,
    )

    llama3_70b = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="llama3_70b",
        label="Llama 3 70B • Meta AI [Redirects to Llama 4.2 17B Instruct]",
        model_id="llama3-70b-8192",
        provider=ModelProvider.groq,
        llm_context_window=8192,
        llm_supports_json=True,
        is_deprecated=True,
        redirect_to=llama4_maverick_17b_128e,
    )
    llama3_8b = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="llama3_8b",
        label="Llama 3 8B • Meta AI [Redirects to Llama 4.2 17B Instruct]",
        model_id="llama3-8b-8192",
        provider=ModelProvider.groq,
        llm_context_window=8192,
        llm_supports_json=True,
        is_deprecated=True,
        redirect_to=llama4_maverick_17b_128e,
    )

    pixtral_large = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="pixtral_large",
        label="Pixtral Large 24/11 • mistral",
        model_id="pixtral-large-2411",
        provider=ModelProvider.mistral,
        llm_context_window=131_000,
        llm_max_output_tokens=4096,
        llm_is_vision_model=True,
        llm_supports_json=True,
    )
    mistral_large = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="mistral_large",
        label="Mistral Large 24/11 • mistral",
        model_id="mistral-large-2411",
        provider=ModelProvider.mistral,
        llm_context_window=131_000,
        llm_max_output_tokens=4096,
        llm_supports_json=True,
    )
    mistral_small_24b_instruct = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="mistral_small_24b_instruct",
        label="Mistral Small 25/01 • mistral",
        model_id="mistral-small-2501",
        provider=ModelProvider.mistral,
        llm_context_window=32_768,
        llm_max_output_tokens=4096,
        llm_supports_json=True,
    )
    mixtral_8x7b_instruct_0_1 = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="mixtral_8x7b_instruct_0_1",
        label="Mixtral 8x7b Instruct v0.1 • mistral [Deprecated]",
        model_id="mixtral-8x7b-32768",
        provider=ModelProvider.groq,
        llm_context_window=32_768,
        llm_max_output_tokens=4096,
        llm_supports_json=True,
        is_deprecated=True,
        redirect_to=mistral_small_24b_instruct,
    )
    gemma_2_9b_it = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="gemma_2_9b_it",
        label="Gemma 2 9B • Google",
        model_id="gemma2-9b-it",
        provider=ModelProvider.groq,
        llm_context_window=8_192,
        llm_max_output_tokens=4096,
        llm_supports_json=True,
    )
    gemma_7b_it = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="gemma_7b_it",
        label="Gemma 7B • Google [Redirects to Gemma 2 9B]",
        model_id="gemma-7b-it",
        provider=ModelProvider.groq,
        llm_context_window=8_192,
        llm_max_output_tokens=4096,
        llm_supports_json=True,
        is_deprecated=True,
        redirect_to=gemma_2_9b_it,
    )

    # https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/3-pro
    gemini_3_pro = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="gemini_3_pro",
        label="Gemini 3 Pro • Google",
        model_id="google/gemini-3-pro-preview",
        provider=ModelProvider.openai,
        llm_context_window=1_048_576,
        llm_max_output_tokens=65_535,
        llm_is_vision_model=True,
        llm_is_thinking_model=True,
        llm_supports_input_audio=True,
        llm_supports_json=True,
        llm_supports_temperature=False,
        version=3,
    )

    # https://cloud.google.com/vertex-ai/docs/generative-ai/learn/models
    gemini_2_5_pro = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="gemini_2_5_pro",
        label="Gemini 2.5 Pro (Google)",
        model_id="google/gemini-2.5-pro",
        provider=ModelProvider.openai,
        llm_context_window=1_048_576,
        llm_max_output_tokens=65_535,
        llm_is_vision_model=True,
        llm_is_thinking_model=True,
        llm_supports_input_audio=True,
        llm_supports_json=True,
    )
    gemini_2_5_flash = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="gemini_2_5_flash",
        label="Gemini 2.5 Flash • Google",
        model_id="google/gemini-2.5-flash",
        provider=ModelProvider.openai,
        llm_context_window=1_048_576,
        llm_max_output_tokens=65_535,
        llm_is_vision_model=True,
        llm_is_thinking_model=True,
        llm_supports_input_audio=True,
        llm_supports_json=True,
    )
    gemini_2_5_flash_lite = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="gemini_2_5_flash_lite",
        label="Gemini 2.5 Flash Lite • Google",
        model_id="google/gemini-2.5-flash-lite",
        provider=ModelProvider.openai,
        llm_context_window=1_048_576,
        llm_max_output_tokens=65_536,
        llm_is_vision_model=True,
        llm_supports_input_audio=True,
        llm_supports_json=True,
    )
    gemini_2_5_pro_preview = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="gemini_2_5_pro_preview",
        label="Gemini 2.5 Pro • Google",
        model_id="google/gemini-2.5-pro-preview-03-25",
        provider=ModelProvider.openai,
        llm_context_window=1_048_576,
        llm_max_output_tokens=65_535,
        llm_is_vision_model=True,
        llm_supports_json=True,
        is_deprecated=True,
        llm_is_thinking_model=True,
        redirect_to=gemini_2_5_pro,
    )
    gemini_2_5_flash_preview = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="gemini_2_5_flash_preview",
        label="Gemini 2.5 Flash • Google [Redirects to Gemini 2.5 Flash]",
        model_id="google/gemini-2.5-flash-preview-04-17",
        provider=ModelProvider.openai,
        llm_context_window=1_048_576,
        llm_max_output_tokens=65_535,
        llm_is_vision_model=True,
        llm_supports_json=True,
        is_deprecated=True,
        llm_is_thinking_model=True,
        redirect_to=gemini_2_5_flash,
    )
    gemini_2_flash_lite = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="gemini_2_flash_lite",
        label="Gemini 2 Flash Lite • Google",
        model_id="google/gemini-2.0-flash-lite",
        provider=ModelProvider.openai,
        llm_context_window=1_048_576,
        llm_max_output_tokens=8192,
        llm_is_vision_model=True,
        llm_supports_input_audio=True,
        llm_supports_json=True,
    )
    gemini_2_flash = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="gemini_2_flash",
        label="Gemini 2 Flash • Google",
        model_id="google/gemini-2.0-flash-001",
        provider=ModelProvider.openai,
        llm_context_window=1_048_576,
        llm_max_output_tokens=8192,
        llm_is_vision_model=True,
        llm_supports_input_audio=True,
        llm_supports_json=True,
    )
    gemini_1_5_flash = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="gemini_1_5_flash",
        label="Gemini 1.5 Flash • Google [Redirects to Gemini 2 Flash]",
        model_id="gemini-1.5-flash",
        provider=ModelProvider.google,
        llm_context_window=1_048_576,
        llm_max_output_tokens=8192,
        llm_is_vision_model=True,
        llm_supports_json=True,
        is_deprecated=True,
        redirect_to=gemini_2_flash,
    )
    gemini_1_5_pro = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="gemini_1_5_pro",
        label="Gemini 1.5 Pro • Google [Redirects to Gemini 2.5 Pro]",
        model_id="gemini-1.5-pro",
        provider=ModelProvider.google,
        llm_context_window=2_097_152,
        llm_max_output_tokens=8192,
        llm_is_vision_model=True,
        llm_supports_json=True,
        is_deprecated=True,
        redirect_to=gemini_2_5_pro,
    )
    gemini_1_pro_vision = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="gemini_1_pro_vision",
        label="Gemini 1.0 Pro Vision • Google",
        model_id="gemini-1.0-pro-vision",
        provider=ModelProvider.google,
        llm_context_window=2048,
        llm_is_vision_model=True,
        llm_is_chat_model=False,
        is_deprecated=True,
        redirect_to=gemini_2_5_pro,
    )
    gemini_1_pro = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="gemini_1_pro",
        label="Gemini 1.0 Pro • Google [Redirects to Gemini 2.5 Pro]",
        model_id="gemini-1.0-pro",
        provider=ModelProvider.google,
        llm_context_window=8192,
        is_deprecated=True,
        redirect_to=gemini_2_5_pro,
    )
    palm2_chat = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="palm2_chat",
        label="PaLM 2 Chat • Google [Redirects to Gemini 2 Flash]",
        model_id="chat-bison",
        provider=ModelProvider.google,
        llm_context_window=4096,
        llm_max_output_tokens=1024,
        is_deprecated=True,
        redirect_to=gemini_2_flash,
    )
    gemini_live = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="gemini_live",
        label="Gemini Live (Voice Only) • Google",
        model_id="gemini-live-2.5-flash-preview-native-audio-09-2025",
        provider=ModelProvider.google,
        llm_context_window=32_000,
        llm_max_output_tokens=64_000,
        llm_is_audio_model=True,
    )
    palm2_text = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="palm2_text",
        label="PaLM 2 Text • Google [Redirects to Gemini 2 Flash]",
        model_id="text-bison",
        provider=ModelProvider.google,
        llm_context_window=8192,
        llm_max_output_tokens=1024,
        llm_is_chat_model=False,
        is_deprecated=True,
        redirect_to=gemini_2_flash,
    )

    # https://docs.anthropic.com/claude/docs/models-overview#model-comparison
    claude_4_5_sonnet = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="claude_4_5_sonnet",
        label="Claude 4.5 Sonnet • Anthropic",
        model_id="claude-sonnet-4-5",
        provider=ModelProvider.openai,
        llm_context_window=200_000,
        llm_max_output_tokens=64_000,
        llm_is_vision_model=True,
        llm_supports_json=True,
        llm_is_thinking_model=True,
    )
    claude_4_1_opus = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="claude_4_1_opus",
        label="Claude 4.1 Opus • Anthropic",
        model_id="claude-opus-4-1",
        provider=ModelProvider.openai,
        llm_context_window=200_000,
        llm_max_output_tokens=32_000,
        llm_is_vision_model=True,
        llm_supports_json=True,
        llm_is_thinking_model=True,
    )
    claude_4_sonnet = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="claude_4_sonnet",
        label="Claude 4 Sonnet • Anthropic [Redirects to Claude 4.5 Sonnet]",
        model_id="claude-4-sonnet-20250514",
        provider=ModelProvider.openai,
        llm_context_window=200_000,
        llm_max_output_tokens=64_000,
        llm_is_vision_model=True,
        llm_supports_json=True,
        llm_is_thinking_model=True,
        is_deprecated=True,
        redirect_to=claude_4_5_sonnet,
    )
    claude_4_opus = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="claude_4_opus",
        label="Claude 4 Opus • Anthropic [Redirects to Claude 4.1 Opus]",
        model_id="claude-4-opus-20250514",
        provider=ModelProvider.openai,
        llm_context_window=200_000,
        llm_max_output_tokens=64_000,
        llm_is_vision_model=True,
        llm_supports_json=True,
        llm_is_thinking_model=True,
        is_deprecated=True,
        redirect_to=claude_4_1_opus,
    )
    claude_3_7_sonnet = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="claude_3_7_sonnet",
        label="Claude 3.7 Sonnet • Anthropic [Redirects to Claude 4.5 Sonnet]",
        model_id="claude-3-7-sonnet-20250219",
        provider=ModelProvider.anthropic,
        llm_context_window=200_000,
        llm_is_vision_model=True,
        llm_supports_json=True,
        llm_is_thinking_model=True,
        is_deprecated=True,
        redirect_to=claude_4_5_sonnet,
    )
    claude_3_5_sonnet = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="claude_3_5_sonnet",
        label="Claude 3.5 Sonnet • Anthropic [Redirects to Claude 4.5 Sonnet]",
        model_id="claude-3-5-sonnet-20241022",
        provider=ModelProvider.anthropic,
        llm_context_window=200_000,
        llm_max_output_tokens=8192,
        llm_is_vision_model=True,
        llm_supports_json=True,
        is_deprecated=True,
        redirect_to=claude_4_5_sonnet,
    )
    claude_3_opus = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="claude_3_opus",
        label="Claude 3 Opus • Anthropic [Redirects to Claude 4.5 Sonnet]",
        model_id="claude-3-opus-20240229",
        provider=ModelProvider.anthropic,
        llm_context_window=200_000,
        llm_max_output_tokens=4096,
        llm_is_vision_model=True,
        llm_supports_json=True,
        is_deprecated=True,
        redirect_to=claude_4_5_sonnet,
    )
    claude_3_sonnet = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="claude_3_sonnet",
        label="Claude 3 Sonnet • Anthropic [Redirects to Claude 4.5 Sonnet]",
        model_id="claude-3-sonnet-20240229",
        provider=ModelProvider.anthropic,
        llm_context_window=200_000,
        llm_max_output_tokens=4096,
        llm_is_vision_model=True,
        llm_supports_json=True,
        is_deprecated=True,
        redirect_to=claude_4_5_sonnet,
    )
    claude_3_haiku = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="claude_3_haiku",
        label="Claude 3 Haiku • Anthropic [Redirects to Claude 4.5 Sonnet]",
        model_id="claude-3-haiku-20240307",
        provider=ModelProvider.anthropic,
        llm_context_window=200_000,
        llm_max_output_tokens=4096,
        llm_is_vision_model=True,
        llm_supports_json=True,
        is_deprecated=True,
        redirect_to=claude_4_5_sonnet,
    )

    afrollama_v1 = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="afrollama_v1",
        label="AfroLlama3 v1 • Jacaranda [Deprecated]",
        model_id="Jacaranda/AfroLlama_V1",
        provider=ModelProvider.aks,
        llm_context_window=2048,
        llm_is_chat_model=False,
        is_deprecated=True,
    )
    llama3_8b_cpt_sea_lion_v2_1_instruct = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="llama3_8b_cpt_sea_lion_v2_1_instruct",
        label="Llama3 8B CPT SEA-LIONv2.1 Instruct • aisingapore",
        model_id="aisingapore/llama3-8b-cpt-sea-lionv2.1-instruct",
        provider=ModelProvider.aks,
        llm_context_window=8192,
    )
    sarvam_2b = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="sarvam_2b",
        label="Sarvam 2B • sarvamai [Deprecated]",
        model_id="sarvamai/sarvam-2b-v0.5",
        provider=ModelProvider.aks,
        llm_context_window=2048,
        is_deprecated=True,
    )
    sarvam_m = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="sarvam_m",
        label="Sarvam M • sarvam.ai",
        model_id="sarvam-m",
        provider=ModelProvider.openai,
        llm_context_window=128_000,
    )

    llama_3_groq_70b_tool_use = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="llama_3_groq_70b_tool_use",
        label="Llama 3 Groq 70b Tool Use [Deprecated]",
        model_id="llama3-groq-70b-8192-tool-use-preview",
        provider=ModelProvider.groq,
        llm_context_window=8192,
        llm_max_output_tokens=4096,
        llm_supports_json=True,
        is_deprecated=True,
    )
    llama_3_groq_8b_tool_use = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="llama_3_groq_8b_tool_use",
        label="Llama 3 Groq 8b Tool Use [Deprecated]",
        model_id="llama3-groq-8b-8192-tool-use-preview",
        provider=ModelProvider.groq,
        llm_context_window=8192,
        llm_max_output_tokens=4096,
        llm_supports_json=True,
        is_deprecated=True,
    )
    llama2_70b_chat = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="llama2_70b_chat",
        label="Llama 2 70B Chat • Meta AI",
        model_id="llama2-70b-4096",
        provider=ModelProvider.groq,
        llm_context_window=4096,
        is_deprecated=True,
    )

    sea_lion_7b_instruct = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="sea_lion_7b_instruct",
        label="SEA-LION-7B-Instruct • aisingapore [Deprecated]",
        model_id="aisingapore/sea-lion-7b-instruct",
        provider=ModelProvider.aks,
        llm_context_window=2048,
        is_deprecated=True,
    )
    llama3_8b_cpt_sea_lion_v2_instruct = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="llama3_8b_cpt_sea_lion_v2_instruct",
        label="Llama3 8B CPT SEA-LIONv2 Instruct • aisingapore [Deprecated]",
        model_id="aisingapore/llama3-8b-cpt-sea-lionv2-instruct",
        provider=ModelProvider.aks,
        llm_context_window=8192,
        is_deprecated=True,
    )

    # https://platform.openai.com/docs/models/gpt-3
    text_davinci_003 = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="text_davinci_003",
        label="GPT-3.5 Davinci-3 • openai [Deprecated]",
        model_id="text-davinci-003",
        provider=ModelProvider.openai,
        llm_context_window=4097,
        is_deprecated=True,
    )
    text_davinci_002 = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="text_davinci_002",
        label="GPT-3.5 Davinci-2 • openai [Deprecated]",
        model_id="text-davinci-002",
        provider=ModelProvider.openai,
        llm_context_window=4097,
        is_deprecated=True,
    )
    code_davinci_002 = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="code_davinci_002",
        label="Codex • openai [Deprecated]",
        model_id="code-davinci-002",
        provider=ModelProvider.openai,
        llm_context_window=8001,
        is_deprecated=True,
    )
    text_curie_001 = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="text_curie_001",
        label="Curie • openai [Deprecated]",
        model_id="text-curie-001",
        provider=ModelProvider.openai,
        llm_context_window=2049,
        is_deprecated=True,
    )
    text_babbage_001 = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="text_babbage_001",
        label="Babbage • openai [Deprecated]",
        model_id="text-babbage-001",
        provider=ModelProvider.openai,
        llm_context_window=2049,
        is_deprecated=True,
    )
    text_ada_001 = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="text_ada_001",
        label="Ada • openai [Deprecated]",
        model_id="text-ada-001",
        provider=ModelProvider.openai,
        llm_context_window=2049,
        is_deprecated=True,
    )
