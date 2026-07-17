import datetime
import json
import tempfile
import typing
from contextlib import contextmanager
from enum import Enum

import gooey_gui as gui
from fastapi import HTTPException, Query
from fastapi.openapi.docs import get_redoc_html
from fastapi.responses import JSONResponse, RedirectResponse
from furl import furl
from loguru import logger
from starlette.datastructures import FormData
from starlette.requests import Request
from starlette.responses import FileResponse, Response

from bots.models import BotIntegration, PublishedRun, Workflow
from bots.models.convo_msg import Conversation, db_msgs_to_api_json
from daras_ai.image_input import safe_filename, upload_file_from_bytes
from daras_ai_v2 import icons, settings
from daras_ai_v2.api_examples_widget import api_example_generator
from daras_ai_v2.asr import FFMPEG_WAV_ARGS, check_wav_audio_format
from daras_ai_v2.copy_to_clipboard_button_widget import copy_to_clipboard_scripts
from daras_ai_v2.exceptions import UserError, ffmpeg
from daras_ai_v2.fastapi_tricks import (
    fastapi_request_form,
    fastapi_request_json,
    get_route_path,
)
from daras_ai_v2.gooey_builder import (
    GOOEY_BUILDER_EVENT_KEY,
    render_gooey_builder,
)
from daras_ai_v2.manage_api_keys_widget import manage_api_keys
from daras_ai_v2.meta_content import build_meta_tags, raw_build_meta_tags
from daras_ai_v2.profiles import get_meta_tags_for_profile, profile_page
from daras_ai_v2.settings import templates
from handles.models import Handle
from routers.custom_api_router import CustomAPIRouter
from routers.static_pages import serve_static_file
from widgets.sidebar import persist_toggle_state, sidebar_layout
from widgets.workflow_search import SearchFilters
from workspaces.widgets import get_current_workspace

if typing.TYPE_CHECKING:
    from daras_ai_v2.base import BasePage


app = CustomAPIRouter()


@app.get("/sitemap.xml/")
def get_sitemap():
    my_sitemap = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">"""

    all_urls = [
        furl(settings.APP_BASE_URL) / path
        for path in [
            "/",
            "/faq",
            "/pricing",
            "/privacy",
            "/terms",
            "/team",
            "/jobs",
            "/farmerchat",
            "/contact",
            "/impact",
            "/explore",
            "/api",
        ]
    ] + [
        pr.get_app_url()
        for pr in (
            PublishedRun.objects.filter(is_approved_example=True).order_by("workflow")
        )
    ]
    for url in all_urls:
        my_sitemap += f"""<url>
          <loc>{url}</loc>
          <lastmod>{datetime.datetime.today().strftime("%Y-%m-%d")}</lastmod>
          <changefreq>daily</changefreq>
          <priority>1.0</priority>
        </url>"""

    my_sitemap += """</urlset>"""

    return Response(content=my_sitemap, media_type="application/xml")


@app.get("/favicon")
@app.get("/favicon.ico")
async def favicon():
    return FileResponse("static/favicon.ico")


@app.get("/docs")
async def redoc_html():
    return get_redoc_html(
        openapi_url="/openapi.json",
        title="GOOEY.AI - ReDoc",
        redoc_js_url="https://unpkg.com/redoc@2/bundles/redoc.standalone.js",
    )


@app.post("/__/file-upload/url/meta")
async def file_upload_meta(body_json: dict = fastapi_request_json):
    return dict(name=body_json["url"], type="url/undefined")


