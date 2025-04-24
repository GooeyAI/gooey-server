from time import sleep

from daras_ai_v2.facebook_bots import WhatsappBot


def run(bot_number: str, user_number: str, *args):
    class TestWhatsappBot(WhatsappBot):
        def __init__(self):
            self.bot_id = bot_number
            self.user_id = user_number
            self.access_token = None

        def send_msg(self, *args, **kwargs):
            super().send_msg(
                *args,
                **kwargs,
                send_feedback_buttons="nofeedback" not in args,
            )
            sleep(1)
            super().send_msg(text="✨🧪✨🧪✨🧪✨")
            sleep(3)

    bot = TestWhatsappBot()

    bot.send_msg(
        text="",
    )
    bot.send_msg(
        text="Text https://gooey.ai/explore/",
    )
    bot.send_msg(
        audio="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/d949d330-95cb-11ee-9a21-02420a00012e/google_tts_gen.mp3",
    )
    bot.send_msg(
        text="Audio with text https://gooey.ai/explore/",
        audio="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/d949d330-95cb-11ee-9a21-02420a00012e/google_tts_gen.mp3",
    )
    bot.send_msg(
        text="Audio + Video https://gooey.ai/explore/",
        audio="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/d949d330-95cb-11ee-9a21-02420a00012e/google_tts_gen.mp3",
        video="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/6f019f2a-b714-11ee-82f3-02420a000172/gooey.ai%20lipsync.mp4#t=0.001",
    )
    bot.send_msg(
        video="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/6f019f2a-b714-11ee-82f3-02420a000172/gooey.ai%20lipsync.mp4#t=0.001",
    )
    bot.send_msg(
        text="Video with text https://gooey.ai/explore/",
        video="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/6f019f2a-b714-11ee-82f3-02420a000172/gooey.ai%20lipsync.mp4#t=0.001",
    )
    bot.send_msg(
        documents=[
            "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/d30155b8-b438-11ed-85e8-02420a0001f7/Chetan%20Bhagat%20-three%20mistakes%20of%20my%20life.pdf"
        ],
    )
    bot.send_msg(
        text="Some Docs https://gooey.ai/explore/",
        documents=[
            "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/d30155b8-b438-11ed-85e8-02420a0001f7/Chetan%20Bhagat%20-three%20mistakes%20of%20my%20life.pdf"
        ],
    )
    bot.send_msg(
        text="Audio + Docs https://gooey.ai/explore/",
        audio="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/d949d330-95cb-11ee-9a21-02420a00012e/google_tts_gen.mp3",
        documents=[
            "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/d30155b8-b438-11ed-85e8-02420a0001f7/Chetan%20Bhagat%20-three%20mistakes%20of%20my%20life.pdf"
        ],
    )
    bot.send_msg(
        text="""Here's a political cartoon based on today's news: 

![Political Cartoon](https://v3.fal.media/files/tiger/IBWpoUzDGP-OkUgJ4WwFF_91a2d4d495f44257a66336da551a6ff3.png)

Image prompt: A political cartoon showing Elon Musk holding a DOGE coin and an Ebola prevention fund jar, looking surprised. In the background, a confused health worker holding a clipboard labeled 'Ebola Prevention Budget'. The caption reads: 'When cryptocurrency cuts the wrong funding...'
https://gooey.ai/explore/
<button gui-target="input_prompt">📰 More on today's news</button>
<button gui-target="input_prompt">🎨 Create another cartoon</button>
<button gui-target="input_prompt">😂 Tell me another joke</button>
<button gui-target="input_prompt">🤔 What are the ideal soil conditions for chilli growth?</button>
<button gui-target="input_prompt">🌱 How often should I irrigate my chilli plants during the rainy season?</button>
""",
    )
    bot.send_msg(
        text="""
If the user asks something related to their current location, ask them for their location first by displaying the following html button:
https://gooey.ai/explore/ 
<button gui-action="send_location"></button>
        """,
    )
    bot.send_msg(
        text="""
If the user asks something related to their current location, ask them for their location first by displaying the following html button: 
https://gooey.ai/explore/
<button gui-action="send_location, disable_feedback"></button>
        """,
    )
    bot.send_msg(
        text="""Hello I'm an AI bot named Mshauri. I'm here to help you grow more and earn more. I'm brought to you by Digifarm and Opportunity International. Note that we store your WhatsApp number, questions and our responses to improve the bot, so please don't share personal information. 
https://gooey.ai/explore/
Please respond with '✅ I Agree' to let us know you understand what data we collect and to start using the Mshauri service.  Thank you.
<button gui-action="disable_feedback" gui-target="input_prompt">✅ I Agree</button>""",
    )
    bot.send_msg(
        text="""Hello! How can I assist you today? 😊 https://gooey.ai/explore/

<button gui-target="input_prompt" gui-action="disable_feedback">🔍 Search for something</button>
<button gui-target="input_prompt">❓ Ask a question</button>
<button gui-target="input_prompt">📅 Find events near me</button>""",
    )
    bot.send_msg(
        text="""Hello! How can I assist you today? 😊 https://gooey.ai/explore/
<button gui-action="disable_feedback"></button>""",
    )
