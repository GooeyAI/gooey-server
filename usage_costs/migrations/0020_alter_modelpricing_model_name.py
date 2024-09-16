# Generated by Django 4.2.7 on 2024-09-06 16:42

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('usage_costs', '0019_alter_modelpricing_model_name'),
    ]

    operations = [
        migrations.AlterField(
            model_name='modelpricing',
            name='model_name',
            field=models.CharField(choices=[('gpt_4_o', 'GPT-4o (openai)'), ('gpt_4_o_mini', 'GPT-4o-mini (openai)'), ('chatgpt_4_o', 'ChatGPT-4o (openai) 🧪'), ('gpt_4_turbo_vision', 'GPT-4 Turbo with Vision (openai)'), ('gpt_4_vision', 'GPT-4 Vision (openai) 🔻'), ('gpt_4_turbo', 'GPT-4 Turbo (openai)'), ('gpt_4', 'GPT-4 (openai)'), ('gpt_4_32k', 'GPT-4 32K (openai) 🔻'), ('gpt_3_5_turbo', 'ChatGPT (openai)'), ('gpt_3_5_turbo_16k', 'ChatGPT 16k (openai)'), ('gpt_3_5_turbo_instruct', 'GPT-3.5 Instruct (openai) 🔻'), ('llama3_70b', 'Llama 3 70b (Meta AI)'), ('llama_3_groq_70b_tool_use', 'Llama 3 Groq 70b Tool Use'), ('llama3_8b', 'Llama 3 8b (Meta AI)'), ('llama_3_groq_8b_tool_use', 'Llama 3 Groq 8b Tool Use'), ('llama2_70b_chat', 'Llama 2 70b Chat [Deprecated] (Meta AI)'), ('mixtral_8x7b_instruct_0_1', 'Mixtral 8x7b Instruct v0.1 (Mistral)'), ('gemma_2_9b_it', 'Gemma 2 9B (Google)'), ('gemma_7b_it', 'Gemma 7B (Google)'), ('gemini_1_5_flash', 'Gemini 1.5 Flash (Google)'), ('gemini_1_5_pro', 'Gemini 1.5 Pro (Google)'), ('gemini_1_pro_vision', 'Gemini 1.0 Pro Vision (Google)'), ('gemini_1_pro', 'Gemini 1.0 Pro (Google)'), ('palm2_chat', 'PaLM 2 Chat (Google)'), ('palm2_text', 'PaLM 2 Text (Google)'), ('claude_3_5_sonnet', 'Claude 3.5 Sonnet (Anthropic)'), ('claude_3_opus', 'Claude 3 Opus [L] (Anthropic)'), ('claude_3_sonnet', 'Claude 3 Sonnet [M] (Anthropic)'), ('claude_3_haiku', 'Claude 3 Haiku [S] (Anthropic)'), ('sea_lion_7b_instruct', 'SEA-LION-7B-Instruct [Deprecated] (aisingapore)'), ('llama3_8b_cpt_sea_lion_v2_instruct', 'Llama3 8B CPT SEA-LIONv2 Instruct [Deprecated] (aisingapore)'), ('llama3_8b_cpt_sea_lion_v2_1_instruct', 'Llama3 8B CPT SEA-LIONv2.1 Instruct (aisingapore)'), ('sarvam_2b', 'Sarvam 2B (sarvamai)'), ('text_davinci_003', 'GPT-3.5 Davinci-3 [Deprecated] (openai)'), ('text_davinci_002', 'GPT-3.5 Davinci-2 [Deprecated] (openai)'), ('code_davinci_002', 'Codex [Deprecated] (openai)'), ('text_curie_001', 'Curie [Deprecated] (openai)'), ('text_babbage_001', 'Babbage [Deprecated] (openai)'), ('text_ada_001', 'Ada [Deprecated] (openai)'), ('protogen_2_2', 'Protogen V2.2 (darkstorm2150)'), ('epicdream', 'epiCDream (epinikion)'), ('dream_shaper', 'DreamShaper (Lykon)'), ('dreamlike_2', 'Dreamlike Photoreal 2.0 (dreamlike.art)'), ('sd_2', 'Stable Diffusion v2.1 (stability.ai)'), ('sd_1_5', 'Stable Diffusion v1.5 (RunwayML)'), ('dall_e', 'DALL·E 2 (OpenAI)'), ('dall_e_3', 'DALL·E 3 (OpenAI)'), ('openjourney_2', 'Open Journey v2 beta (PromptHero)'), ('openjourney', 'Open Journey (PromptHero)'), ('analog_diffusion', 'Analog Diffusion (wavymulder)'), ('protogen_5_3', 'Protogen v5.3 (darkstorm2150)'), ('jack_qiao', 'Stable Diffusion v1.4 [Deprecated] (Jack Qiao)'), ('rodent_diffusion_1_5', 'Rodent Diffusion 1.5 [Deprecated] (NerdyRodent)'), ('deepfloyd_if', 'DeepFloyd IF [Deprecated] (stability.ai)'), ('dream_shaper', 'DreamShaper (Lykon)'), ('dreamlike_2', 'Dreamlike Photoreal 2.0 (dreamlike.art)'), ('sd_2', 'Stable Diffusion v2.1 (stability.ai)'), ('sd_1_5', 'Stable Diffusion v1.5 (RunwayML)'), ('dall_e', 'Dall-E (OpenAI)'), ('instruct_pix2pix', '✨ InstructPix2Pix (Tim Brooks)'), ('openjourney_2', 'Open Journey v2 beta (PromptHero) 🐢'), ('openjourney', 'Open Journey (PromptHero) 🐢'), ('analog_diffusion', 'Analog Diffusion (wavymulder) 🐢'), ('protogen_5_3', 'Protogen v5.3 (darkstorm2150) 🐢'), ('jack_qiao', 'Stable Diffusion v1.4 [Deprecated] (Jack Qiao)'), ('rodent_diffusion_1_5', 'Rodent Diffusion 1.5 [Deprecated] (NerdyRodent)'), ('sd_2', 'Stable Diffusion v2.1 (stability.ai)'), ('runway_ml', 'Stable Diffusion v1.5 (RunwayML)'), ('dall_e', 'Dall-E (OpenAI)'), ('jack_qiao', 'Stable Diffusion v1.4 [Deprecated] (Jack Qiao)'), ('wav2lip', 'LipSync (wav2lip)'), ('sadtalker', 'LipSync (sadtalker)')], help_text='The name of the model. Only used for Display purposes.', max_length=255),
        ),
    ]