@app.post("/__/file-upload/")
def file_upload(request: Request, form_data: FormData = fastapi_request_form):
    from wand.image import Image
    from routers.firebase_auth import init_firebase_anonymous_user

    file = form_data["file"]
    data = file.file.read()
    if not data:
        return Response(content="No file uploaded", status_code=400)
    filename = file.filename
    content_type = file.content_type

    if content_type.startswith("audio/"):
        with tempfile.NamedTemporaryFile(
            suffix="." + safe_filename(filename)
        ) as infile:
            infile.write(data)
            infile.flush()
            try:
                if not check_wav_audio_format(infile.name):
                    with tempfile.NamedTemporaryFile(suffix=".wav") as outfile:
                        ffmpeg("-i", infile.name, *FFMPEG_WAV_ARGS, outfile.name)

                        filename += ".wav"
                        content_type = "audio/wav"
                        data = outfile.read()
            except UserError as e:
                return Response(content=str(e), status_code=400)

    if content_type.startswith("image/"):
        with Image(blob=data) as img:
            if img.format.lower() not in ["png", "jpeg", "jpg", "gif"]:
                img.format = "png"
                content_type = "image/png"
                filename += ".png"
            img.transform(resize=form_data.get("resize", f"{1024**2}@>"))
            data = img.make_blob()

    if len(data) > settings.MAX_UPLOAD_SIZE:
        return Response(
            content=f"File size exceeds the maximum allowed size of {settings.MAX_UPLOAD_SIZE} bytes",
            status_code=400,
        )

    if not request.user and settings.ENABLE_FIREBASE_AUTH:
        init_firebase_anonymous_user(request)
    if request.user:
        workspace = get_current_workspace(request.user, request.session)
    else:
        workspace = None

    return {
        "url": upload_file_from_bytes(
            filename,
            data,
            content_type,
            workspace=workspace,
            user=request.user,
            is_user_uploaded=True,
        )
    }


@gui.route(app, "/GuiComponents/")
def component_page(request: Request):
    import components_doc

    request.session.setdefault(components_doc.SIDEBAR_KEY + ":default-open", True)
    sidebar, page_content = sidebar_layout(
        key=components_doc.SIDEBAR_KEY,
        session=request.session,
    )

    with sidebar:
        components_doc.render_sidebar_nav()

    with page_content:
        components_doc.render()

    return {
        "meta": raw_build_meta_tags(
            url=get_og_url_path(request),
            title=components_doc.META_TITLE,
            description=components_doc.META_DESCRIPTION,
        ),
    }


@gui.route(app, "/explore/")
def explore_page(
    request: Request, search_filters: typing.Annotated[SearchFilters, Query()]
):
    from widgets import explore

    with sidebar_page_wrapper(
        request, search_filters=search_filters, show_search_bar=False
    ):
        explore.render(request, search_filters)

    return {
        "meta": explore.build_meta_tags(
            url=get_og_url_path(request), search_filters=search_filters
        ),
    }


@gui.route(app, "/explore2/")
def explore2_page(request: Request):
    from widgets import explore2

    with sidebar_page_wrapper(request, show_search_bar=False):
        explore2.render(request)

    return {
        "meta": explore2.build_meta_tags(url=get_og_url_path(request)),
    }


@gui.route(app, "/home/")
def home_page(request: Request):
    from widgets import home

    with sidebar_page_wrapper(request):
        home.render(request)

    return {
        "meta": home.build_meta_tags(url=get_og_url_path(request)),
    }


@app.get("/tools/{toolkit_slug}/{tool_slug}")
def tool_page(request: Request, toolkit_slug: str, tool_slug: str):
    import composio_client
    from composio import Composio

    try:
        tool = Composio().tools.get_raw_composio_tool_by_slug(slug=tool_slug)
    except composio_client.NotFoundError:
        raise HTTPException(status_code=404)
    return JSONResponse(content=tool.to_dict())


@gui.route(app, "/api/")
def api_docs_page(request: Request):
    with sidebar_page_wrapper(request):
        _api_docs_page(request)
    return dict(
        meta=raw_build_meta_tags(
            url=get_og_url_path(request),
            title="Gooey.AI API Platform",
            description="Explore resources, tutorials, API docs, and dynamic examples to get the most out of GooeyAI's developer platform.",
            image="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/e48d59be-aaee-11ee-b112-02420a000175/thumbs/API%20Docs.png_400x400.png",
        )
    )


