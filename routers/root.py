import datetime
import json
import tempfile
import traceback
import typing
from contextlib import contextmanager
from enum import Enum
from textwrap import dedent
from time import time

import gooey_gui as gui
import sentry_sdk
from fastapi import Depends, HTTPException
from fastapi.responses import RedirectResponse
from firebase_admin import auth, exceptions
from furl import furl
from loguru import logger
from starlette.datastructures import FormData
from starlette.requests import Request
from starlette.responses import (
    FileResponse,
    PlainTextResponse,
    Response,
)

from app_users.models import AppUser
from bots.models import BotIntegration, PublishedRun, Workflow
from daras_ai.image_input import safe_filename, upload_file_from_bytes
from daras_ai_v2 import icons, settings
from daras_ai_v2.api_examples_widget import api_example_generator
from daras_ai_v2.asr import FFMPEG_WAV_ARGS, check_wav_audio_format
from daras_ai_v2.copy_to_clipboard_button_widget import copy_to_clipboard_scripts
from daras_ai_v2.db import FIREBASE_SESSION_COOKIE
from daras_ai_v2.exceptions import UserError, ffmpeg
from daras_ai_v2.fastapi_tricks import (
    fastapi_request_form,
    fastapi_request_json,
    get_app_route_url,
    get_route_path,
    resolve_url,
)
from daras_ai_v2.manage_api_keys_widget import manage_api_keys
from daras_ai_v2.meta_content import build_meta_tags, raw_build_meta_tags
from daras_ai_v2.meta_preview_url import meta_preview_url
from daras_ai_v2.profiles import get_meta_tags_for_profile, profile_page
from daras_ai_v2.settings import templates
from handles.models import Handle
from routers.custom_api_router import CustomAPIRouter
from routers.static_pages import serve_static_file
from workspaces.widgets import global_workspace_selector

if typing.TYPE_CHECKING:
    from widgets.workflow_search import SearchFilters

app = CustomAPIRouter()

DEFAULT_LOGIN_REDIRECT = "/explore/"
DEFAULT_LOGOUT_REDIRECT = "/"


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


@app.get("/login/")
def login(request: Request):
    from routers.account import invitation_route, load_invite_from_hashid_or_404

    if request.user and not request.user.is_anonymous:
        return RedirectResponse(
            request.query_params.get("next", DEFAULT_LOGIN_REDIRECT)
        )
    context = {
        "request": request,
    }

    try:
        if (
            (next_url := request.query_params.get("next"))
            and (match := resolve_url(next_url))
            and match.route.name == invitation_route.__name__
            and (invite_id := match.matched_params.get("invite_id"))
        ):
            context["invite"] = load_invite_from_hashid_or_404(invite_id)
    except Exception as e:
        traceback.print_exc()
        sentry_sdk.capture_exception(e)

    return templates.TemplateResponse(
        "login_options.html",
        context=context,
    )


async def form_id_token(request: Request):
    form = await request.form()
    return form.get("idToken", "")


@app.post("/login/")
def authentication(request: Request, id_token: bytes = Depends(form_id_token)):
    ## Taken from https://firebase.google.com/docs/auth/admin/manage-cookies#create_session_cookie

    # To ensure that cookies are set only on recently signed in users, check auth_time in
    # ID token before creating a cookie.
    try:
        decoded_claims = auth.verify_id_token(id_token)
        # Only process if the user signed in within the last 5 minutes.
        if time() - decoded_claims["auth_time"] < 5 * 60:
            expires_in = datetime.timedelta(days=14)
            session_cookie = auth.create_session_cookie(id_token, expires_in=expires_in)
            request.session[FIREBASE_SESSION_COOKIE] = session_cookie
            uid = decoded_claims["uid"]
            # upgrade an anonymous account to a permanent account
            try:
                existing_user = AppUser.objects.get(uid=uid)
                if existing_user.is_anonymous:
                    existing_user.copy_from_firebase_user(auth.get_user(uid))
            except AppUser.DoesNotExist:
                pass
            return RedirectResponse(
                request.query_params.get("next", DEFAULT_LOGIN_REDIRECT),
                status_code=303,
            )
        # User did not sign in recently. To guard against ID token theft, require
        # re-authentication.
        return PlainTextResponse(status_code=401, content="Recent sign in required")
    except auth.InvalidIdTokenError:
        return PlainTextResponse(status_code=401, content="Invalid ID token")
    except exceptions.FirebaseError:
        return PlainTextResponse(
            status_code=401, content="Failed to create a session cookie"
        )


@app.get("/logout/")
async def logout(request: Request):
    request.session.pop(FIREBASE_SESSION_COOKIE, None)
    return RedirectResponse(request.query_params.get("next", DEFAULT_LOGOUT_REDIRECT))


@app.post("/__/file-upload/url/meta")
async def file_upload_meta(body_json: dict = fastapi_request_json):
    return dict(name=body_json["url"], type="url/undefined")


