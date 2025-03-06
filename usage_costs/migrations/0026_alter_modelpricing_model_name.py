# Generated by Django 5.1.3 on 2025-03-06 01:48

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('usage_costs', '0025_alter_modelpricing_model_name_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='modelpricing',
            name='model_name',
            field=models.CharField(choices=[('gpt_4_5', 'GPT-4.5 (openai)'), ('o3_mini', 'o3-mini (openai)'), ('o1', 'o1 (openai)'), ('o1_preview', 'o1-preview (openai) [Deprecated]'), ('o1_mini', 'o1-mini (openai)'), ('gpt_4_o', 'GPT-4o (openai)'), ('gpt_4_o_mini', 'GPT-4o-mini (openai)'), ('chatgpt_4_o', 'ChatGPT-4o (openai) 🧪'), ('gpt_4_turbo_vision', 'GPT-4 Turbo with Vision (openai)'), ('gpt_4_vision', 'GPT-4 Vision (openai) [Deprecated]'), ('gpt_4_turbo', 'GPT-4 Turbo (openai)'), ('gpt_4', 'GPT-4 (openai)'), ('gpt_4_32k', 'GPT-4 32K (openai) 🔻'), ('gpt_3_5_turbo', 'ChatGPT (openai)'), ('gpt_3_5_turbo_16k', 'ChatGPT 16k (openai)'), ('gpt_3_5_turbo_instruct', 'GPT-3.5 Instruct (openai) 🔻'), ('deepseek_r1', 'DeepSeek R1'), ('llama3_3_70b', 'Llama 3.3 70B'), ('llama3_2_90b_vision', 'Llama 3.2 90B + Vision (Meta AI)'), ('llama3_2_11b_vision', 'Llama 3.2 11B + Vision (Meta AI)'), ('llama3_2_3b', 'Llama 3.2 3B (Meta AI)'), ('llama3_2_1b', 'Llama 3.2 1B (Meta AI)'), ('llama3_1_405b', 'Llama 3.1 405B (Meta AI)'), ('llama3_1_70b', 'Llama 3.1 70B (Meta AI) [Deprecated]'), ('llama3_1_8b', 'Llama 3.1 8B (Meta AI)'), ('llama3_70b', 'Llama 3 70B (Meta AI)'), ('llama3_8b', 'Llama 3 8B (Meta AI)'), ('pixtral_large', 'Pixtral Large 24/11'), ('mistral_large', 'Mistral Large 24/11'), ('mistral_small_24b_instruct', 'Mistral Small 25/01'), ('mixtral_8x7b_instruct_0_1', 'Mixtral 8x7b Instruct v0.1 [Deprecated]'), ('gemma_2_9b_it', 'Gemma 2 9B (Google)'), ('gemma_7b_it', 'Gemma 7B (Google) [Deprecated]'), ('gemini_2_flash', 'Gemini 2 Flash (Google)'), ('gemini_1_5_flash', 'Gemini 1.5 Flash (Google)'), ('gemini_1_5_pro', 'Gemini 1.5 Pro (Google)'), ('gemini_1_pro_vision', 'Gemini 1.0 Pro Vision (Google)'), ('gemini_1_pro', 'Gemini 1.0 Pro (Google)'), ('palm2_chat', 'PaLM 2 Chat (Google)'), ('palm2_text', 'PaLM 2 Text (Google)'), ('claude_3_7_sonnet', 'Claude 3.7 Sonnet (Anthropic)'), ('claude_3_5_sonnet', 'Claude 3.5 Sonnet (Anthropic)'), ('claude_3_opus', 'Claude 3 Opus [L] (Anthropic)'), ('claude_3_sonnet', 'Claude 3 Sonnet [M] (Anthropic)'), ('claude_3_haiku', 'Claude 3 Haiku [S] (Anthropic)'), ('afrollama_v1', 'AfroLlama3 v1 (Jacaranda)'), ('llama3_8b_cpt_sea_lion_v2_1_instruct', 'Llama3 8B CPT SEA-LIONv2.1 Instruct (aisingapore)'), ('sarvam_2b', 'Sarvam 2B (sarvamai)'), ('llama_3_groq_70b_tool_use', 'Llama 3 Groq 70b Tool Use [Deprecated]'), ('llama_3_groq_8b_tool_use', 'Llama 3 Groq 8b Tool Use [Deprecated]'), ('llama2_70b_chat', 'Llama 2 70B Chat [Deprecated] (Meta AI)'), ('sea_lion_7b_instruct', 'SEA-LION-7B-Instruct [Deprecated] (aisingapore)'), ('llama3_8b_cpt_sea_lion_v2_instruct', 'Llama3 8B CPT SEA-LIONv2 Instruct [Deprecated] (aisingapore)'), ('text_davinci_003', 'GPT-3.5 Davinci-3 [Deprecated] (openai)'), ('text_davinci_002', 'GPT-3.5 Davinci-2 [Deprecated] (openai)'), ('code_davinci_002', 'Codex [Deprecated] (openai)'), ('text_curie_001', 'Curie [Deprecated] (openai)'), ('text_babbage_001', 'Babbage [Deprecated] (openai)'), ('text_ada_001', 'Ada [Deprecated] (openai)'), ('protogen_2_2', 'Protogen V2.2 (darkstorm2150)'), ('epicdream', 'epiCDream (epinikion)'), ('flux_1_dev', 'FLUX.1 [dev]'), ('dream_shaper', 'DreamShaper (Lykon)'), ('dreamlike_2', 'Dreamlike Photoreal 2.0 (dreamlike.art)'), ('sd_2', 'Stable Diffusion v2.1 (stability.ai)'), ('sd_1_5', 'Stable Diffusion v1.5 (RunwayML)'), ('dall_e', 'DALL·E 2 (OpenAI)'), ('dall_e_3', 'DALL·E 3 (OpenAI)'), ('openjourney_2', 'Open Journey v2 beta (PromptHero)'), ('openjourney', 'Open Journey (PromptHero)'), ('analog_diffusion', 'Analog Diffusion (wavymulder)'), ('protogen_5_3', 'Protogen v5.3 (darkstorm2150)'), ('jack_qiao', 'Stable Diffusion v1.4 [Deprecated] (Jack Qiao)'), ('rodent_diffusion_1_5', 'Rodent Diffusion 1.5 [Deprecated] (NerdyRodent)'), ('deepfloyd_if', 'DeepFloyd IF [Deprecated] (stability.ai)'), ('dream_shaper', 'DreamShaper (Lykon)'), ('dreamlike_2', 'Dreamlike Photoreal 2.0 (dreamlike.art)'), ('sd_2', 'Stable Diffusion v2.1 (stability.ai)'), ('sd_1_5', 'Stable Diffusion v1.5 (RunwayML)'), ('dall_e', 'Dall-E (OpenAI)'), ('instruct_pix2pix', '✨ InstructPix2Pix (Tim Brooks)'), ('openjourney_2', 'Open Journey v2 beta (PromptHero) 🐢'), ('openjourney', 'Open Journey (PromptHero) 🐢'), ('analog_diffusion', 'Analog Diffusion (wavymulder) 🐢'), ('protogen_5_3', 'Protogen v5.3 (darkstorm2150) 🐢'), ('jack_qiao', 'Stable Diffusion v1.4 [Deprecated] (Jack Qiao)'), ('rodent_diffusion_1_5', 'Rodent Diffusion 1.5 [Deprecated] (NerdyRodent)'), ('sd_2', 'Stable Diffusion v2.1 (stability.ai)'), ('runway_ml', 'Stable Diffusion v1.5 (RunwayML)'), ('dall_e', 'Dall-E (OpenAI)'), ('jack_qiao', 'Stable Diffusion v1.4 [Deprecated] (Jack Qiao)'), ('wav2lip', 'LipSync (wav2lip)'), ('sadtalker', 'LipSync (sadtalker)')], help_text='The name of the model. Only used for Display purposes.', max_length=255),
        ),
    ]
