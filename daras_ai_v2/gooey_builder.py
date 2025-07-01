import typing
import uuid

import gooey_gui as gui
from pydantic import BaseModel

from bots.models import BotIntegration
from daras_ai_v2 import settings


def render_gooey_builder(
    page_slug: str,
    request_model: typing.Type[BaseModel],
    load_session_state: typing.Callable[[], dict],
):
    from daras_ai_v2.base import extract_model_fields

    if not settings.GOOEY_BUILDER_INTEGRATION_ID:
        return

    request_state = extract_model_fields(model=request_model, state=gui.session_state)

    # pull updates from UpdateGuiStateLLMTool
    channel_key = "-gooey-builder-channel"
    channel = gui.session_state.setdefault(
        channel_key, f"gooey-bot-builder/{uuid.uuid4()}"
    )
    updates = gui.realtime_pull([channel])[0]

    # use the nonce to detect if the state has changed, avoid re-applying the state if it has not changed
    nonce_key = "-gooey-builder-nonce"
    if updates and updates.get(nonce_key) != gui.session_state.get(nonce_key):
        gui.session_state.clear()
        gui.session_state.update(load_session_state() | request_state | updates)
        gui.session_state[channel_key] = channel

    bi = BotIntegration.objects.get(id=settings.GOOEY_BUILDER_INTEGRATION_ID)
    config = bi.get_web_widget_config(
        hostname="gooey.ai", target="#gooey-builder-embed"
    )

    branding = config.setdefault("branding", {})
    branding["showPoweredByGooey"] = False

    variables = config.setdefault("payload", {}).setdefault("variables", {})
    variables["update_gui_state_params"] = dict(
        channel=channel,
        state=request_state,
        page_slug=page_slug,
    )

    gui.html(
        # language=html
        f"""
<div id="gooey-builder-embed"></div>
<script id="gooey-builder-embed-script" src="{settings.WEB_WIDGET_LIB}"></script>
        """
    )
    gui.js(
        # language=javascript
        """
async function onload() {
    await window.waitUntilHydrated;
    if (typeof GooeyEmbed === "undefined" ||
        document.getElementById("gooey-builder-embed")?.children.length)
        return;
    GooeyEmbed.mount(config);
}

const script = document.getElementById("gooey-builder-embed-script");
if (script) script.onload = onload;
onload();
window.addEventListener("hydrated", onload);
        """,
        config=config,
    )
