from __future__ import annotations

import typing

import gooey_gui as gui
from starlette.requests import Request

from bots.models import BotIntegration
from daras_ai_v2 import settings
from workspaces.models import Workspace

if typing.TYPE_CHECKING:
    from daras_ai_v2.base import BasePage

DEFAULT_GOOEY_BUILDER_PHOTO_URL = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/63bdb560-b891-11f0-b9bc-02420a00014a/generate-ai-abstract-symbol-artificial-intelligence-colorful-stars-icon-vector%201.jpg"


def render_gooey_builder_launcher(
    sidebar_key: str,
    request: Request,
    current_workspace: Workspace | None,
):
    if not can_launch_gooey_builder(request, current_workspace):
        return

    try:
        bi = BotIntegration.objects.get(id=settings.GOOEY_BUILDER_INTEGRATION_ID)
    except BotIntegration.DoesNotExist:
        return
    branding = bi.get_web_widget_branding()
    photo_url = branding.get("photoUrl", DEFAULT_GOOEY_BUILDER_PHOTO_URL)

    with gui.styled("& button:hover { scale: 1.2; }"):
        with gui.div(
            className="position-fixed d-none d-xxl-block",
            style={"bottom": "24px", "left": "16px", "zIndex": "1000"},
        ):
            with gui.tag(
                "button",
                type="button",
                className=f"btn btn-secondary border-0 p-0 {sidebar_key}-button",
                onClick=f"window.dispatchEvent(new CustomEvent(`{sidebar_key}:open`))",
                style={
                    "width": "56px",
                    "height": "56px",
                    "borderRadius": "50%",
                    "boxShadow": "#0000001a 0 1px 4px, #0003 0 2px 12px",
                },
            ):
                gui.html(
                    f"<img src='{photo_url}' style='width: 56px; height: 56px; border-radius: 50%;' />"
                )

    with gui.tag(
        "button",
        type="button",
        className=f"border-0 m-0 btn btn-secondary rounded-pill d-xxl-none p-0 {sidebar_key}-button",
        onClick=f"window.dispatchEvent(new CustomEvent(`{sidebar_key}:open`))",
        style={
            "width": "36px",
            "height": "36px",
            "borderRadius": "50%",
        },
    ):
        gui.html(
            f"<img src='{photo_url}' style='width: 36px; height: 36px; border-radius: 50%;' />"
        )


def render_gooey_builder(
    *,
    sidebar_key: str,
    request: Request,
    page: BasePage | None,
    current_workspace: Workspace | None,
):
    from daras_ai_v2.base import StateKeys, extract_model_fields

    if not can_launch_gooey_builder(request, current_workspace):
        return

    with gui.div(className="w-100 h-100"):
        update_gui_state: dict | None = gui.session_state.pop("update_gui_state", None)
        if update_gui_state:
            gui.session_state.update(update_gui_state)
            sr = page.create_and_validate_new_run(
                enable_rate_limits=True, run_status=None
            )
            if sr:
                raise gui.RedirectException(sr.get_app_url())

        render_gooey_builder_inline(
            sidebar_key=sidebar_key,
            page_slug=page.slug_versions[-1],
            builder_state=dict(
                status=dict(
                    error_msg=gui.session_state.get(StateKeys.error_msg),
                    run_status=gui.session_state.get(StateKeys.run_status),
                    run_time=gui.session_state.get(StateKeys.run_time),
                ),
                request=extract_model_fields(
                    model=page.RequestModel, state=gui.session_state
                ),
                response=extract_model_fields(
                    model=page.ResponseModel, state=gui.session_state
                ),
                metadata=dict(
                    title=page.current_pr.title,
                    description=page.current_pr.notes,
                ),
            ),
        )


def render_gooey_builder_inline(
    *, sidebar_key: str, page_slug: str, builder_state: dict
):
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
        window.dispatchEvent(new CustomEvent(`${sidebar_key}:close`))
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
        sidebar_key=sidebar_key,
    )


def can_launch_gooey_builder(
    request: Request, current_workspace: Workspace | None
) -> bool:
    if not settings.GOOEY_BUILDER_INTEGRATION_ID:
        return False
    if not request.user or request.user.is_anonymous:
        return False
    if request.user.is_admin():
        return True
    return current_workspace and current_workspace.enable_bot_builder
