# Generated by Django 4.2.7 on 2024-02-07 16:48

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('usage_costs', '0002_alter_modelpricing_category_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='modelpricing',
            name='model_name',
            field=models.CharField(choices=[('gpt_4_vision', 'GPT-4 Vision (openai)'), ('gpt_4_turbo', 'GPT-4 Turbo (openai)'), ('gpt_4', 'GPT-4 (openai)'), ('gpt_4_32k', 'GPT-4 32K (openai)'), ('gpt_3_5_turbo', 'ChatGPT (openai)'), ('gpt_3_5_turbo_16k', 'ChatGPT 16k (openai)'), ('llama2_70b_chat', 'Llama 2 (Meta AI)'), ('palm2_chat', 'PaLM 2 Chat (Google)'), ('palm2_text', 'PaLM 2 Text (Google)'), ('text_davinci_003', 'GPT-3.5 Davinci-3 (openai)'), ('text_davinci_002', 'GPT-3.5 Davinci-2 (openai)'), ('text_curie_001', 'Curie (openai)'), ('text_babbage_001', 'Babbage (openai)'), ('text_ada_001', 'Ada (openai)'), ('code_davinci_002', 'Codex [Deprecated] (openai)'), ('protogen_2_2', 'Protogen V2.2 (darkstorm2150)'), ('epicdream', 'epiCDream (epinikion)'), ('dream_shaper', 'DreamShaper (Lykon)'), ('dreamlike_2', 'Dreamlike Photoreal 2.0 (dreamlike.art)'), ('sd_2', 'Stable Diffusion v2.1 (stability.ai)'), ('sd_1_5', 'Stable Diffusion v1.5 (RunwayML)'), ('dall_e', 'DALL·E 2 (OpenAI)'), ('dall_e_3', 'DALL·E 3 (OpenAI)'), ('openjourney_2', 'Open Journey v2 beta (PromptHero) 🐢'), ('openjourney', 'Open Journey (PromptHero) 🐢'), ('analog_diffusion', 'Analog Diffusion (wavymulder) 🐢'), ('protogen_5_3', 'Protogen v5.3 (darkstorm2150) 🐢'), ('jack_qiao', 'Stable Diffusion v1.4 [Deprecated] (Jack Qiao)'), ('rodent_diffusion_1_5', 'Rodent Diffusion 1.5 [Deprecated] (NerdyRodent)'), ('deepfloyd_if', 'DeepFloyd IF [Deprecated] (stability.ai)'), ('dream_shaper', 'DreamShaper (Lykon)'), ('dreamlike_2', 'Dreamlike Photoreal 2.0 (dreamlike.art)'), ('sd_2', 'Stable Diffusion v2.1 (stability.ai)'), ('sd_1_5', 'Stable Diffusion v1.5 (RunwayML)'), ('dall_e', 'Dall-E (OpenAI)'), ('instruct_pix2pix', '✨ InstructPix2Pix (Tim Brooks)'), ('openjourney_2', 'Open Journey v2 beta (PromptHero) 🐢'), ('openjourney', 'Open Journey (PromptHero) 🐢'), ('analog_diffusion', 'Analog Diffusion (wavymulder) 🐢'), ('protogen_5_3', 'Protogen v5.3 (darkstorm2150) 🐢'), ('jack_qiao', 'Stable Diffusion v1.4 [Deprecated] (Jack Qiao)'), ('rodent_diffusion_1_5', 'Rodent Diffusion 1.5 [Deprecated] (NerdyRodent)'), ('sd_2', 'Stable Diffusion v2.1 (stability.ai)'), ('runway_ml', 'Stable Diffusion v1.5 (RunwayML)'), ('dall_e', 'Dall-E (OpenAI)'), ('jack_qiao', 'Stable Diffusion v1.4 [Deprecated] (Jack Qiao)')], help_text='The name of the model. Only used for Display purposes.', max_length=255),
        ),
    ]
