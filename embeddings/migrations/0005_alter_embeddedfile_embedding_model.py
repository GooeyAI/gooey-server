from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("embeddings", "0004_remove_embeddedfile_embeddings__url_750ab2_idx_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="embeddedfile",
            name="embedding_model",
            field=models.CharField(
                choices=[
                    ("openai_3_large", "Text Embedding 3 Large (OpenAI)"),
                    ("openai_3_small", "Text Embedding 3 Small (OpenAI)"),
                    ("openai_ada_2", "Text Embedding Ada 2 (OpenAI)"),
                    ("gemini_embedding_2", "Gemini Embedding 2 (Google)"),
                    ("mistral_embed", "Mistral Embed (Mistral AI)"),
                    ("e5_large_v2", "E5 large v2 (Liang Wang)"),
                    ("e5_base_v2", "E5 base v2 (Liang Wang)"),
                    ("multilingual_e5_base", "Multilingual E5 Base (Liang Wang)"),
                    ("multilingual_e5_large", "Multilingual E5 Large (Liang Wang)"),
                    ("gte_large", "General Text Embeddings Large (Dingkun Long)"),
                    ("gte_base", "General Text Embeddings Base (Dingkun Long)"),
                ],
                default="openai_3_large",
                max_length=100,
            ),
        ),
    ]