def _api_docs_page(request: Request):
    from daras_ai_v2.all_pages import all_api_pages

    api_docs_url = str(furl(settings.API_BASE_URL) / "docs")

    gui.markdown(
        f"""
# Gooey.AI API Platform

##### 📖 Introduction 
You can interact with the API through HTTP requests from any language.

If you're comfortable with OpenAPI specs, jump straight to our <a href="{api_docs_url}" target="_blank">complete API</a>

##### 🔐 Authentication
The Gooey.AI API uses API keys for authentication. Visit the [API Keys](#api-keys) section to retrieve the API key you'll use in your requests.

Remember that your API key is a secret! Do not share it with others or expose it in any client-side code (browsers, apps). Production requests must be routed through your own backend server where your API key can be securely loaded from an environment variable or key management service.

All API requests should include your API key in an Authorization HTTP header as follows:

```bash
Authorization: Bearer GOOEY_API_KEY
```
        """,
        unsafe_allow_html=True,
    )

    gui.write("---")
    options = {
        page_cls.workflow.value: page_cls.get_recipe_title()
        for page_cls in all_api_pages
    }

    gui.write(
        "##### ⚕ API Generator\nChoose a workflow to see how you can interact with it via the API"
    )

    col1, col2 = gui.columns([11, 1], responsive=False)
    with col1:
        with gui.div(className="pt-1"):
            workflow = Workflow(
                gui.selectbox(
                    "",
                    options=options,
                    format_func=lambda x: options[x],
                )
            )
    with col2:
        gui.url_button(workflow.page_cls.app_url())

    gui.write("###### 📤 Example Request")

    include_all = gui.checkbox("Show all fields")
    as_async = gui.checkbox("Run Async")
    as_form_data = gui.checkbox("Upload Files via Form Data")

    page = workflow.page_cls(
        user=request.user,
        request_session=request.session,
        request_url=request.url,
        query_params=dict(request.query_params),
    )
    state = page.get_root_pr().saved_run.to_dict()
    api_url, request_body = page.get_example_request(state, include_all=include_all)
    response_body = page.get_example_response_body(
        state, as_async=as_async, include_all=include_all
    )

    api_example_generator(
        api_url=api_url,
        request_body=request_body,
        as_form_data=as_form_data,
        as_async=as_async,
    )
    gui.write("")

    gui.write("###### 🎁 Example Response")
    gui.json(response_body, expanded=True)

    gui.write("---")
    with gui.tag("a", id="api-keys"):
        gui.write("##### 🔐 API keys")

    if not page.request.user or page.request.user.is_anonymous:
        gui.write(
            "**Please [Login](/login/?next=/api/) to generate the `$GOOEY_API_KEY`**"
        )
        return

    manage_api_keys(workspace=page.current_workspace, user=page.request.user)


@gui.route(
    app,
    "/{page_slug}/examples/",
    "/{page_slug}/{run_slug}/examples/",
    "/{page_slug}/{run_slug}-{example_id}/examples/",
)
def examples_route(
    request: Request, page_slug: str, run_slug: str = None, example_id: str = None
):
    return render_recipe_page(request, page_slug, RecipeTabs.examples, example_id)


@gui.route(
    app,
    "/{page_slug}/api/",
    "/{page_slug}/{run_slug}/api/",
    "/{page_slug}/{run_slug}-{example_id}/api/",
)
def api_route(
    request: Request, page_slug: str, run_slug: str = None, example_id: str = None
):
    return render_recipe_page(request, page_slug, RecipeTabs.run_as_api, example_id)


@gui.route(
    app,
    "/{page_slug}/history/",
    "/{page_slug}/{run_slug}/history/",
    "/{page_slug}/{run_slug}-{example_id}/history/",
)
def history_route(
    request: Request, page_slug: str, run_slug: str = None, example_id: str = None
):
    return render_recipe_page(request, page_slug, RecipeTabs.history, example_id)


@gui.route(
    app,
    "/{page_slug}/saved/",
    "/{page_slug}/{run_slug}/saved/",
    "/{page_slug}/{run_slug}-{example_id}/saved/",
)
def save_route(
    request: Request, page_slug: str, run_slug: str = None, example_id: str = None
):
    return render_recipe_page(request, page_slug, RecipeTabs.saved, example_id)


@gui.route(
    app,
    "/{page_slug}/integrations/add/",
    "/{page_slug}/{run_slug}/integrations/add/",
    "/{page_slug}/{run_slug}-{example_id}/integrations/add/",
)
def add_integrations_route(
    request: Request,
    page_slug: str,
    run_slug: str = None,
    example_id: str = None,
):
    gui.session_state["--add-integration"] = True
    return render_recipe_page(request, page_slug, RecipeTabs.integrations, example_id)


