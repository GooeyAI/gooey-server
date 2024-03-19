from time import sleep

from daras_ai_v2.bots import _feedback_start_buttons
from daras_ai_v2.facebook_bots import WhatsappBot


def run(bot_number: str, user_number: str):
    WhatsappBot.send_msg_to(
        bot_number=bot_number,
        user_number=user_number,
        text="",
        buttons=_feedback_start_buttons(),
    )
    sleep(1)
    WhatsappBot.send_msg_to(
        bot_number=bot_number,
        user_number=user_number,
        text="",
    )
    sleep(1)
    WhatsappBot.send_msg_to(
        bot_number=bot_number,
        user_number=user_number,
        text="Text With Buttons",
        buttons=_feedback_start_buttons(),
    )
    sleep(1)
    WhatsappBot.send_msg_to(
        bot_number=bot_number,
        user_number=user_number,
        audio="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/d949d330-95cb-11ee-9a21-02420a00012e/google_tts_gen.mp3",
    )
    sleep(1)
    WhatsappBot.send_msg_to(
        bot_number=bot_number,
        user_number=user_number,
        audio="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/d949d330-95cb-11ee-9a21-02420a00012e/google_tts_gen.mp3",
        buttons=_feedback_start_buttons(),
    )
    sleep(1)
    WhatsappBot.send_msg_to(
        bot_number=bot_number,
        user_number=user_number,
        text="Audio with text",
        audio="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/d949d330-95cb-11ee-9a21-02420a00012e/google_tts_gen.mp3",
        buttons=_feedback_start_buttons(),
    )
    sleep(1)
    WhatsappBot.send_msg_to(
        bot_number=bot_number,
        user_number=user_number,
        text="Audio + Video",
        audio="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/d949d330-95cb-11ee-9a21-02420a00012e/google_tts_gen.mp3",
        video="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/6f019f2a-b714-11ee-82f3-02420a000172/gooey.ai%20lipsync.mp4#t=0.001",
        buttons=_feedback_start_buttons(),
    )
    sleep(1)
    WhatsappBot.send_msg_to(
        bot_number=bot_number,
        user_number=user_number,
        video="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/6f019f2a-b714-11ee-82f3-02420a000172/gooey.ai%20lipsync.mp4#t=0.001",
    )
    sleep(1)
    WhatsappBot.send_msg_to(
        bot_number=bot_number,
        user_number=user_number,
        video="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/6f019f2a-b714-11ee-82f3-02420a000172/gooey.ai%20lipsync.mp4#t=0.001",
        buttons=_feedback_start_buttons(),
    )
    sleep(1)
    WhatsappBot.send_msg_to(
        bot_number=bot_number,
        user_number=user_number,
        text="Video with text",
        video="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/6f019f2a-b714-11ee-82f3-02420a000172/gooey.ai%20lipsync.mp4#t=0.001",
        buttons=_feedback_start_buttons(),
    )
    sleep(1)
    WhatsappBot.send_msg_to(
        bot_number=bot_number,
        user_number=user_number,
        documents=[
            "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/d30155b8-b438-11ed-85e8-02420a0001f7/Chetan%20Bhagat%20-three%20mistakes%20of%20my%20life.pdf"
        ],
    )
    sleep(1)
    WhatsappBot.send_msg_to(
        bot_number=bot_number,
        user_number=user_number,
        documents=[
            "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/d30155b8-b438-11ed-85e8-02420a0001f7/Chetan%20Bhagat%20-three%20mistakes%20of%20my%20life.pdf"
        ],
        buttons=_feedback_start_buttons(),
    )
    sleep(1)
    WhatsappBot.send_msg_to(
        bot_number=bot_number,
        user_number=user_number,
        text="Some Docs",
        documents=[
            "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/d30155b8-b438-11ed-85e8-02420a0001f7/Chetan%20Bhagat%20-three%20mistakes%20of%20my%20life.pdf"
        ],
    )
    sleep(1)
    WhatsappBot.send_msg_to(
        bot_number=bot_number,
        user_number=user_number,
        text="Some Docs",
        documents=[
            "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/d30155b8-b438-11ed-85e8-02420a0001f7/Chetan%20Bhagat%20-three%20mistakes%20of%20my%20life.pdf"
        ],
        buttons=_feedback_start_buttons(),
    )
    sleep(1)
    WhatsappBot.send_msg_to(
        bot_number=bot_number,
        user_number=user_number,
        text="Audio + Docs",
        audio="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/d949d330-95cb-11ee-9a21-02420a00012e/google_tts_gen.mp3",
        documents=[
            "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/d30155b8-b438-11ed-85e8-02420a0001f7/Chetan%20Bhagat%20-three%20mistakes%20of%20my%20life.pdf"
        ],
        buttons=_feedback_start_buttons(),
    )
