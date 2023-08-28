import datetime
import os
import os.path
import re
import typing

import jinja2
from django.db.models import QuerySet
from furl import furl
from pydantic import BaseModel

import gooey_ui as st
from bots.models import BotIntegration, Platform
from bots.models import Workflow
from daras_ai.image_input import (
    truncate_text_words,
)
from daras_ai_v2.GoogleGPT import SearchReference
from daras_ai_v2.asr import (
    run_google_translate,
    google_translate_language_selector,
)
from daras_ai_v2.base import BasePage, MenuTabs, StateKeys
from daras_ai_v2.doc_search_settings_widgets import (
    doc_search_settings,
    document_uploader,
)
from daras_ai_v2.language_model import (
    run_language_model,
    calc_gpt_tokens,
    ConversationEntry,
    format_chatml_message,
    CHATML_END_TOKEN,
    CHATML_START_TOKEN,
    LargeLanguageModels,
    CHATML_ROLE_ASSISTANT,
    CHATML_ROLE_USER,
    CHATML_ROLE_SYSTEM,
    model_max_tokens,
)
from daras_ai_v2.language_model_settings_widgets import language_model_settings
from daras_ai_v2.lipsync_settings_widgets import lipsync_settings
from daras_ai_v2.loom_video_widget import youtube_video
from daras_ai_v2.query_params import gooey_get_query_params
from daras_ai_v2.query_params_util import extract_query_params
from daras_ai_v2.search_ref import apply_response_template, parse_refs, CitationStyles
from daras_ai_v2.text_output_widget import text_output
from daras_ai_v2.text_to_speech_settings_widgets import (
    TextToSpeechProviders,
    text_to_speech_settings,
)
from recipes.DocSearch import (
    get_top_k_references,
    DocSearchPage,
    references_as_prompt,
)
from recipes.Lipsync import LipsyncPage
from recipes.TextToSpeech import TextToSpeechPage
from url_shortener.models import ShortenedURL

BOT_SCRIPT_RE = re.compile(
    # start of line
    r"^"
    # name of bot / user
    r"([\w\ \t]+)"
    # colon
    r"\:\ ",
    flags=re.M,
)

SAFETY_BUFFER = 100


def show_landbot_widget():
    landbot_url = st.session_state.get("landbot_url")
    if not landbot_url:
        st.html("", **{"data-landbot-config-url": ""})
        return

    f = furl(landbot_url)
    config_path = os.path.join(f.host, *f.path.segments[:2])
    config_url = f"https://storage.googleapis.com/{config_path}/index.json"

    st.html(
        # language=HTML
        """
<script>
function updateLandbotWidget() {
    if (window.myLandbot) {
        try {
            window.myLandbot.destroy();
        } catch (e) {}
    }
    const configUrl = document.querySelector("[data-landbot-config-url]")?.getAttribute("data-landbot-config-url");
    if (configUrl) {
        window.myLandbot = new Landbot.Livechat({ configUrl });
    }
}
if (typeof Landbot === "undefined") {
    const script = document.createElement("script");
    script.src = "https://cdn.landbot.io/landbot-3/landbot-3.0.0.js";
    script.async = true;
    script.defer = true;
    script.onload = () => {
        window.waitUntilHydrated.then(updateLandbotWidget);
        window.addEventListener("hydrated", updateLandbotWidget);
    };
    document.body.appendChild(script);
}
</script>
        """,
        **{"data-landbot-config-url": config_url},
    )


def parse_script(bot_script: str) -> (str, list[ConversationEntry]):
    # run regex to find scripted messages in script text
    script_matches = list(BOT_SCRIPT_RE.finditer(bot_script))
    # extract system message from script
    system_message = bot_script
    if script_matches:
        system_message = system_message[: script_matches[0].start()]
    system_message = system_message.strip()
    # extract pre-scripted messages from script
    scripted_msgs: list[ConversationEntry] = []
    for idx in range(len(script_matches)):
        match = script_matches[idx]
        try:
            next_match = script_matches[idx + 1]
        except IndexError:
            next_match_start = None
        else:
            next_match_start = next_match.start()
        if (len(script_matches) - idx) % 2 == 0:
            role = CHATML_ROLE_USER
        else:
            role = CHATML_ROLE_ASSISTANT
        scripted_msgs.append(
            {
                "role": role,
                "display_name": match.group(1).strip(),
                "content": bot_script[match.end() : next_match_start].strip(),
            }
        )
    return system_message, scripted_msgs