@gui.route(
    app,
    "/{page_slug}/integrations/{integration_id}/stats/",
    "/{page_slug}/{run_slug}/integrations/{integration_id}/stats/",
    "/{page_slug}/{run_slug}-{example_id}/integrations/{integration_id}/stats/",
    ###
    "/{page_slug}/integrations/{integration_id}/analysis/",
    "/{page_slug}/{run_slug}/integrations/{integration_id}/analysis/",
    "/{page_slug}/{run_slug}-{example_id}/integrations/{integration_id}/analysis/",
)
def integrations_stats_route(
    request: Request,
    page_slug: str,
    integration_id: str,
    run_slug: str = None,
    example_id: str = None,
    graphs: str = None,
):
    from routers.bots_api import api_hashids

    try:
        gui.session_state.setdefault("bi_id", api_hashids.decode(integration_id)[0])
    except IndexError:
        raise HTTPException(status_code=404)

    if graphs:
        try:
            gui.session_state["analysis_graphs"] = json.loads(graphs)
        except json.JSONDecodeError:
            pass

    return render_recipe_page(request, "stats", RecipeTabs.integrations, example_id)


@gui.route(
    app,
    "/{page_slug}/integrations/",
    "/{page_slug}/{run_slug}/integrations/",
    "/{page_slug}/{run_slug}-{example_id}/integrations/",
    ###
    "/{page_slug}/integrations/{integration_id}/",
    "/{page_slug}/{run_slug}/integrations/{integration_id}/",
    "/{page_slug}/{run_slug}-{example_id}/integrations/{integration_id}/",
)
def integrations_route(
    request: Request,
    page_slug: str,
    run_slug: str = None,
    example_id: str = None,
    integration_id: str = None,
):
    from routers.bots_api import api_hashids

    if integration_id:
        try:
            gui.session_state.setdefault("bi_id", api_hashids.decode(integration_id)[0])
        except IndexError:
            raise HTTPException(status_code=404)
    return render_recipe_page(request, page_slug, RecipeTabs.integrations, example_id)


@gui.route(
    app,
    "/chat/",
    "/chats/",
)
def chat_explore_route(request: Request):
    from daras_ai_v2 import chat_explore

    with sidebar_page_wrapper(request):
        chat_explore.render()

    return dict(
        meta=raw_build_meta_tags(
            url=get_og_url_path(request),
            title="Explore our Bots",
            description="Explore & Chat with our Bots on Gooey.AI",
        ),
    )


@app.get("/chat/{integration_name}-{integration_id}/")
@app.get("/chat/{integration_name}-{integration_id}/share/{conversation_id}/")
def chat_route(
    request: Request,
    integration_id: str | None = None,
    integration_name: str | None = None,
    conversation_id: str | None = None,
):
    from daras_ai_v2.bot_integration_widgets import get_web_widget_embed_code
    from routers.bots_api import api_hashids

    try:
        bi = BotIntegration.objects.get(id=api_hashids.decode(integration_id)[0])
    except (IndexError, BotIntegration.DoesNotExist):
        raise HTTPException(status_code=404)

    if conversation_id:
        try:
            conversation: Conversation = Conversation.objects.get(
                id=api_hashids.decode(conversation_id)[0],
            )
        except (IndexError, Conversation.DoesNotExist):
            raise HTTPException(status_code=404)
        messages = list(db_msgs_to_api_json(conversation.last_n_msgs()))
        conversation_data = dict(
            id=conversation_id,
            bot_id=integration_id,
            timestamp=conversation.created_at.isoformat(),
            user_id=conversation.web_user_id,
            messages=messages,
        )
    else:
        conversation_data = None

    return templates.TemplateResponse(
        "chat_fullscreen.html",
        {
            "request": request,
            "bi": bi,
            "embed_code": get_web_widget_embed_code(
                bi,
                config=dict(
                    mode="fullscreen",
                    conversationData=conversation_data,
                ),
            ),
            "meta": raw_build_meta_tags(
                url=get_og_url_path(request),
                title=f"Chat with {bi.name}",
                description=f"Chat with {bi.name} on Gooey.AI - {bi.descripton}",
                image=bi.photo_url,
            ),
        },
    )