@app.post("/__/file-upload/")
def file_upload(form_data: FormData = fastapi_request_form):
    from wand.image import Image

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

    return {"url": upload_file_from_bytes(filename, data, content_type)}


@gui.route(app, "/GuiComponents/")
def component_page(request: Request):
    import components_doc

    with page_wrapper(request):
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
    request: Request,
    search: str = "",
    workspace: str = "",
    workflow: str = "",
):
    from widgets import explore
    from widgets.workflow_search import SearchFilters

    search_filters = SearchFilters(
        search=search, workspace=workspace, workflow=workflow
    )
    with page_wrapper(request, search_filters=search_filters):
        explore.render(request.user, search_filters)

    return {
        "meta": raw_build_meta_tags(
            url=get_og_url_path(request),
            title=explore.META_TITLE,
            description=explore.META_DESCRIPTION,
        ),
    }


@gui.route(app, "/api/")
def api_docs_page(request: Request):
    with page_wrapper(request):
        _api_docs_page(request)
    return dict(
        meta=raw_build_meta_tags(
            url=get_og_url_path(request),
            title="Gooey.AI API Platform",
            description="Explore resources, tutorials, API docs, and dynamic examples to get the most out of GooeyAI's developer platform.",
            image=meta_preview_url(
                "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/e48d59be-aaee-11ee-b112-02420a000175/API%20Docs.png.png"
            )[0],
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

    with page_wrapper(request):
        chat_explore.render()

    return dict(
        meta=raw_build_meta_tags(
            url=get_og_url_path(request),
            title="Explore our Bots",
            description="Explore & Chat with our Bots on Gooey.AI",
        ),
    )


@app.get("/chat/{integration_name}-{integration_id}/")
def chat_route(
    request: Request, integration_id: str = None, integration_name: str = None
):
    from daras_ai_v2.bot_integration_widgets import get_web_widget_embed_code
    from routers.bots_api import api_hashids

    try:
        bi = BotIntegration.objects.get(id=api_hashids.decode(integration_id)[0])
    except (IndexError, BotIntegration.DoesNotExist):
        raise HTTPException(status_code=404)

    return templates.TemplateResponse(
        "chat_fullscreen.html",
        {
            "request": request,
            "bi": bi,
            "embed_code": get_web_widget_embed_code(bi, config=dict(mode="fullscreen")),
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
        with page_wrapper(request):
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
    latest_slug = page_cls.slug_versions[-1]
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
        query_params=dict(request.query_params) | dict(example_id=example_id),
    )

    if not gui.session_state:
        gui.session_state.update(page.current_sr_to_session_state())

    with page_wrapper(request):
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


def _render_search_bar_with_redirect(
    request: Request, search_filters: typing.Optional["SearchFilters"], **props
):
    from widgets.workflow_search import SearchFilters, render_search_bar

    search_filters = search_filters or SearchFilters()
    search_query = render_search_bar(value=search_filters.search, **props)
    if search_query != search_filters.search:
        search_filters.search = search_query
        raise gui.RedirectException(
            get_app_route_url(
                explore_page,
                query_params=search_filters.model_dump(exclude_defaults=True),
            )
        )


def get_js_hide_mobile_search():
    return dedent("""
    event.preventDefault();
    const hide_on_mobile_search = document.querySelectorAll('.hide_on_mobile_search');
    const show_on_mobile_search = document.querySelectorAll('.show_on_mobile_search');
    hide_on_mobile_search.forEach(el => el.style.setProperty('display', 'flex'));
    show_on_mobile_search.forEach(el => el.style.setProperty('display', 'none'));
    """)


def get_js_show_mobile_search():
    return dedent("""
    event.preventDefault();
    const hide_on_mobile_search = document.querySelectorAll('.hide_on_mobile_search');
    const show_on_mobile_search = document.querySelectorAll('.show_on_mobile_search');
    hide_on_mobile_search.forEach(el => el.style.setProperty('display', 'none'));
    show_on_mobile_search.forEach(el => el.style.setProperty('display', 'flex'));
    document.querySelector('#search_bar').focus();
    """)


@contextmanager
def page_wrapper(
    request: Request,
    className="",
    search_filters: typing.Optional["SearchFilters"] = None,
):
    context = {"request": request, "block_incognito": True}

    with gui.div(className="d-flex flex-column min-vh-100"):
        gui.html(templates.get_template("gtag.html").render(**context))

        with (
            gui.div(className="header"),
            gui.div(className="navbar navbar-expand-xl bg-transparent p-0 m-0"),
            gui.div(className="container-xxl my-2"),
            gui.div(className="w-100 d-flex gap-2"),
        ):
            with (
                gui.div(className="hide_on_mobile_search d-md-block"),
                gui.tag("a", href="/"),
            ):
                gui.tag(
                    "img",
                    src=settings.GOOEY_LOGO_IMG,
                    width="300",
                    height="142",
                    className="img-fluid logo d-none d-sm-block",
                )
                gui.tag(
                    "img",
                    src=settings.GOOEY_LOGO_RECT,
                    width="145",
                    height="40",
                    className="img-fluid logo d-sm-none",
                )

            with gui.div(
                className="flex-grow-1 d-flex justify-content-center align-items-center"
            ):
                with gui.div(
                    className="show_on_mobile_search d-md-flex flex-grow-1 justify-content-center align-items-center",
                    style={"display": "none"},
                    onBlur=get_js_hide_mobile_search(),
                ):
                    _render_search_bar_with_redirect(
                        request, search_filters, id="search_bar"
                    )
                with gui.div(
                    className="hide_on_mobile_search d-md-none flex-grow-1 justify-content-end",
                    style={"display": "flex"},
                ):
                    gui.button(
                        icons.search,
                        type="tertiary",
                        unsafe_allow_html=True,
                        className="m-0",
                        onClick=get_js_show_mobile_search(),
                    )

            with gui.div(
                className="hide_on_mobile_search gap-2 d-md-flex justify-content-end flex-wrap align-items-center",
                style={"display": "flex", "maxWidth": "50%"},
            ):
                for url, label in settings.HEADER_LINKS:
                    with gui.tag("a", href=url, className="pe-2 d-none d-xl-block"):
                        if icon := settings.HEADER_ICONS.get(url):
                            with gui.div(className="d-inline-block me-2 small"):
                                gui.html(icon)
                        gui.html(label)

                if request.user and not request.user.is_anonymous:
                    current_workspace = global_workspace_selector(
                        request.user, request.session
                    )
                else:
                    current_workspace = None
                    anonymous_login_container(request, context)

        gui.html(copy_to_clipboard_scripts)

        with gui.div(id="main-content", className="container-xxl " + className):
            yield current_workspace

        gui.html(templates.get_template("footer.html").render(**context))
        gui.html(templates.get_template("login_scripts.html").render(**context))


def anonymous_login_container(request: Request, context: dict):
    next_url = str(furl(request.url).set(origin=None))
    login_url = str(furl("/login/", query_params=dict(next=next_url)))

    with gui.tag("a", href=login_url, className="pe-2 d-none d-lg-block"):
        gui.html("Sign In")

    popover, content = gui.popover(interactive=True)

    with popover, gui.div(className="d-flex align-items-center"):
        gui.html(
            templates.get_template("google_one_tap_button.html").render(**context)
            + '<i class="ps-2 fa-regular fa-chevron-down d-lg-none"></i>'
        )

    with (
        content,
        gui.div(
            className="d-flex flex-column bg-white border border-dark rounded shadow mx-2 overflow-hidden",
            style=dict(minWidth="200px"),
        ),
    ):
        row_height = "2.2rem"

        with gui.tag(
            "a",
            href=login_url,
            className="text-decoration-none d-block bg-hover-light align-items-center px-3 my-1 py-1",
            style=dict(height=row_height),
        ):
            with gui.div(className="row align-items-center"):
                with gui.div(className="col-2 d-flex justify-content-center"):
                    gui.html('<i class="fa-regular fa-circle-user"></i>')
                with gui.div(className="col-10"):
                    gui.html("Sign In")

        gui.html('<hr class="my-1"/>')

        for url, label in settings.HEADER_LINKS:
            with gui.tag(
                "a",
                href=url,
                className="text-decoration-none d-block bg-hover-light align-items-center px-3 my-1 py-1",
                style=dict(height=row_height),
            ):
                col1, col2 = gui.columns(
                    [2, 10], responsive=False, className="row align-items-center"
                )
                if icon := settings.HEADER_ICONS.get(url):
                    with col1, gui.div(className="d-flex justify-content-center"):
                        gui.html(icon)
                with col2:
                    gui.html(label)


class TabData(typing.NamedTuple):
    title: str
    label: str
    route: typing.Callable


class RecipeTabs(TabData, Enum):
    run = TabData(
        title=f"{icons.run} <span class='d-none d-lg-inline'>Run</span>",
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
        title=f'<img width="20" height="20" style="margin-right: 4px;margin-top: -3px" src="{icons.integrations_img}" alt="Facebook, Whatsapp, Slack, Instagram Icons"> <span class="d-none d-lg-inline">Integrations</span>',
        label="Integrations",
        route=integrations_route,
    )
    saved = TabData(
        title=f"{icons.save} Saved",
        label="Saved Runs",
        route=save_route,
    )

    def url_path(
        self, page_slug: str, run_slug: str = None, example_id: str = None, **kwargs
    ) -> str:
        kwargs["page_slug"] = page_slug
        if example_id:
            kwargs["example_id"] = example_id
            kwargs["run_slug"] = run_slug or "untitled"
        return get_route_path(self.route, kwargs)
