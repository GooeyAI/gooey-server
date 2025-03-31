from bots.models import Workflow

META_IMAGES = {
    Workflow.ASR: "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/1916825c-93fa-11ee-97be-02420a0001c8/Speech.jpg.png",
    Workflow.BULK_EVAL: "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/9631fb74-9a97-11ee-971f-02420a0001c4/evaluator.png.png",
    Workflow.BULK_RUNNER: "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/d80fd4d8-93fa-11ee-bc13-02420a0001cc/Bulk%20Runner.jpg.png",
    Workflow.COMPARE_LLM: "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/fef06d86-1f70-11ef-b8ee-02420a00015b/LLMs.jpg",
    Workflow.COMPARE_TEXT2IMG: "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/039110ba-1f72-11ef-8d23-02420a00015d/Compare%20image%20generators.jpg",
    Workflow.COMPARE_UPSCALER: "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/2e8ee512-93fe-11ee-a083-02420a0001c8/Image%20upscaler.jpg.png",
    Workflow.DOC_EXTRACT: "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/ddc8ffac-93fb-11ee-89fb-02420a0001cb/Youtube%20transcripts.jpg.png",
    Workflow.DOC_SEARCH: "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/bcc7aa58-93fe-11ee-a083-02420a0001c8/Search%20your%20docs.jpg.png",
    Workflow.DOC_SUMMARY: "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/f35796d2-93fe-11ee-b86c-02420a0001c7/Summarize%20with%20GPT.jpg.png",
    Workflow.EMAIL_FACE_INPAINTING: "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/6937427a-9522-11ee-b6d3-02420a0001ea/Email%20photo.jpg.png",
    Workflow.FACE_INPAINTING: "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/a146bfc0-93ff-11ee-b86c-02420a0001c7/Face%20in%20painting.jpg.png",
    Workflow.GOOGLE_GPT: "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/85ed60a2-9405-11ee-9747-02420a0001ce/Web%20search%20GPT.jpg.png",
    Workflow.GOOGLE_IMAGE_GEN: "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/dcd82b68-9400-11ee-9e3a-02420a0001ce/Search%20result%20photo.jpg.png",
    Workflow.IMAGE_SEGMENTATION: "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/8363ed50-9401-11ee-878f-02420a0001cb/AI%20bg%20changer.jpg.png",
    Workflow.IMG_2_IMG: "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/cc2804ea-9401-11ee-940a-02420a0001c7/Edit%20an%20image.jpg.png",
    Workflow.LIPSYNC: "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/7fc4d302-9402-11ee-98dc-02420a0001ca/Lip%20Sync.jpg.png",
    Workflow.LIPSYNC_TTS: "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/13b4d352-9456-11ee-8edd-02420a0001c7/Lipsync%20TTS.jpg.png",
    Workflow.OBJECT_INPAINTING: "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/4bca6982-9456-11ee-bc12-02420a0001cc/Product%20photo%20backgrounds.jpg.png",
    Workflow.QR_CODE: "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/a679a410-9456-11ee-bd77-02420a0001ce/QR%20Code.jpg.png",
    Workflow.RELATED_QNA_MAKER: "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/cbd2c94e-9456-11ee-a95e-02420a0001cc/People%20also%20ask.jpg.png",
    Workflow.RELATED_QNA_MAKER_DOC: "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/bab3dd2a-538c-11ee-920f-02420a00018e/RQnA-doc%20search%201.png.png",
    Workflow.SEO_SUMMARY: "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/13d3ab1e-9457-11ee-98a6-02420a0001c9/SEO.jpg.png",
    Workflow.SMART_GPT: "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/3d71b434-9457-11ee-8edd-02420a0001c7/Smart%20GPT.jpg.png",
    Workflow.SOCIAL_LOOKUP_EMAIL: "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/6729ea44-9457-11ee-bd77-02420a0001ce/Profile%20look%20up%20gpt%20email.jpg.png",
    Workflow.TEXT_2_AUDIO: "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/85cf8ea4-9457-11ee-bd77-02420a0001ce/Text%20guided%20audio.jpg.png",
    Workflow.VIDEO_BOTS: "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/7a3127ec-1f71-11ef-aa2b-02420a00015d/Copilot.jpg",
    Workflow.DEFORUM_SD: "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/7dc25196-93fe-11ee-9e3a-02420a0001ce/AI%20Animation%20generator.jpg.png",
    Workflow.TEXT_TO_SPEECH: "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/a73181ce-9457-11ee-8edd-02420a0001c7/Voice%20generators.jpg.png",
}


def run():
    for workflow, url in META_IMAGES.items():
        meta = workflow.get_or_create_metadata()
        if meta.meta_image:
            # Skip if already set
            continue
        meta.meta_image = url
        meta.save()
