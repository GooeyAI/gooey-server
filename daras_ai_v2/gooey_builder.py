import gooey_gui as gui

from bots.models import BotIntegration
from daras_ai_v2 import settings


def render_gooey_builder_inline(page_slug: str, builder_state: dict):
    if not settings.GOOEY_BUILDER_INTEGRATION_ID:
        return

    bi = BotIntegration.objects.get(id=settings.GOOEY_BUILDER_INTEGRATION_ID)
    config = bi.get_web_widget_config(
        hostname="gooey.ai", target="#gooey-builder-embed"
    )

    config["mode"] = "inline"
    config["showRunLink"] = True
    branding = config.setdefault("branding", {})
    branding["showPoweredByGooey"] = False

    config.setdefault("payload", {}).setdefault("variables", {})
    # will be added later in the js code
    variables = dict(
        update_gui_state_params=dict(state=builder_state, page_slug=page_slug),
    )

    gui.html(
        # language=html
        f"""
<div id="gooey-builder-embed" style="height: 100%"></div>
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
    
    // this is a trick to update the variables after the widget is already mounted
    GooeyEmbed.setGooeyBuilderVariables = (value) => {
        config.payload.variables = value;
    };
    
    GooeyEmbed.setGooeyBuilderVariables(variables);
    
    config.onClose = function() {
        document.getElementById("onClose").click();
    };
    GooeyEmbed.mount(config);
}

const script = document.getElementById("gooey-builder-embed-script");
if (script) script.onload = onload;
onload();
window.addEventListener("hydrated", onload);

// if the widget is already mounted, update the variables
if (typeof GooeyEmbed !== "undefined" && GooeyEmbed.setGooeyBuilderVariables) {
    GooeyEmbed.setGooeyBuilderVariables(variables);
}
        """,
        config=config,
        variables=variables,
    )


def render_gooey_builder(page_slug: str, builder_state: dict):
    if not settings.GOOEY_BUILDER_INTEGRATION_ID:
        return

    bi = BotIntegration.objects.get(id=settings.GOOEY_BUILDER_INTEGRATION_ID)
    config = bi.get_web_widget_config(
        hostname="gooey.ai", target="#gooey-builder-embed"
    )

    branding = config.setdefault("branding", {})
    branding["showPoweredByGooey"] = False

    config.setdefault("payload", {}).setdefault("variables", {})
    # will be added later in the js code
    variables = dict(
        update_gui_state_params=dict(state=builder_state, page_slug=page_slug),
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
    
    // this is a trick to update the variables after the widget is already mounted
    GooeyEmbed.setGooeyBuilderVariables = (value) => {
        config.payload.variables = value;
    };
    GooeyEmbed.setGooeyBuilderVariables(variables);
    
    GooeyEmbed.mount(config);
}

const script = document.getElementById("gooey-builder-embed-script");
if (script) script.onload = onload;
onload();
window.addEventListener("hydrated", onload);

// if the widget is already mounted, update the variables
if (typeof GooeyEmbed !== "undefined" && GooeyEmbed.setGooeyBuilderVariables) {
    GooeyEmbed.setGooeyBuilderVariables(variables);
}
        """,
        config=config,
        variables=variables,
    )
