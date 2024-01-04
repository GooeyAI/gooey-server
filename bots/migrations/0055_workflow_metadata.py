# Generated by Django 4.2.7 on 2024-01-01 23:15

from django.db import migrations, models
from bots.models import Workflow


def forwards_func(apps, schema_editor):
    workflow_metadata_updates = [
        {
            "workflow": Workflow.DOC_SEARCH,
            "short_title": "Doc Search",
            "meta_title": "Advanced Document Search Solution",
            "meta_description": """
            Easily search within PDFs, Word documents, and other formats using Gooey AI's doc-search feature. Improve efficiency and knowledge extraction with our advanced AI tools.
            """.strip(),
            "meta_image": "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/bcc7aa58-93fe-11ee-a083-02420a0001c8/Search%20your%20docs.jpg.png",
        },
        {
            "workflow": Workflow.DOC_SUMMARY,
            "short_title": "Summarize",
            "meta_title": "AI Document Summarization & Transcription",
            "meta_description": """
            Effortlessly summarize large files and collections of PDFs, docs and audio files using AI with Gooey.AI | Gooey.AI Doc-Summary Solution.
            """.strip(),
            "meta_image": "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/f35796d2-93fe-11ee-b86c-02420a0001c7/Summarize%20with%20GPT.jpg.png",
        },
        {
            "workflow": Workflow.GOOGLE_GPT,
            "short_title": "LLM Web Search",
            "meta_title": "Browse the web using ChatGPT",
            "meta_description": """
            Like Bing + ChatGPT or perplexity.ai, this workflow queries Google and then summarizes the results (with citations!) using an editable GPT3 script.
            """.strip(),
            "meta_image": "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/85ed60a2-9405-11ee-9747-02420a0001ce/Web%20search%20GPT.jpg.png",
        },
        {
            "workflow": Workflow.VIDEO_BOTS,
            "short_title": "Copilot",
            "meta_title": "Advanced AI Copilot for Farming Solutions",
            "meta_description": """
            Discover Gooey.AI's Copilot, the most advanced AI bot offering GPT4, PaLM2, LLaAM2, knowledge base integration, conversation analysis & more for farming solutions.
            """.strip(),
            "meta_image": "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/f454d64a-9457-11ee-b6d5-02420a0001cb/Copilot.jpg.png",
        },
        {
            "workflow": Workflow.LIPSYNC_TTS,
            "short_title": "Lipsync + Voice",
            "meta_title": "Lipsync Video Maker with AI Voice Generation",
            "meta_description": """
            Create realistic lipsync videos with custom voices. Just upload a video or image, choose or bring your own voice from EvelenLabs to generate amazing videos with the Gooey.AI Lipsync Maker.
            """.strip(),
            "meta_image": "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/13b4d352-9456-11ee-8edd-02420a0001c7/Lipsync%20TTS.jpg.png",
        },
        {
            "workflow": Workflow.TEXT_TO_SPEECH,
            "short_title": "Text to Speech",
            "meta_title": "Compare Text-to-Speech AI Engines",
            "meta_description": """
            Experience the most powerful text-to-speech APIs with Gooey.AI. Compare and choose the best voice for podcasts, YouTube videos, websites, bots, and more.
            """.strip(),
            "meta_image": "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/a73181ce-9457-11ee-8edd-02420a0001c7/Voice%20generators.jpg.png",
        },
        {
            "workflow": Workflow.ASR,
            "short_title": "Speech",
            "meta_title": "Speech and AI Services",
            "meta_description": """
            Generate realistic audio files, lip-sync videos, and experience multilingual chatbots with Gooey.AI speech and AI-based services. Improve user experience!
            """.strip(),
            "meta_image": "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/1916825c-93fa-11ee-97be-02420a0001c8/Speech.jpg.png",
        },
        {
            "workflow": Workflow.LIPSYNC,
            "short_title": "Lipsync",
            "meta_title": "Lipsync Animation Generator with Audio Input",
            "meta_description": """
            Achieve high-quality, realistic Lipsync animations with Gooey.AI's Lipsync - Just input a face and audio to generate your tailored animation.
            """.strip(),
            "meta_image": "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/7fc4d302-9402-11ee-98dc-02420a0001ca/Lip%20Sync.jpg.png",
        },
        {
            "workflow": Workflow.DEFORUM_SD,
            "short_title": "Animation",
            "meta_title": "Animation Generator: AI-Powered Animations Simplified",
            "meta_description": """
            Create AI-generated animations effortlessly with Gooey.AI's Animation Generator and Stable Diffusion's Deforum technology. No complex CoLab notebooks required!
            """.strip(),
            "meta_image": "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/7dc25196-93fe-11ee-9e3a-02420a0001ce/AI%20Animation%20generator.jpg.png",
        },
        {
            "workflow": Workflow.COMPARE_TEXT2IMG,
            "short_title": "Image Generator",
            "meta_title": "AI Image Generators Comparison",
            "meta_description": """
            Discover the most effective AI image generator for your needs by comparing different models like Stable Diffusion, Dall-E, and more at Gooey.AI.
            """.strip(),
            "meta_image": "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/ae7b2940-93fc-11ee-8edc-02420a0001cc/Compare%20image%20generators.jpg.png",
        },
        {
            "workflow": Workflow.TEXT_2_AUDIO,
            "short_title": "Music",
            "meta_title": "Text2Audio - AI-Driven Text-to-Sound Generator | Gooey.AI",
            "meta_description": """
            Transform text into realistic audio with Gooey.AI's text2audio tool. Create custom sounds using AI-driven technology for your projects and content.
            """.strip(),
            "meta_image": "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/85cf8ea4-9457-11ee-bd77-02420a0001ce/Text%20guided%20audio.jpg.png",
        },
        {
            "workflow": Workflow.IMG_2_IMG,
            "short_title": "Photo Editor",
            "meta_title": "AI Photo Editor for Stunning Image Transformations",
            "meta_description": """
            Transform your images with our AI Photo Editor utilizing the latest AI technology for incredible results. Enhance your photos, create unique art, and more
            """.strip(),
            "meta_image": "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/cc2804ea-9401-11ee-940a-02420a0001c7/Edit%20an%20image.jpg.png",
        },
        {
            "workflow": Workflow.FACE_INPAINTING,
            "short_title": "Face Editor",
            "meta_title": "AI Face Extraction & Generation",
            "meta_description": """
            Explore Gooey.AI's revolutionary face extraction and AI-generated photo technology, where you can upload, extract, and bring your desired character to life in a new image.
            """.strip(),
            "meta_image": "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/a146bfc0-93ff-11ee-b86c-02420a0001c7/Face%20in%20painting.jpg.png",
        },
        {
            "workflow": Workflow.GOOGLE_IMAGE_GEN,
            "short_title": "SEO Renderer",
            "meta_title": "AI Image Rendering & Generation Solution",
            "meta_description": """
            Discover the power of AI in image rendering with Gooey.AI's cutting-edge technology, transforming text prompts into stunning visuals for any search query.
            """.strip(),
            "meta_image": "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/dcd82b68-9400-11ee-9e3a-02420a0001ce/Search%20result%20photo.jpg.png",
        },
        {
            "workflow": Workflow.COMPARE_UPSCALER,
            "short_title": "Upscaler",
            "meta_title": "AI Upscalers Comparison & Examples",
            "meta_description": """
            Explore the benefits of AI upscalers and discover how they enhance image quality through cutting-edge technology at Gooey.ai.
            """.strip(),
            "meta_image": "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/2e8ee512-93fe-11ee-a083-02420a0001c8/Image%20upscaler.jpg.png",
        },
        {
            "workflow": Workflow.SEO_SUMMARY,
            "short_title": "SEO Renderer",
            "meta_title": "SEO Paragraph Generator for Enhanced Content",
            "meta_description": """
            Optimize your content with Gooey's SEO Paragraph Generator - AI powered content optimization for improved search engine rankings and increased traffic.
            """.strip(),
            "meta_image": "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/13d3ab1e-9457-11ee-98a6-02420a0001c9/SEO.jpg.png",
        },
        {
            "workflow": Workflow.EMAIL_FACE_INPAINTING,
            "short_title": "Email to Image",
            "meta_title": "AI Image from Email Lookup",
            "meta_description": """
            Discover the AI-based solution for generating images from email lookups, creating unique and engaging visuals using email addresses and AI-generated scenes.
            """.strip(),
            "meta_image": "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/6937427a-9522-11ee-b6d3-02420a0001ea/Email%20photo.jpg.png",
        },
        {
            "workflow": Workflow.SOCIAL_LOOKUP_EMAIL,
            "short_title": "Emailer",
            "meta_title": "AI-Powered Email Writer with Profile Lookup",
            "meta_description": """
            Enhance your outreach with Gooey.AI's Email Writer that finds public social profiles and creates personalized emails using advanced AI mail merge.
            """.strip(),
            "meta_image": "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/6729ea44-9457-11ee-bd77-02420a0001ce/Profile%20look%20up%20gpt%20email.jpg.png",
        },
        {
            "workflow": Workflow.OBJECT_INPAINTING,
            "short_title": "Background Maker",
            "meta_title": "Product Photo Background Generator",
            "meta_description": """
            Generate professional background scenery for your product photos with Gooey.AI's advanced inpainting AI technology.
            """.strip(),
            "meta_image": "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/4bca6982-9456-11ee-bc12-02420a0001cc/Product%20photo%20backgrounds.jpg.png",
        },
        {
            "workflow": Workflow.COMPARE_LLM,
            "short_title": "LLM",
            "meta_title": "Compare GPT-4, PaLM2, and LLaMA2 | Large Language Model Comparison",
            "meta_description": """
            Compare popular large language models like GPT-4, PaLM2, and LLaMA2 to determine which one performs best for your specific needs | Gooey.AI
            """.strip(),
            "meta_image": "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/5e4f4c58-93fc-11ee-a39e-02420a0001ce/LLMs.jpg.png",
        },
        {
            "workflow": Workflow.SMART_GPT,
            "short_title": "SmartGPT",
            "meta_title": "SmartGPT - Advanced AI Language Model",
            "meta_description": """
            Explore powerful AI solutions with Gooey.AI's SmartGPT, a cutting-edge language model designed to transform industries and simplify your work.
            """.strip(),
            "meta_image": "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/3d71b434-9457-11ee-8edd-02420a0001c7/Smart%20GPT.jpg.png",
        },
        {
            "workflow": Workflow.QR_CODE,
            "short_title": "QR Code",
            "meta_title": "AI Art QR Code Generator",
            "meta_description": """
            Generate AI-empowered artistic QR codes tailored to your style for impactful marketing, branding & more with Gooey.AI.
            """.strip(),
            "meta_image": "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/a679a410-9456-11ee-bd77-02420a0001ce/QR%20Code.jpg.png",
        },
        {
            "workflow": Workflow.DOC_EXTRACT,
            "short_title": "Synthetic Data",
            "meta_title": "Efficient YouTube Video Transcription & GPT4 Integration",
            "meta_description": """
            Automate YouTube video transcription, run GPT4 prompts, and save data to Google Sheets with Gooey AI's YouTube Bot. Elevate your content creation strategy!
            """.strip(),
            "meta_image": "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/ddc8ffac-93fb-11ee-89fb-02420a0001cb/Youtube%20transcripts.jpg.png",
        },
        {
            "workflow": Workflow.RELATED_QNA_MAKER,
            "short_title": "People Also Ask",
            "meta_title": "Related QnA Maker API for Document Search",
            "meta_description": """
            Enhance your document search experience with Gooey.AI's Related QnA Maker API, leveraging advanced machine learning to deliver relevant information from your doc, pdf, or files.
            """.strip(),
            "meta_image": "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/cbd2c94e-9456-11ee-a95e-02420a0001cc/People%20also%20ask.jpg.png",
        },
        {
            "workflow": Workflow.BULK_RUNNER,
            "short_title": "Bulk",
            "meta_title": "Bulk Runner",
            "meta_description": """
            Which AI model actually works best for your needs? Upload your own data and evaluate any Gooey.AI workflow, LLM or AI model against any other.
            """.strip(),
            "meta_image": "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/d80fd4d8-93fa-11ee-bc13-02420a0001cc/Bulk%20Runner.jpg.png",
        },
        {
            "workflow": Workflow.BULK_EVAL,
            "short_title": "Eval",
            "meta_title": "Bulk Evaluator",
            "meta_description": """
            Summarize and score every row of any CSV, google sheet or excel with GPT4 (or any LLM you choose).  Then average every score in any column to generate automated evaluations.
            """.strip(),
            "meta_image": "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/9631fb74-9a97-11ee-971f-02420a0001c4/evaluator.png.png",
        },
    ]

    workflow_metadata_model = apps.get_model("bots", "WorkflowMetadata")
    workflow_metadata_model.objects.bulk_create(
        [workflow_metadata_model(**kwargs) for kwargs in workflow_metadata_updates]
    )


def backwards_func(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("bots", "0054_alter_savedrun_example_id_alter_savedrun_page_notes_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="WorkflowMetadata",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "workflow",
                    models.IntegerField(
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
                            (30, "Bulk Runner"),
                            (31, "Bulk Evaluator"),
                        ],
                        unique=True,
                    ),
                ),
                ("short_title", models.TextField()),
                ("help_url", models.URLField(blank=True, default="")),
                (
                    "default_image",
                    models.URLField(help_text="(not implemented)", null=True),
                ),
                ("meta_title", models.TextField()),
                ("meta_description", models.TextField(blank=True, default="")),
                (
                    "meta_image",
                    models.URLField(null=True),
                ),
                (
                    "meta_keywords",
                    models.JSONField(
                        blank=True, default=list, help_text="(not implemented)"
                    ),
                ),
            ],
        ),
        migrations.RunPython(forwards_func, backwards_func),
    ]
