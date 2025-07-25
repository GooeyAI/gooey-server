# Generated by Django 5.1.3 on 2025-07-24 09:38

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("usage_costs", "0032_alter_modelpricing_model_name_alter_modelpricing_sku"),
    ]

    operations = [
        migrations.AlterField(
            model_name="modelpricing",
            name="model_name",
            field=models.CharField(
                choices=[
                    ("gpt_4_1", "GPT-4.1 (openai)"),
                    ("gpt_4_1_mini", "GPT-4.1 Mini (openai)"),
                    ("gpt_4_1_nano", "GPT-4.1 Nano (openai)"),
                    ("gpt_4_5", "GPT-4.5 (openai) [Redirects to GPT-4o (openai)]"),
                    ("o4_mini", "o4-mini (openai)"),
                    ("o3", "o3 (openai)"),
                    ("o3_mini", "o3-mini (openai)"),
                    ("o1", "o1 (openai)"),
                    ("o1_preview", "o1-preview (openai) [Redirects to o1 (openai)]"),
                    ("o1_mini", "o1-mini (openai)"),
                    ("gpt_4_o", "GPT-4o (openai)"),
                    ("gpt_4_o_mini", "GPT-4o-mini (openai)"),
                    ("gpt_4_o_audio", "GPT-4o Audio (openai)"),
                    ("gpt_4_o_mini_audio", "GPT-4o-mini Audio (openai)"),
                    (
                        "chatgpt_4_o",
                        "ChatGPT-4o (openai) 🧪 [Redirects to GPT-4o (openai)]",
                    ),
                    (
                        "gpt_4_turbo_vision",
                        "GPT-4 Turbo with Vision (openai) [Redirects to GPT-4o (openai)]",
                    ),
                    (
                        "gpt_4_vision",
                        "GPT-4 Vision (openai) [Redirects to GPT-4o (openai)]",
                    ),
                    (
                        "gpt_4_turbo",
                        "GPT-4 Turbo (openai) [Redirects to GPT-4o (openai)]",
                    ),
                    ("gpt_4", "GPT-4 (openai) [Redirects to GPT-4o (openai)]"),
                    (
                        "gpt_4_32k",
                        "GPT-4 32K (openai) 🔻 [Redirects to GPT-4o (openai)]",
                    ),
                    (
                        "gpt_3_5_turbo",
                        "ChatGPT (openai) [Redirects to GPT-4o-mini (openai)]",
                    ),
                    (
                        "gpt_3_5_turbo_16k",
                        "ChatGPT 16k (openai) [Redirects to GPT-4o-mini (openai)]",
                    ),
                    (
                        "gpt_3_5_turbo_instruct",
                        "GPT-3.5 Instruct (openai) [Redirects to GPT-4o-mini (openai)]",
                    ),
                    ("deepseek_r1", "DeepSeek R1"),
                    ("llama4_maverick_17b_128e", "Llama 4 Maverick Instruct"),
                    ("llama4_scout_17b_16e", "Llama 4 Scout Instruct"),
                    ("llama3_3_70b", "Llama 3.3 70B"),
                    (
                        "llama3_2_90b_vision",
                        "Llama 3.2 90B + Vision (Meta AI) [Redirects to Llama 4 Maverick Instruct]",
                    ),
                    (
                        "llama3_2_11b_vision",
                        "Llama 3.2 11B + Vision (Meta AI) [Redirects to Llama 4 Maverick Instruct]",
                    ),
                    (
                        "llama3_2_3b",
                        "Llama 3.2 3B (Meta AI) [Redirects to Llama 4 Maverick Instruct]",
                    ),
                    (
                        "llama3_2_1b",
                        "Llama 3.2 1B (Meta AI) [Redirects to Llama 4 Maverick Instruct]",
                    ),
                    (
                        "llama3_1_405b",
                        "Llama 3.1 405B (Meta AI) [Redirects to Llama 4 Maverick Instruct]",
                    ),
                    (
                        "llama3_1_70b",
                        "Llama 3.1 70B (Meta AI) [Redirects to Llama 4 Maverick Instruct]",
                    ),
                    (
                        "llama3_1_8b",
                        "Llama 3.1 8B (Meta AI) [Redirects to Llama 4 Maverick Instruct]",
                    ),
                    (
                        "llama3_70b",
                        "Llama 3 70B (Meta AI) [Redirects to Llama 4 Maverick Instruct]",
                    ),
                    (
                        "llama3_8b",
                        "Llama 3 8B (Meta AI) [Redirects to Llama 4 Maverick Instruct]",
                    ),
                    ("pixtral_large", "Pixtral Large 24/11"),
                    ("mistral_large", "Mistral Large 24/11"),
                    ("mistral_small_24b_instruct", "Mistral Small 25/01"),
                    (
                        "mixtral_8x7b_instruct_0_1",
                        "Mixtral 8x7b Instruct v0.1 [Deprecated] [Redirects to Mistral Small 25/01]",
                    ),
                    ("gemma_2_9b_it", "Gemma 2 9B (Google)"),
                    (
                        "gemma_7b_it",
                        "Gemma 7B (Google) [Redirects to Gemma 2 9B (Google)]",
                    ),
                    ("gemini_2_5_pro", "Gemini 2.5 Pro (Google)"),
                    ("gemini_2_5_flash", "Gemini 2.5 Flash (Google)"),
                    (
                        "gemini_2_5_pro_preview",
                        "Gemini 2.5 Pro (Google) [Redirects to Gemini 2.5 Pro (Google)]",
                    ),
                    (
                        "gemini_2_5_flash_preview",
                        "Gemini 2.5 Flash (Google) [Redirects to Gemini 2.5 Flash (Google)]",
                    ),
                    ("gemini_2_flash_lite", "Gemini 2 Flash Lite (Google)"),
                    ("gemini_2_flash", "Gemini 2 Flash (Google)"),
                    (
                        "gemini_1_5_flash",
                        "Gemini 1.5 Flash (Google) [Redirects to Gemini 2 Flash (Google)]",
                    ),
                    (
                        "gemini_1_5_pro",
                        "Gemini 1.5 Pro (Google) [Redirects to Gemini 2.5 Pro (Google)]",
                    ),
                    (
                        "gemini_1_pro_vision",
                        "Gemini 1.0 Pro Vision (Google) [Redirects to Gemini 2.5 Pro (Google)]",
                    ),
                    (
                        "gemini_1_pro",
                        "Gemini 1.0 Pro (Google) [Redirects to Gemini 2.5 Pro (Google)]",
                    ),
                    (
                        "palm2_chat",
                        "PaLM 2 Chat (Google) [Redirects to Gemini 2 Flash (Google)]",
                    ),
                    (
                        "palm2_text",
                        "PaLM 2 Text (Google) [Redirects to Gemini 2 Flash (Google)]",
                    ),
                    ("claude_4_sonnet", "Claude 4 Sonnet (Anthropic)"),
                    ("claude_4_opus", "Claude 4 Opus (Anthropic)"),
                    ("claude_3_7_sonnet", "Claude 3.7 Sonnet (Anthropic)"),
                    (
                        "claude_3_5_sonnet",
                        "Claude 3.5 Sonnet (Anthropic) [Redirects to Claude 3.7 Sonnet (Anthropic)]",
                    ),
                    (
                        "claude_3_opus",
                        "Claude 3 Opus (Anthropic) [Redirects to Claude 3.7 Sonnet (Anthropic)]",
                    ),
                    (
                        "claude_3_sonnet",
                        "Claude 3 Sonnet (Anthropic) [Redirects to Claude 3.7 Sonnet (Anthropic)]",
                    ),
                    (
                        "claude_3_haiku",
                        "Claude 3 Haiku (Anthropic) [Redirects to Claude 3.7 Sonnet (Anthropic)]",
                    ),
                    (
                        "afrollama_v1",
                        "AfroLlama3 v1 (Jacaranda) [Redirects to GPT-4o-mini (openai)]",
                    ),
                    (
                        "llama3_8b_cpt_sea_lion_v2_1_instruct",
                        "Llama3 8B CPT SEA-LIONv2.1 Instruct (aisingapore)",
                    ),
                    (
                        "sarvam_2b",
                        "Sarvam 2B (sarvamai) [Redirects to GPT-4o-mini (openai)]",
                    ),
                    ("sarvam_m", "Sarvam M (sarvam.ai)"),
                    (
                        "llama_3_groq_70b_tool_use",
                        "Llama 3 Groq 70b Tool Use [Deprecated] [Redirects to GPT-4o-mini (openai)]",
                    ),
                    (
                        "llama_3_groq_8b_tool_use",
                        "Llama 3 Groq 8b Tool Use [Deprecated] [Redirects to GPT-4o-mini (openai)]",
                    ),
                    (
                        "llama2_70b_chat",
                        "Llama 2 70B Chat (Meta AI) [Redirects to GPT-4o-mini (openai)]",
                    ),
                    (
                        "sea_lion_7b_instruct",
                        "SEA-LION-7B-Instruct (aisingapore) [Redirects to GPT-4o-mini (openai)]",
                    ),
                    (
                        "llama3_8b_cpt_sea_lion_v2_instruct",
                        "Llama3 8B CPT SEA-LIONv2 Instruct (aisingapore) [Redirects to GPT-4o-mini (openai)]",
                    ),
                    (
                        "text_davinci_003",
                        "GPT-3.5 Davinci-3 (openai) [Redirects to GPT-4o-mini (openai)]",
                    ),
                    (
                        "text_davinci_002",
                        "GPT-3.5 Davinci-2 (openai) [Redirects to GPT-4o-mini (openai)]",
                    ),
                    (
                        "code_davinci_002",
                        "Codex (openai) [Redirects to GPT-4o-mini (openai)]",
                    ),
                    (
                        "text_curie_001",
                        "Curie (openai) [Redirects to GPT-4o-mini (openai)]",
                    ),
                    (
                        "text_babbage_001",
                        "Babbage (openai) [Redirects to GPT-4o-mini (openai)]",
                    ),
                    (
                        "text_ada_001",
                        "Ada (openai) [Redirects to GPT-4o-mini (openai)]",
                    ),
                    ("protogen_2_2", "Protogen V2.2 (darkstorm2150)"),
                    ("epicdream", "epiCDream [Deprecated] (epinikion)"),
                    ("flux_1_dev", "FLUX.1 [dev]"),
                    ("dream_shaper", "DreamShaper (Lykon)"),
                    ("dreamlike_2", "Dreamlike Photoreal 2.0 (dreamlike.art)"),
                    ("sd_2", "Stable Diffusion v2.1 (stability.ai)"),
                    ("sd_1_5", "Stable Diffusion v1.5 (RunwayML)"),
                    ("dall_e", "DALL·E 2 (OpenAI)"),
                    ("dall_e_3", "DALL·E 3 (OpenAI)"),
                    ("gpt_image_1", "GPT Image 1 (OpenAI)"),
                    ("openjourney_2", "Open Journey v2 beta [Deprecated] (PromptHero)"),
                    ("openjourney", "Open Journey [Deprecated] (PromptHero)"),
                    ("analog_diffusion", "Analog Diffusion [Deprecated] (wavymulder)"),
                    ("protogen_5_3", "Protogen v5.3 [Deprecated] (darkstorm2150)"),
                    ("jack_qiao", "Stable Diffusion v1.4 [Deprecated] (Jack Qiao)"),
                    (
                        "rodent_diffusion_1_5",
                        "Rodent Diffusion 1.5 [Deprecated] (NerdyRodent)",
                    ),
                    ("deepfloyd_if", "DeepFloyd IF [Deprecated] (stability.ai)"),
                    ("flux_pro_kontext", "FLUX.1 Pro Kontext (fal.ai)"),
                    ("dream_shaper", "DreamShaper (Lykon)"),
                    ("dreamlike_2", "Dreamlike Photoreal 2.0 (dreamlike.art)"),
                    ("sd_2", "Stable Diffusion v2.1 (stability.ai)"),
                    ("sd_1_5", "Stable Diffusion v1.5 (RunwayML)"),
                    ("dall_e", "Dall-E (OpenAI)"),
                    ("gpt_image_1", "GPT Image 1 (OpenAI)"),
                    ("instruct_pix2pix", "✨ InstructPix2Pix (Tim Brooks)"),
                    ("openjourney_2", "Open Journey v2 beta [Deprecated] (PromptHero)"),
                    ("openjourney", "Open Journey [Deprecated] (PromptHero)"),
                    ("analog_diffusion", "Analog Diffusion [Deprecated] (wavymulder)"),
                    ("protogen_5_3", "Protogen v5.3 [Deprecated] (darkstorm2150)"),
                    ("jack_qiao", "Stable Diffusion v1.4 [Deprecated] (Jack Qiao)"),
                    (
                        "rodent_diffusion_1_5",
                        "Rodent Diffusion 1.5 [Deprecated] (NerdyRodent)",
                    ),
                    ("sd_2", "Stable Diffusion v2.1 (stability.ai)"),
                    ("runway_ml", "Stable Diffusion v1.5 (RunwayML)"),
                    ("dall_e", "Dall-E (OpenAI)"),
                    ("jack_qiao", "Stable Diffusion v1.4 [Deprecated] (Jack Qiao)"),
                    ("wav2lip", "LipSync (wav2lip)"),
                    ("sadtalker", "LipSync (sadtalker)"),
                ],
                help_text="The name of the model. Only used for Display purposes.",
                max_length=255,
            ),
        ),
        migrations.AlterField(
            model_name="modelpricing",
            name="provider",
            field=models.IntegerField(
                choices=[
                    (1, "OpenAI"),
                    (2, "Google"),
                    (3, "TogetherAI"),
                    (4, "Azure OpenAI"),
                    (6, "Anthropic"),
                    (7, "groq"),
                    (8, "Fireworks AI"),
                    (9, "Mistral AI"),
                    (10, "sarvam.ai"),
                    (11, "fal.ai"),
                    (5, "Azure Kubernetes Service"),
                ],
                help_text="The provider of the model. Only used for Display purposes.",
            ),
        ),
    ]
