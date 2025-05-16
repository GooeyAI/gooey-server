from __future__ import annotations

import json
import typing
from textwrap import indent

import gooey_gui as gui
from furl import furl
from starlette.requests import Request
from starlette.responses import RedirectResponse

from app_users.models import AppUser
from bots.models import PublishedRun
from daras_ai_v2 import settings
from daras_ai_v2.html_spinner_widget import html_spinner
from routers.custom_api_router import CustomAPIRouter
from routers.root import page_wrapper
from workspaces.models import Workspace

if typing.TYPE_CHECKING:
    pass

app = CustomAPIRouter()


@gui.route(app, "/pycon")
def pycon_page(request: Request):
    if not request.user or request.user.is_anonymous:
        redirect_url = furl("/login", query_params={"next": request.url})
        return RedirectResponse(str(redirect_url))

    key = "bot_generator"

    with page_wrapper(request) as workspace:
        gui.write("# Pycon 2025 Demo")

        description = gui.text_area(
            "#### Requirements\nWhat do you want your bot to do?"
        )

        if gui.button("Generate Bot"):
            run_bot_generator(
                key, workspace=workspace, user=request.user, description=description
            )
            gui.session_state.pop("run_url", None)

        gui.write("---")

        is_generating, error_msg = pull_bot_generator_result(key=key)
        if is_generating:
            html_spinner("Generating...")
        run_url = gui.session_state.get(key + ":bot-run-url")
        if run_url:
            gui.caption(f"[View Generation URL]({run_url})")
        if error_msg:
            gui.error(error_msg)
            return

        config = gui.session_state.get(key)
        if not config:
            return

        config |= dict(integration_id="Kbo", mode="inline", target="#gooey-embed")

        with gui.expander("👩‍💻 Embed code", expanded=True):
            gui.write(
                """
```html
<div id="gooey-embed"></div>
<script>
  function onLoadGooeyEmbed() {
    GooeyEmbed.mount(%s);
  }
</script>
<script async defer onload="onLoadGooeyEmbed()" src="https://gooey.ai/chat/gooey-base-copilot-Kbo/lib.js"></script>
```
"""
                % indent(json.dumps(config, indent=2), "    ").strip(),
                unsafe_allow_html=True,
            )

        run_url = gui.session_state.get("run_url")
        if not run_url:
            pr = PublishedRun.objects.get(published_run_id="v1xm6uhp")
            _, sr = pr.submit_api_call(
                workspace=workspace,
                request_body=config["payload"] | dict(input_prompt=""),
                current_user=request.user,
            )
            run_url = gui.session_state["run_url"] = sr.get_app_url()

        gui.caption(f"[View & Edit Run]({run_url})")

        gui.html(
            # language=html
            """
            <div id="gooey-embed" class="border rounded mb-5" style="height: 80vh"></div>
            <script id="gooey-embed-script" src="https://cdn.jsdelivr.net/gh/GooeyAI/gooey-web-widget@2/dist/lib.js"></script>
            """
        )
        gui.js(
            # language=javascript
            """
            async function loadGooeyEmbed() {
                await window.waitUntilHydrated;
                if (typeof GooeyEmbed === 'undefined') return;
                GooeyEmbed.unmount();
                GooeyEmbed.mount(config);
            }
            const script = document.getElementById("gooey-embed-script");
            if (script) script.onload = loadGooeyEmbed;
            loadGooeyEmbed();
            """,
            config=config,
        )