@app.get("/chat/{integration_name}-{integration_id}/lib.js")
def chat_lib_route(request: Request, integration_id: str, integration_name: str = None):
    from routers.bots_api import api_hashids

    try:
        bi = BotIntegration.objects.get(id=api_hashids.decode(integration_id)[0])
    except (IndexError, BotIntegration.DoesNotExist):
        raise HTTPException(status_code=404)

    return Response(
        """
(() => {
let script = document.createElement("script");
    script.src = %(lib_url)r;
    script.onload = function() {
        window.GooeyEmbed.defaultConfig = %(config)s;
    };
    document.body.appendChild(script);
    
    window.GooeyEmbed = new Proxy({}, {
        get: function(target, prop) {
            return (...args) => {
                window.addEventListener("load", () => {
                    window.GooeyEmbed[prop](...args);
                });
            }
        },
    });
})();
        """
        % dict(
            lib_url=settings.WEB_WIDGET_LIB,
            config=json.dumps(bi.get_web_widget_config(hostname=request.url.hostname)),
        ),
        headers={
            "Content-Type": "application/javascript",
            "Cache-Control": "no-store",
        },
    )


@gui.route(
    app,
    "/{page_slug}/preview/",
    "/{page_slug}/{run_slug}/preview/",
    "/{page_slug}/{run_slug}-{example_id}/preview/",
)
def preview_route(
    request: Request, page_slug: str, run_slug: str = None, example_id: str = None
):
    return render_recipe_page(request, page_slug, RecipeTabs.preview, example_id)


@gui.route(
    app,
    "/{path:path}",
    "/{page_slug}/",
    "/{page_slug}/{run_slug}/",
    "/{page_slug}/{run_slug}-{example_id}/",
)
def recipe_or_handle_or_static(
    request: Request, page_slug=None, run_slug=None, example_id=None, path=None
):
    parts = request.url.path.strip("/").split("/")

    # try to render a recipe page
    if len(parts) in {1, 2}:
        try:
            example_id = parts[1].split("-")[-1] or None
        except IndexError:
            example_id = None
        try:
            return render_recipe_page(request, parts[0], RecipeTabs.run, example_id)
        except RecipePageNotFound:
            pass

    # try to render a handle page
    if len(parts) == 1:
        try:
            return render_handle_page(request, parts[0])
        except Handle.DoesNotExist:
            pass

    # try to serve a static file
    return serve_static_file(request)


def render_handle_page(request: Request, name: str):
    handle = Handle.objects.get_by_name(name)
    if handle.has_workspace:
        with sidebar_page_wrapper(request):
            profile_page(request, handle=handle)
        return dict(meta=get_meta_tags_for_profile(handle))
    elif handle.has_redirect:
        return RedirectResponse(
            handle.redirect_url, status_code=301, headers={"Cache-Control": "no-cache"}
        )
    else:
        logger.error(f"Handle {handle.name} has no user or redirect")
        raise HTTPException(status_code=404)


class RecipePageNotFound(HTTPException):
    def __init__(self) -> None:
        super().__init__(status_code=404)


def render_recipe_page(
    request: Request, page_slug: str, tab: "RecipeTabs", example_id: str | None
):
    from daras_ai_v2.all_pages import normalize_slug, page_slug_map

    # lookup the page class
    try:
        page_cls = page_slug_map[normalize_slug(page_slug)]
    except KeyError:
        raise RecipePageNotFound

    # ensure the latest slug is used
    latest_slug = page_cls.canonical_slug()
    if latest_slug != page_slug:
        new_url = furl(request.url)
        for i, seg in enumerate(new_url.path.segments):
            if seg == page_slug:
                new_url.path.segments[i] = latest_slug
                break
        return RedirectResponse(str(new_url.set(origin=None)), status_code=301)

    # ensure the new example_id path param
    if request.query_params.get("example_id"):
        new_url = furl(
            page_cls.app_url(tab=tab, query_params=dict(request.query_params))
        )
        return RedirectResponse(str(new_url.set(origin=None)), status_code=301)

    page = page_cls(
        tab=tab,
        user=request.user,
        request_session=request.session,
        request_url=request.url,
        # this is because the code still expects example_id to be in the query params
        query_params=dict(request.query_params) | dict(example_id=example_id or ""),
    )

    page.load_state()

    with sidebar_page_wrapper(request, page=page):
        page.render()

    return dict(
        meta=build_meta_tags(
            url=get_og_url_path(request), page=page, state=gui.session_state
        ),
    )


