from ai_models.models import AIModelCreator, AIModelSpec, ModelProvider


def run():
    openai = init_llm_creator(
        name="OpenAI",
        website_url="https://openai.com/",
        photo_url="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/ai-model-creators/openai.png",
    )
    google = init_llm_creator(
        name="Google",
        website_url="https://deepmind.google/models/gemini/",
        photo_url="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/ai-model-creators/google.png",
    )
    anthropic = init_llm_creator(
        name="Anthropic",
        website_url="https://www.anthropic.com/",
        photo_url="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/ai-model-creators/anthropic.png",
    )

    # Top 3 latest non-deprecated OpenAI LLMs on prod (by created_at).
    init_llm_model(
        name="gpt_realtime_2",
        creator=openai,
        label="GPT-Realtime 2",
        model_id="gpt-realtime-2",
        provider=ModelProvider.openai_audio,
        llm_context_window=128_000,
        llm_max_output_tokens=32_000,
        llm_is_audio_model=True,
        llm_supports_input_audio=True,
        llm_supports_json=True,
        llm_supports_temperature=False,
    )
    init_llm_model(
        name="gpt_5_5",
        creator=openai,
        label="GPT-5.5 (Thinking)",
        model_id="gpt-5.5-2026-04-23",
        provider=ModelProvider.openai_responses,
        version=5.5,
        llm_context_window=1_050_000,
        llm_max_output_tokens=128_000,
        llm_is_vision_model=True,
        llm_is_thinking_model=True,
        llm_supports_json=True,
        llm_supports_temperature=False,
    )
    init_llm_model(
        name="gpt_realtime_1_5",
        creator=openai,
        label="GPT-Realtime 1.5",
        model_id="gpt-realtime-1.5",
        provider=ModelProvider.openai_audio,
        llm_context_window=32_000,
        llm_max_output_tokens=4_096,
        llm_is_audio_model=True,
        llm_supports_input_audio=True,
        llm_supports_json=True,
        llm_supports_temperature=False,
    )

    # Top 3 latest non-deprecated Google LLMs on prod (by created_at).
    init_llm_model(
        name="gemini_3_5_flash",
        creator=google,
        label="Gemini 3.5 Flash",
        model_id="google/gemini-3.5-flash",
        provider=ModelProvider.openai,
        llm_context_window=1_048_576,
        llm_max_output_tokens=65_536,
        llm_is_vision_model=True,
        llm_is_thinking_model=True,
        llm_supports_input_audio=True,
        llm_supports_json=True,
        llm_supports_temperature=False,
    )
    init_llm_model(
        name="gemini_live_3_1",
        creator=google,
        label="Gemini 3.1 Live (Voice Only)",
        model_id="gemini-3.1-flash-live-preview",
        provider=ModelProvider.google,
        version=3.1,
        llm_context_window=131_072,
        llm_max_output_tokens=65_536,
        llm_is_audio_model=True,
        llm_supports_json=False,
        llm_supports_temperature=False,
    )
    init_llm_model(
        name="gemma-4-26b-a4b-it",
        creator=google,
        label="Gemma 4 26B",
        model_id="google/gemma-4-26b-a4b-it",
        provider=ModelProvider.openai,
        version=4,
        llm_context_window=262_144,
        llm_max_output_tokens=131_072,
        llm_is_vision_model=True,
        llm_is_thinking_model=True,
        llm_supports_temperature=True,
    )

    # Top 3 latest non-deprecated Anthropic LLMs on prod (by created_at).
    init_llm_model(
        name="claude_opus_4_8",
        creator=anthropic,
        label="Claude 4.8 Opus",
        model_id="claude-opus-4-8",
        provider=ModelProvider.openai,
        llm_context_window=1_000_000,
        llm_max_output_tokens=127_999,
        llm_is_vision_model=True,
        llm_is_thinking_model=True,
        llm_supports_json=True,
        llm_supports_temperature=False,
    )
    init_llm_model(
        name="claude_opus_4_7",
        creator=anthropic,
        label="Claude 4.7 Opus",
        model_id="claude-opus-4-7",
        provider=ModelProvider.openai,
        llm_context_window=1_000_000,
        llm_max_output_tokens=128_000,
        llm_is_vision_model=True,
        llm_is_thinking_model=True,
        llm_supports_json=True,
        llm_supports_temperature=False,
    )
    init_llm_model(
        name="claude_4_6_sonnet",
        creator=anthropic,
        label="Claude 4.6 Sonnet",
        model_id="claude-sonnet-4-6",
        provider=ModelProvider.openai,
        llm_context_window=1_000_000,
        llm_max_output_tokens=64_000,
        llm_is_vision_model=True,
        llm_is_thinking_model=True,
        llm_supports_json=True,
        llm_supports_temperature=True,
    )


def init_llm_creator(
    *,
    name: str,
    website_url: str,
    photo_url: str,
) -> AIModelCreator:
    obj, created = AIModelCreator.objects.get_or_create(
        name=name,
        defaults=dict(
            website_url=website_url,
            photo_url=photo_url,
        ),
    )
    if created:
        print("created", obj)
    return obj


def init_llm_model(
    *,
    name: str,
    creator: AIModelCreator,
    label: str,
    model_id: str,
    provider: ModelProvider,
    **kwargs,
) -> AIModelSpec:
    obj, created = AIModelSpec.objects.get_or_create(
        name=name,
        defaults=dict(
            creator=creator,
            label=label,
            model_id=model_id,
            provider=provider,
            category=AIModelSpec.Categories.llm,
            **kwargs,
        ),
    )
    if created:
        print("created", obj)
    return obj