PROMPT_FORMAT = '''\
Description: """
%s
"""
Respond with the following JSON object: 
{ 
   // branding for the web widget
   branding: {
    // (required)
    name: string,
    byLine: string,
    description: string,
    conversationStarters: string[],
    // (optional)
    fabLabel?: string,
    photoUrl?: string,
    websiteUrl?: string,
    showPoweredByGooey?: boolean,
  },
  // payload for the AI backend
  payload: {
    // (required) instructions for the bot
    bot_script: string
    // (optional) selected LLM model 
    selected_model?: string Enum - "gpt_4_1" "gpt_4_1_mini" "gpt_4_1_nano" "gpt_4_5" "o4_mini" "o3" "o3_mini" "o1" "o1_preview" "o1_mini" "gpt_4_o" "gpt_4_o_mini" "gpt_4_o_audio" "gpt_4_o_mini_audio" "chatgpt_4_o" "gpt_4_turbo_vision" "gpt_4_vision" "gpt_4_turbo" "gpt_4" "gpt_4_32k" "gpt_3_5_turbo" "gpt_3_5_turbo_16k" "gpt_3_5_turbo_instruct" "deepseek_r1" "llama4_maverick_17b_128e" "llama4_scout_17b_16e" "llama3_3_70b" "llama3_2_90b_vision" "llama3_2_11b_vision" "llama3_2_3b" "llama3_2_1b" "llama3_1_405b" "llama3_1_70b" "llama3_1_8b" "llama3_70b" "llama3_8b" "pixtral_large" "mistral_large" "mistral_small_24b_instruct" "mixtral_8x7b_instruct_0_1" "gemma_2_9b_it" "gemma_7b_it" "gemini_2_5_pro_preview" "gemini_2_5_flash_preview" "gemini_2_flash_lite" "gemini_2_flash" "gemini_1_5_flash" "gemini_1_5_pro" "gemini_1_pro_vision" "gemini_1_pro" "palm2_chat" "palm2_text" "claude_3_7_sonnet" "claude_3_5_sonnet" "claude_3_opus" "claude_3_sonnet" "claude_3_haiku" "afrollama_v1" "llama3_8b_cpt_sea_lion_v2_1_instruct" "sarvam_2b" "llama_3_groq_70b_tool_use" "llama_3_groq_8b_tool_use" "llama2_70b_chat" "sea_lion_7b_instruct" "llama3_8b_cpt_sea_lion_v2_instruct" "text_davinci_003" "text_davinci_002" "code_davinci_002" "text_curie_001" "text_babbage_001" "text_ada_001"
    // (optional) speech recognition model
    asr_model?: string Enum  - "whisper_large_v2" "whisper_large_v3" "gpt_4_o_audio" "gpt_4_o_mini_audio" "gcp_v1" "usm" "deepgram" "azure" "seamless_m4t_v2" "mms_1b_all" "ghana_nlp_asr_v2" "lelapa" "seamless_m4t" "whisper_chichewa_large_v3" "nemo_english" "nemo_hindi" "whisper_hindi_large_v2" "whisper_telugu_large_v2" "vakyansh_bhojpuri"
    // (optional) translation model
    translation_model?: string Enum - "google" "ghana_nlp" "lelapa" "whisper_large_v2" "whisper_large_v3" "seamless_m4t_v2"
    // (optional) user language code
    user_language?: string
    // (optional) text to speech provider
    tts_provider?: string Enum - "GOOGLE_TTS" "ELEVEN_LABS" "UBERDUCK" "BARK" "AZURE_TTS" "OPEN_AI" "GHANA_NLP"
    // (optional) url to a face image for lipsync
    input_face?: string
    // (optional) knowledge base document URLs
    documents?: string[]
  },
}\
'''


def run_bot_generator(
    key: str, workspace: Workspace, user: AppUser, description: str
) -> str:
    from recipes.VideoBots import VideoBotsPage

    prompt = PROMPT_FORMAT % (description,)
    pr = VideoBotsPage.get_pr_from_example_id(
        example_id=settings.BOT_GENERATOR_EXAMPLE_ID
    )
    result, sr = pr.submit_api_call(
        workspace=workspace,
        current_user=user,
        request_body=dict(
            input_prompt=prompt,
            messages=[],
            response_format_type="json_object",
        ),
        deduct_credits=False,
    )
    gui.session_state[key + ":bot-channel"] = VideoBotsPage.realtime_channel_name(
        sr.run_id, sr.uid
    )
    gui.session_state[key + ":bot-run-url"] = sr.get_app_url()


def pull_bot_generator_result(key: str) -> tuple[bool, str | None]:
    """
    Pulls the result from the QR bot and updates the session state with the result.
    Returns a tuple of (success, error_msg).
    """
    from daras_ai_v2.base import RecipeRunState, StateKeys
    from recipes.VideoBots import VideoBotsPage

    channel = gui.session_state.get(key + ":bot-channel")
    error_msg = None
    if not channel:
        return False, error_msg

    state = gui.realtime_pull([channel])[0]
    recipe_run_state = state and VideoBotsPage.get_run_state(state)
    match recipe_run_state:
        case RecipeRunState.failed:
            error_msg = state.get(StateKeys.error_msg)
        case RecipeRunState.completed:
            result = json.loads(state.get("output_text", ["{}"])[0])
            error_msg = result.get("error")
            gui.session_state[key] = result
        case _:
            return True, error_msg

    gui.session_state.pop(key + ":bot-channel", None)
    return False, error_msg