def get_og_url_path(request) -> str:
    return str(
        (furl(settings.APP_BASE_URL) / request.url.path).add(request.query_params)
    )


@contextmanager
def sidebar_page_wrapper(
    request: Request,
    className="",
    search_filters: typing.Optional[SearchFilters] = None,
    show_search_bar: bool = True,
    page: typing.Optional["BasePage"] = None,
):
    from widgets import navigation_sidebar

    context = {"request": request, "block_incognito": True}

    display_gooey_builder = page and page.tab in [RecipeTabs.run, RecipeTabs.preview]

    default_collapsed = persist_toggle_state(
        navigation_sidebar.NAV_COLLAPSED_STATE_KEY,
        session=request.session,
        default=False,
    )

    # Column on mobile (rail collapses to an off-canvas drawer + top bar),
    # row on desktop (rail beside content).
    with gui.div(className="d-flex flex-column flex-lg-row min-vh-100 w-100"):
        navigation_sidebar.render(
            request, default_collapsed=default_collapsed, page=page
        )

        with gui.div(className="d-flex flex-column flex-grow-1 min-w-0"):
            sidebar, page_content = sidebar_layout(
                key=GOOEY_BUILDER_EVENT_KEY,
                session=request.session,
                disabled=not display_gooey_builder,
            )
            with (
                page_content,
                gui.div(className="d-flex flex-column min-vh-100 w-100"),
            ):
                gui.html(templates.get_template("gtag.html").render(**context))
                gui.html(copy_to_clipboard_scripts)

                if request.user and not request.user.is_anonymous:
                    current_workspace = get_current_workspace(
                        request.user, request.session
                    )

                    if display_gooey_builder:
                        with sidebar:
                            render_gooey_builder(
                                event_key=GOOEY_BUILDER_EVENT_KEY,
                                request=request,
                                page=page,
                            )
                else:
                    current_workspace = None

                with gui.div(className="container-xxl"):
                    with gui.div(id="main-content", className=className):
                        yield current_workspace

                    gui.html(templates.get_template("footer.html").render(**context))
                    gui.html(
                        templates.get_template("login_scripts.html").render(**context)
                    )


class TabData(typing.NamedTuple):
    title: str
    label: str
    route: typing.Callable


PREVIEW_ROUTE_WORKFLOWS = [Workflow.VIDEO_BOTS]


class RecipeTabs(TabData, Enum):
    preview = TabData(
        title=f"<span class='mobile-only-recipe-tab'>{icons.preview} Preview</span>",
        label="",
        route=preview_route,
    )
    run = TabData(
        title=f"{icons.run} Run",
        label="",
        route=recipe_or_handle_or_static,
    )
    examples = TabData(
        title=f"{icons.example} Examples",
        label="Examples",
        route=examples_route,
    )
    run_as_api = TabData(
        title=f"{icons.api} API",
        label="API",
        route=api_route,
    )
    history = TabData(
        title=f"{icons.history} History",
        label="History",
        route=history_route,
    )
    integrations = TabData(
        title=f'<img width="20" height="20" style="margin-right: 4px;margin-top: -3px" src="{icons.integrations_img}" alt="Facebook, Whatsapp, Slack, Instagram Icons"> Deploy',
        label="Deploy",
        route=integrations_route,
    )
    saved = TabData(
        title=f"{icons.save} Saved",
        label="Saved Runs",
        route=save_route,
    )

    def url_path(
        self,
        page_slug: str,
        run_slug: str | None = None,
        example_id: str | None = None,
        **kwargs,
    ) -> str:
        kwargs["page_slug"] = page_slug
        if example_id:
            kwargs["example_id"] = example_id
            kwargs["run_slug"] = run_slug or "untitled"
        return get_route_path(self.route, kwargs)
