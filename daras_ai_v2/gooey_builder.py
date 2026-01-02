import gooey_gui as gui

from bots.models import BotIntegration
from daras_ai_v2 import settings
from widgets.sidebar import SidebarRef, use_sidebar
from starlette.requests import Request

from workspaces.models import Workspace

DEFAULT_GOOEY_BUILDER_PHOTO_URL = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/63bdb560-b891-11f0-b9bc-02420a00014a/generate-ai-abstract-symbol-artificial-intelligence-colorful-stars-icon-vector%201.jpg"


def can_launch_gooey_builder(
    request: Request, current_workspace: Workspace | None
) -> bool:
    if not request.user or request.user.is_anonymous:
        return False
    if request.user.is_admin():
        return True
    return current_workspace and current_workspace.enable_bot_builder


def render_gooey_builder_launcher(
    request: Request,
    current_workspace: Workspace | None = None,
    is_fab_button: bool = False,
):
    if not can_launch_gooey_builder(request, current_workspace):
        return
    from bots.models import BotIntegration

    sidebar_ref = use_sidebar("builder-sidebar", request.session)
    bi = BotIntegration.objects.get(id=settings.GOOEY_BUILDER_INTEGRATION_ID)
    branding = bi.get_web_widget_branding()
    photo_url = branding.get(
        "photoUrl",
        DEFAULT_GOOEY_BUILDER_PHOTO_URL,
    )
    branding["showPoweredByGooey"] = False
    if is_fab_button:
        with gui.styled("& .gooey-builder-open-button:hover { scale: 1.2; }"):
            with gui.div(
                className="w-100 position-absolute",
                style={"bottom": "24px", "left": "16px", "zIndex": "1000"},
            ):
                gooey_builder_open_button = gui.button(
                    label=f"<img src='{photo_url}' style='width: 56px; height: 56px; border-radius: 50%;' />",
                    className="btn btn-secondary border-0 d-none d-md-block p-0 gooey-builder-open-button",
                    style={
                        "width": "56px",
                        "height": "56px",
                        "borderRadius": "50%",
                        "boxShadow": "#0000001a 0 1px 4px, #0003 0 2px 12px",
                    },
                )
            if gooey_builder_open_button:
                sidebar_ref.set_open(True)
                raise gui.RerunException()
    else:
        gooey_builder_mobile_open_button = gui.button(
            label=f"<img src='{photo_url}' style='width: 36px; height: 36px; border-radius: 50%;' />",
            className="border-0 m-0 btn btn-secondary rounded-pill d-md-none gooey-builder-open-button p-0",
            style={
                "width": "36px",
                "height": "36px",
                "borderRadius": "50%",
            },
        )
        if gooey_builder_mobile_open_button:
            sidebar_ref.set_mobile_open(True)
            raise gui.RerunException()


def render_gooey_builder_inline(
    page_slug: str, builder_state: dict, sidebar_ref: SidebarRef
):
    if not settings.GOOEY_BUILDER_INTEGRATION_ID:
        return

    # hidden button to trigger the onClose event passed in the widget config
    gui.tag(
        "button",
        type="submit",
        name="onCloseGooeyBuilder",
        value="yes",
        hidden=True,
        id="onClose",
    )

    if gui.session_state.pop("onCloseGooeyBuilder", None):
        sidebar_ref.set_open(False)
        raise gui.RerunException()

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
