# Generated by Django 4.2.5 on 2023-09-20 09:18

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("bots", "0042_alter_message_platform_msg_id"),
    ]

    operations = [
        migrations.AlterField(
            model_name="savedrun",
            name="workflow",
            field=models.IntegerField(
                choices=[
                    (1, "Doc Search"),
                    (2, "Doc Summary"),
                    (3, "Google GPT"),
                    (4, "Copilot"),
                    (5, "Lipysnc + TTS"),
                    (6, "Text to Speech"),
                    (7, "Speech Recognition"),
                    (8, "Lipsync"),
                    (9, "Deforum Animation"),
                    (10, "Compare Text2Img"),
                    (11, "Text2Audio"),
                    (12, "Img2Img"),
                    (13, "Face Inpainting"),
                    (14, "Google Image Gen"),
                    (15, "Compare AI Upscalers"),
                    (16, "SEO Summary"),
                    (17, "Email Face Inpainting"),
                    (18, "Social Lookup Email"),
                    (19, "Object Inpainting"),
                    (20, "Image Segmentation"),
                    (21, "Compare LLM"),
                    (22, "Chyron Plant"),
                    (23, "Letter Writer"),
                    (24, "Smart GPT"),
                    (25, "AI QR Code"),
                    (26, "Doc Extract"),
                    (27, "Related QnA Maker"),
                    (28, "Related QnA Maker Doc"),
                    (29, "Embeddings"),
                ],
                default=4,
            ),
        ),
    ]