class VideoBotsPage(BasePage):
    title = "Copilot for your Enterprise"  #  "Create Interactive Video Bots"
    workflow = Workflow.VIDEO_BOTS
    slug_versions = ["video-bots", "bots", "copilot"]

    sane_defaults = {
        "messages": [],
        # tts
        "tts_provider": TextToSpeechProviders.GOOGLE_TTS.name,
        "google_voice_name": "en-IN-Wavenet-A",
        "google_pitch": 0.0,
        "google_speaking_rate": 1.0,
        "uberduck_voice_name": "hecko",
        "uberduck_speaking_rate": 1.0,
        # gpt3
        "selected_model": LargeLanguageModels.text_davinci_003.name,
        "avoid_repetition": True,
        "num_outputs": 1,
        "quality": 1.0,
        "max_tokens": 1500,
        "sampling_temperature": 0.5,
        # wav2lip
        "face_padding_top": 0,
        "face_padding_bottom": 10,
        "face_padding_left": 0,
        "face_padding_right": 0,
        # doc search
        "citation_style": CitationStyles.number.name,
        "documents": [],
        "task_instructions": "Make sure to use only the following search results to guide your response. "
        'If the Search Results do not contain enough information, say "I don\'t know".',
        "max_references": 3,
        "max_context_words": 200,
        "scroll_jump": 5,
        "use_url_shortener": False,
    }

    class RequestModel(BaseModel):
        input_prompt: str
        bot_script: str | None

        # tts settings
        tts_provider: typing.Literal[
            tuple(e.name for e in TextToSpeechProviders)
        ] | None
        uberduck_voice_name: str | None
        uberduck_speaking_rate: float | None
        google_voice_name: str | None
        google_speaking_rate: float | None
        google_pitch: float | None

        # llm settings
        selected_model: typing.Literal[
            tuple(e.name for e in LargeLanguageModels)
        ] | None
        avoid_repetition: bool | None
        num_outputs: int | None
        quality: float | None
        max_tokens: int | None
        sampling_temperature: float | None

        # lipsync
        input_face: str | None
        face_padding_top: int | None
        face_padding_bottom: int | None
        face_padding_left: int | None
        face_padding_right: int | None

        # conversation history/context
        messages: list[ConversationEntry] | None

        # doc search
        query_instructions: str | None
        task_instructions: str | None
        documents: list[str] | None
        max_references: int | None
        max_context_words: int | None
        scroll_jump: int | None

        citation_style: typing.Literal[tuple(e.name for e in CitationStyles)] | None
        use_url_shortener: bool | None

        user_language: str | None

    class ResponseModel(BaseModel):
        final_prompt: str
        raw_input_text: str | None
        raw_output_text: list[str] | None
        output_text: list[str]

        # tts
        output_audio: list[str]

        # lipsync
        output_video: list[str]

        # doc search
        references: list[SearchReference] | None
        search_query: str | None

    def related_workflows(self):
        from recipes.LipsyncTTS import LipsyncTTSPage
        from recipes.CompareText2Img import CompareText2ImgPage
        from recipes.DeforumSD import DeforumSDPage
        from recipes.DocSearch import DocSearchPage

        return [
            LipsyncTTSPage,
            DocSearchPage,
            DeforumSDPage,
            CompareText2ImgPage,
        ]

    def preview_description(self, state: dict) -> str:
        return "Create customized chatbots from your own docs/PDF/webpages. Craft your own bot prompts using the creative GPT3, fast GPT 3.5-turbo or powerful GPT4 & optionally prevent hallucinations by constraining all answers to just your citations. Available as Facebook, Instagram, WhatsApp bots or via API. Add multi-lingual speech recognition and text-to-speech in 100+ languages and even video responses. Collect 👍🏾 👎🏽 feedback + see usage & retention graphs too! This is the workflow that powers https://Farmer.CHAT and it's yours to tweak."
        # return "Create an amazing, interactive AI videobot with just a GPT3 script + a video clip or photo. To host it on your own site or app, contact us at support@gooey.ai"

    def render_description(self):
        st.write(
            """
Have you ever wanted to create a bot that you could talk to about anything? Ever wanted to create your own https://dara.network/RadBots or https://Farmer.CHAT? This is how. 

This workflow takes a dialog LLM prompt describing your character, a collection of docs & links and optional an video clip of your bot’s face and  voice settings. 
 
We use all these to build a bot that anyone can speak to about anything and you can host directly in your own site or app, or simply connect to your Facebook, WhatsApp or Instagram page. 

How It Works:
1. Appends the user's question to the bottom of your dialog script. 
2. Sends the appended script to OpenAI’s GPT3 asking it to respond to the question in the style of your character
3. Synthesizes your character's response as audio using your voice settings (using Google Text-To-Speech or Uberduck)
4. Lip syncs the face video clip to the voice clip
5. Shows the resulting video to the user

PS. This is the workflow that we used to create RadBots - a collection of Turing-test videobots, authored by leading international writers, singers and playwrights - and really inspired us to create Gooey.AI so that every person and organization could create their own fantastic characters, in any personality of their choosing. It's also the workflow that powers https://Farmer.CHAT and was demo'd at the UN General Assembly in April 2023 as a multi-lingual WhatsApp bot for Indian, Ethiopian and Kenyan farmers. 
        """
        )

    def render_form_v2(self):
        st.text_area(
            """
            ##### 📝 Script
            Instructions to the bot + an example scripted conversation (~1000 words)
            """,
            key="bot_script",
            height=300,
        )

        document_uploader(
            """
##### 📄 Documents (*optional*)
Enable document search, to use custom documents as information sources.
"""
        )

    def render_usage_guide(self):
        youtube_video("-j2su1r8pEg")

    def render_settings(self):
        st.checkbox("🔗 Shorten URL", key="use_url_shortener")
        st.caption(
            "This will shorten the urls of the references which allows tracking of clicks and views."
        )
        google_translate_language_selector(
            """
            ###### 🔠 User Language
            If provided, the bot will translate input prompt to english, and the responses to this language.
            """,
            key="user_language",
        )
        st.write("---")

        if not "__enable_audio" in st.session_state:
            st.session_state["__enable_audio"] = bool(
                st.session_state.get("tts_provider")
            )
        enable_audio = st.checkbox("Enable Audio Ouput?", key="__enable_audio")
        if not enable_audio:
            st.write("---")
            st.session_state["tts_provider"] = None
        else:
            text_to_speech_settings()
            st.write("---")

            if not "__enable_video" in st.session_state:
                st.session_state["__enable_video"] = bool(
                    st.session_state.get("input_face")
                )
            enable_video = st.checkbox("Enable Video Output?", key="__enable_video")
            if not enable_video:
                st.write("---")
                st.session_state["input_face"] = None
            else:
                st.file_uploader(
                    """
                    #### 👩‍🦰 Input Face
                    Upload a video/image that contains faces to use  
                    *Recommended - mp4 / mov / png / jpg / gif* 
                    """,
                    key="input_face",
                )
                lipsync_settings()
                st.write("---")

        if st.session_state.get("documents") or st.session_state.get(
            "__documents_files"
        ):
            st.text_area(
                """
##### 👩‍🏫 Task Instructions
Prompt for interpreting the document sources.
                """,
                key="task_instructions",
                height=300,
            )
            st.text_area(
                """
##### 👁‍🗨 Query Instructions
Prompt to transform the conversation history into a vector search query.                
                """,
                key="query_instructions",
                height=300,
            )
            st.write("---")

            doc_search_settings()
            st.write("---")

        language_model_settings()

    def fields_to_save(self) -> [str]:
        return super().fields_to_save() + ["landbot_url"]

    def render_example(self, state: dict):
        input_prompt = state.get("input_prompt")
        if input_prompt:
            st.write(
                "**Prompt**\n```properties\n"
                + truncate_text_words(input_prompt, maxlen=200)
                + "\n```"
            )

        st.write("**Response**")

        output_video = state.get("output_video")
        if output_video:
            st.video(output_video[0])

        output_text = state.get("output_text")
        if output_text:
            st.write(truncate_text_words(output_text[0], maxlen=200))

    def render_output(self):
        with st.div(className="pb-3"):
            with st.div(
                className="pb-1",
                style=dict(
                    maxHeight="80vh",
                    overflowY="scroll",
                    display="flex",
                    flexDirection="column-reverse",
                    border="1px solid #c9c9c9",
                ),
            ):
                with msg_container_widget(CHATML_ROLE_ASSISTANT):
                    output_text = st.session_state.get("output_text", [])
                    output_video = st.session_state.get("output_video", [])
                    output_audio = st.session_state.get("output_audio", [])
                    if output_text:
                        st.write(f"**Assistant**")
                        for idx, text in enumerate(output_text):
                            st.write(text)
                            try:
                                st.video(output_video[idx])
                            except IndexError:
                                try:
                                    st.audio(output_audio[idx])
                                except IndexError:
                                    pass

                input_prompt = st.session_state.get("input_prompt")
                if input_prompt:
                    with msg_container_widget(CHATML_ROLE_USER):
                        st.write(f"**User** \\\n{input_prompt}")

                for entry in reversed(st.session_state.get("messages", [])):
                    with msg_container_widget(entry["role"]):
                        display_name = entry.get("display_name") or entry["role"]
                        display_name = display_name.capitalize()
                        st.write(f'**{display_name}** \\\n{entry["content"]}')

            with st.div(
                className="px-3 pt-3 d-flex gap-1",
                style=dict(background="rgba(239, 239, 239, 0.6)"),
            ):
                with st.div(className="flex-grow-1"):
                    new_input = st.text_area(
                        "", placeholder="Send a message", height=50
                    )

                if st.button("✈ Send", style=dict(height="3.2rem")):
                    messsages = st.session_state.get("messages", [])
                    raw_input_text = st.session_state.get("raw_input_text") or ""
                    raw_output_text = (st.session_state.get("raw_output_text") or [""])[
                        0
                    ]
                    if raw_input_text and raw_output_text:
                        messsages += [
                            {
                                "role": CHATML_ROLE_USER,
                                "content": raw_input_text,
                            },
                            {
                                "role": CHATML_ROLE_ASSISTANT,
                                "content": raw_output_text,
                            },
                        ]
                    st.session_state["messages"] = messsages
                    st.session_state["input_prompt"] = new_input
                    self.on_submit()

        if st.button("🗑️ Clear"):
            st.session_state["messages"] = []
            st.session_state["input_prompt"] = ""
            st.session_state["raw_input_text"] = ""
            self.clear_outputs()
            st.experimental_rerun()

        references = st.session_state.get("references", [])
        if not references:
            return
        with st.expander("💁‍♀️ Sources"):
            for idx, ref in enumerate(references):
                st.write(f"**{idx + 1}**. [{ref['title']}]({ref['url']})")
                text_output(
                    "Source Document",
                    value=ref["snippet"],
                    label_visibility="collapsed",
                )

    def render_steps(self):
        if st.session_state.get("tts_provider"):
            st.video(st.session_state.get("input_face"), caption="Input Face")

        search_query = st.session_state.get("search_query")
        if search_query:
            st.text_area(
                "**Document Search Query**",
                value=search_query,
                height=100,
                disabled=True,
            )

        references = st.session_state.get("references", [])
        if references:
            st.write("**References**")
            st.json(references, expanded=False)

        final_prompt = st.session_state.get("final_prompt")
        if final_prompt:
            text_output(
                "**Final Prompt**",
                value=final_prompt,
                height=300,
            )

        for idx, text in enumerate(st.session_state.get("raw_output_text", [])):
            st.text_area(
                f"**Raw Text Response {idx + 1}**",
                value=text,
                disabled=True,
            )

        col1, col2 = st.columns(2)
        with col1:
            for idx, text in enumerate(st.session_state.get("output_text", [])):
                st.text_area(
                    f"**Final Response {idx + 1}**",
                    value=text,
                    disabled=True,
                )
        with col2:
            for idx, audio_url in enumerate(st.session_state.get("output_audio", [])):
                st.write(f"**Generated Audio {idx + 1}**")
                st.audio(audio_url)

    def run(self, state: dict) -> typing.Iterator[str | None]:
        request: VideoBotsPage.RequestModel = self.RequestModel.parse_obj(state)

        user_input = request.input_prompt.strip()
        if not user_input:
            return
        model = LargeLanguageModels[request.selected_model]
        is_chat_model = model.is_chat_model()
        saved_msgs = request.messages.copy()
        bot_script = request.bot_script

        # translate input text
        if request.user_language and request.user_language != "en":
            yield f"Translating input to english..."
            user_input = run_google_translate(
                texts=[user_input],
                source_language=request.user_language,
                target_language="en",
            )[0]

        # parse the bot script
        system_message, scripted_msgs = parse_script(bot_script)

        # consturct the system prompt
        if system_message:
            # add time to prompt
            utcnow = datetime.datetime.utcnow().strftime("%B %d, %Y %H:%M:%S %Z")
            system_message = system_message.replace("{{ datetime.utcnow }}", utcnow)
            # insert to top
            system_prompt = {"role": CHATML_ROLE_SYSTEM, "content": system_message}
        else:
            system_prompt = None

        # get user/bot display names
        try:
            bot_display_name = scripted_msgs[-1]["display_name"]
        except IndexError:
            bot_display_name = CHATML_ROLE_ASSISTANT
        try:
            user_display_name = scripted_msgs[-2]["display_name"]
        except IndexError:
            user_display_name = CHATML_ROLE_USER

        # construct user prompt
        state["raw_input_text"] = user_input
        user_prompt = {
            "role": CHATML_ROLE_USER,
            "display_name": user_display_name,
            "content": user_input,
        }

        # if documents are provided, run doc search on the saved msgs and get back the references
        references = None
        if request.documents:
            # formulate the search query as a history of all the messages
            query_msgs = saved_msgs + [user_prompt]
            clip_idx = convo_window_clipper(
                query_msgs, model_max_tokens[model] // 2, sep=" "
            )
            query_msgs = query_msgs[clip_idx:]

            query_instructions = (request.query_instructions or "").strip()
            if query_instructions:
                query_instructions = jinja2.Template(query_instructions).render(
                    **state
                    | dict(
                        messages="\n".join(
                            f'{msg["role"]}: """{msg["content"]}"""'
                            for msg in query_msgs
                        ),
                    ),
                )
                state["search_query"] = run_language_model(
                    model=request.selected_model,
                    prompt=query_instructions,
                    max_tokens=model_max_tokens[model] // 2,
                    quality=request.quality,
                    temperature=request.sampling_temperature,
                    avoid_repetition=request.avoid_repetition,
                )[0]
            else:
                query_msgs.reverse()
                state["search_query"] = "\n---\n".join(
                    msg["content"] for msg in query_msgs
                )

            # perform doc search
            references = yield from get_top_k_references(
                DocSearchPage.RequestModel.parse_obj(state)
            )
            if request.use_url_shortener:
                for reference in references:
                    reference["url"] = ShortenedURL.objects.get_or_create_for_workflow(
                        url=reference["url"],
                        user=self.request.user,
                        workflow=Workflow.VIDEO_BOTS,
                    )[0].shortened_url()
            state["references"] = references
        # if doc search is successful, add the search results to the user prompt
        if references:
            user_prompt["content"] = (
                references_as_prompt(references)
                + f"\n**********\n{request.task_instructions.strip()}\n**********\n"
                + user_prompt["content"]
            )

        # truncate the history to fit the model's max tokens
        history_window = scripted_msgs + saved_msgs
        max_history_tokens = (
            model_max_tokens[model]
            - calc_gpt_tokens([system_prompt, user_prompt], is_chat_model=is_chat_model)
            - request.max_tokens
            - SAFETY_BUFFER
        )
        clip_idx = convo_window_clipper(
            history_window, max_history_tokens, is_chat_model=is_chat_model
        )
        history_window = history_window[clip_idx:]
        prompt_messages = [system_prompt, *history_window, user_prompt]

        # for backwards compat with non-chat models
        if not is_chat_model:
            # assistant prompt to triger a model response
            prompt_messages.append(
                {
                    "role": CHATML_ROLE_ASSISTANT,
                    "display_name": bot_display_name,
                    "content": "",
                }
            )

        # final prompt to display
        prompt = "\n".join(format_chatml_message(entry) for entry in prompt_messages)
        state["final_prompt"] = prompt

        # ensure input script is not too big
        max_allowed_tokens = model_max_tokens[model] - calc_gpt_tokens(
            prompt_messages, is_chat_model=is_chat_model
        )
        max_allowed_tokens = min(max_allowed_tokens, request.max_tokens)
        if max_allowed_tokens < 0:
            raise ValueError("Input Script is too long! Please reduce the script size.")

        yield f"Running {model.value}..."
        if is_chat_model:
            output_text = run_language_model(
                model=request.selected_model,
                messages=[
                    {"role": s["role"], "content": s["content"]}
                    for s in prompt_messages
                ],
                max_tokens=max_allowed_tokens,
                num_outputs=request.num_outputs,
                temperature=request.sampling_temperature,
                avoid_repetition=request.avoid_repetition,
            )
        else:
            output_text = run_language_model(
                model=request.selected_model,
                prompt=prompt,
                max_tokens=max_allowed_tokens,
                quality=request.quality,
                num_outputs=request.num_outputs,
                temperature=request.sampling_temperature,
                avoid_repetition=request.avoid_repetition,
                stop=[CHATML_END_TOKEN, CHATML_START_TOKEN],
            )
        # save model response
        state["raw_output_text"] = [
            "".join(snippet for snippet, refs in parse_refs(text, references))
            for text in output_text
        ]

        # translate response text
        if request.user_language and request.user_language != "en":
            yield f"Translating response to {request.user_language}..."
            output_text = run_google_translate(
                texts=output_text,
                source_language="en",
                target_language=request.user_language,
            )

        if references:
            citation_style = (
                request.citation_style and CitationStyles[request.citation_style]
            ) or None
            apply_response_template(output_text, references, citation_style)

        state["output_text"] = output_text

        state["output_audio"] = []
        state["output_video"] = []

        if not request.tts_provider:
            return
        tts_state = dict(state)
        for text in state["output_text"]:
            tts_state["text_prompt"] = text
            yield from TextToSpeechPage().run(tts_state)
            state["output_audio"].append(tts_state["audio_url"])

        if not request.input_face:
            return
        lip_state = dict(state)
        for audio_url in state["output_audio"]:
            lip_state["input_audio"] = audio_url
            yield from LipsyncPage().run(lip_state)
            state["output_video"].append(lip_state["output_video"])

    def get_tabs(self):
        tabs = super().get_tabs()
        tabs.extend([MenuTabs.integrations])
        return tabs

    def render_selected_tab(self, selected_tab):
        super().render_selected_tab(selected_tab)

        if selected_tab == MenuTabs.integrations:
            if not self.request.user or self.request.user.is_anonymous:
                st.write(
                    "**Please Login to connect this workflow to Your Website, Instagram, Whatsapp & More**"
                )
                return

            self.messenger_bot_integration()

            st.markdown(
                """
                ### How to Integrate Chatbots
                """
            )

            col1, col2 = st.columns(2)
            with col1:
                st.write(
                    """
                    #### Part 1:
                    [Interactive Chatbots for your Content - Part 1: Make your Chatbot - How to use Gooey.AI Workflows ](https://youtu.be/-j2su1r8pEg)
                    """
                )
                st.markdown(
                    """
                    <div style="position: relative; padding-bottom: 56.25%; height: 0; width:100%">
                            <iframe src="https://www.youtube.com/embed/-j2su1r8pEg" title="YouTube video player" frameborder="0" webkitallowfullscreen mozallowfullscreen allowfullscreen allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%;">
                    </iframe>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            with col2:
                st.write(
                    """
                    
                    #### Part 2:
                    [Interactive Chatbots for your Content - Part 2: Make your Chatbot - How to use Gooey.AI Workflows ](https://youtu.be/h817RolPjq4)
                    """
                )
                st.markdown(
                    """
                    <div style="position: relative; padding-bottom: 56.25%; height: 0;">
                            <iframe src="https://www.youtube.com/embed/h817RolPjq4" title="YouTube video player" frameborder="0" webkitallowfullscreen mozallowfullscreen allowfullscreen allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%;">
                    </iframe>                    
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            st.write("---")
            st.text_input(
                "###### 🤖 [Landbot](https://landbot.io/) URL", key="landbot_url"
            )

        show_landbot_widget()

    def messenger_bot_integration(self):
        from routers.facebook import ig_connect_url, fb_connect_url
        from routers.slack import slack_connect_url

        st.markdown(
            # language=html
            f"""
            <h3>Connect this bot to your Website, Instagram, Whatsapp & More</h3>       

            Your can connect your FB Messenger account and Slack Workspace here directly.<br>
            If you ping us at support@gooey.ai, we'll add your other accounts too!

            <!--
            <div style='height: 50px'>
                <a target="_blank" class="streamlit-like-btn" href="{ig_connect_url}">
                <img height="20" src="https://www.instagram.com/favicon.ico">️
                &nbsp; 
                Add Your Instagram Page
                </a>
            </div>
            -->
            <div style='height: 50px'>
                <a target="_blank" class="streamlit-like-btn" href="{fb_connect_url}">
                <img height="20" src="https://www.facebook.com/favicon.ico">️             
                &nbsp; 
                Add Your Facebook Page
                </a>
            </div>
            <div style='height: 50px'>
                <a target="_blank" class="streamlit-like-btn" href="{slack_connect_url}">
                <img height="20" src="https://www.slack.com/favicon.ico">             
                &nbsp; 
                Add Your Slack Workspace
                </a>
                <a target="_blank" href="https://docs.google.com/document/d/1EuBaC4TGHTFSOgKYM1eOlisjvPAwLji9dExKwbt2ocA/edit?usp=sharing" class="streamlit-like-btn" aria-label="docs">
                <img height="20" width="0" src="https://www.slack.com/favicon.ico">   <!-- for vertical alignment -->          
                ℹ️
                </a>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.write("---")

        st.button("🔄 Refresh")

        integrations: QuerySet[BotIntegration] = BotIntegration.objects.filter(
            billing_account_uid=self.request.user.uid
        ).order_by("platform")
        if not integrations:
            return

        example_id, run_id, uid = extract_query_params(gooey_get_query_params())

        for bi in integrations:
            if bi.saved_run:
                # same run_id and uid
                if bi.saved_run.run_id and bi.saved_run.uid:
                    is_connected = (
                        bi.saved_run.run_id == run_id and bi.saved_run.uid == uid
                    )
                # same example_id
                elif bi.saved_run.example_id:
                    is_connected = bi.saved_run.example_id == example_id
                # root recipe
                else:
                    is_connected = not (
                        bi.saved_run.run_id
                        or bi.saved_run.uid
                        or bi.saved_run.example_id
                    )
                # same workflow
                is_connected = (
                    is_connected
                    and Workflow(bi.saved_run.workflow) == Workflow.VIDEO_BOTS
                )
            else:
                is_connected = False
            col1, col2, *_ = st.columns([1, 1, 2])
            with col1:
                favicon = Platform(bi.platform).get_favicon()
                st.markdown(
                    # language=html
                    f'<img height="20" width="20" src={favicon!r}>&nbsp;&nbsp;'
                    f"<span>{bi}</span>",
                    unsafe_allow_html=True,
                )
            with col2:
                pressed = st.button(
                    "🔌💔️ Disconnect" if is_connected else "🖇️ Connect",
                    key=f"btn_connect_{bi.id}",
                )
            if not pressed:
                continue
            if is_connected:
                bi.saved_run = None
            else:
                bi.name = st.session_state.get(StateKeys.page_title, bi.name)
                bi.saved_run = self.get_current_doc_sr(
                    example_id=example_id, run_id=run_id, uid=uid
                )
                if bi.platform == Platform.SLACK:
                    from daras_ai_v2.slack_bot import send_confirmation_msg

                    send_confirmation_msg(bi)
            bi.save()
            st.experimental_rerun()

        st.write("---")


def convo_window_clipper(
    window: list[ConversationEntry],
    max_tokens,
    *,
    sep: str = "",
    is_chat_model: bool = True,
    step=2,
):
    for i in range(len(window) - 2, -1, -step):
        if (
            calc_gpt_tokens(window[i:], sep=sep, is_chat_model=is_chat_model)
            > max_tokens
        ):
            return i + step
    return 0


def msg_container_widget(role: str):
    return st.div(
        className="px-3 py-1 pt-2",
        style=dict(
            background="rgba(239, 239, 239, 0.6)"
            if role == CHATML_ROLE_USER
            else "#fff",
        ),
    )
