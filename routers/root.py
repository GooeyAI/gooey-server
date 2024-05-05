import datetime
import os
import tempfile
import typing
from contextlib import contextmanager
from enum import Enum
from time import time

from fastapi import Depends
from fastapi import HTTPException
from fastapi.responses import RedirectResponse
from fastapi.routing import APIRouter
from firebase_admin import auth, exceptions
from furl import furl
from loguru import logger
from starlette.datastructures import FormData
from starlette.requests import Request
from starlette.responses import (
    PlainTextResponse,
    Response,
    FileResponse,
)

import gooey_ui as st
from app_users.models import AppUser
from bots.models import Workflow, BotIntegration
from daras_ai.image_input import upload_file_from_bytes, safe_filename
from daras_ai_v2 import settings, icons
from daras_ai_v2.api_examples_widget import api_example_generator
from daras_ai_v2.asr import FFMPEG_WAV_ARGS, check_wav_audio_format
from daras_ai_v2.copy_to_clipboard_button_widget import copy_to_clipboard_scripts
from daras_ai_v2.db import FIREBASE_SESSION_COOKIE
from daras_ai_v2.exceptions import ffmpeg, UserError
from daras_ai_v2.fastapi_tricks import (
    fastapi_request_json,
    fastapi_request_form,
)
from daras_ai_v2.manage_api_keys_widget import manage_api_keys
from daras_ai_v2.meta_content import build_meta_tags, raw_build_meta_tags
from daras_ai_v2.meta_preview_url import meta_preview_url
from daras_ai_v2.profiles import user_profile_page, get_meta_tags_for_profile
from daras_ai_v2.query_params_util import extract_query_params
from daras_ai_v2.settings import templates
from gooey_ui import RedirectException
from gooey_ui.components.url_button import url_button
from handles.models import Handle

app = APIRouter()

DEFAULT_LOGIN_REDIRECT = "/explore/"
DEFAULT_LOGOUT_REDIRECT = "/"


@app.get("/sitemap.xml/")
async def get_sitemap():
    from daras_ai_v2.all_pages import all_api_pages

    my_sitemap = """<?xml version="1.0" encoding="UTF-8"?>
                <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">"""

    all_paths = ["/", "/faq", "/pricing", "/privacy", "/terms", "/team/"] + [
        page.slug_versions[-1] for page in all_api_pages
    ]

    for path in all_paths:
        url = furl(settings.APP_BASE_URL) / path
        my_sitemap += f"""<url>
              <loc>{url}</loc>
              <lastmod>2022-12-26</lastmod>
              <changefreq>daily</changefreq>
              <priority>1.0</priority>
          </url>"""

    my_sitemap += """</urlset>"""

    return Response(content=my_sitemap, media_type="application/xml")


@app.get("/favicon")
@app.get("/favicon/")
@app.get("/favicon.ico")
@app.get("/favicon.ico/")
async def favicon():
    return FileResponse("static/favicon.ico")


@app.post("/handleError/")
@st.route
def handle_error(request: Request, json_data: dict):
    context = {"request": request, "settings": settings}
    match json_data["status"]:
        case 404:
            template = "errors/404.html"
        case _:
            template = "errors/unknown.html"
    with page_wrapper(request):
        st.html(templates.get_template(template).render(**context))


@app.get("/login/")
def login(request: Request):
    if request.user and not request.user.is_anonymous:
        return RedirectResponse(
            request.query_params.get("next", DEFAULT_LOGIN_REDIRECT)
        )
    context = {
        "request": request,
        "settings": settings,
    }
    if request.user and request.user.is_anonymous:
        context["anonymous_user_token"] = auth.create_custom_token(
            request.user.uid
        ).decode()
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
                    existing_user.save()
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
async def file_upload(body_json: dict = fastapi_request_json):
    return dict(name=body_json["url"], type="url/undefined")


@app.post("/__/file-upload/")
def file_upload(form_data: FormData = fastapi_request_form):
    from wand.image import Image

    file = form_data["file"]
    data = file.file.read()
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

    return {"url": upload_file_from_bytes(filename, data, content_type)}


@app.post("/explore/")
@st.route
def explore_page(request: Request):
    import explore

    with page_wrapper(request):
        explore.render()

    return {
        "meta": raw_build_meta_tags(
            url=get_og_url_path(request),
            title=explore.META_TITLE,
            description=explore.META_DESCRIPTION,
        ),
    }


@app.post("/api/")
@st.route
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
            ),
        )
    )


def _api_docs_page(request):
    from daras_ai_v2.all_pages import all_api_pages

    api_docs_url = str(furl(settings.API_BASE_URL) / "docs")

    st.markdown(
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

    st.write("---")
    options = {
        page_cls.workflow.value: page_cls().get_recipe_title()
        for page_cls in all_api_pages
    }

    st.write(
        "##### ⚕ API Generator\nChoose a workflow to see how you can interact with it via the API"
    )

    col1, col2 = st.columns([11, 1], responsive=False)
    with col1:
        with st.div(className="pt-1"):
            workflow = Workflow(
                st.selectbox(
                    "",
                    options=options,
                    format_func=lambda x: options[x],
                )
            )
    with col2:
        url_button(workflow.page_cls.app_url())

    st.write("###### 📤 Example Request")

    include_all = st.checkbox("Show all fields")
    as_async = st.checkbox("Run Async")
    as_form_data = st.checkbox("Upload Files via Form Data")

    page = workflow.page_cls(request=request)
    state = page.get_root_published_run().saved_run.to_dict()
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
    st.write("")

    st.write("###### 🎁 Example Response")
    st.json(response_body, expanded=True)

    st.write("---")
    with st.tag("a", id="api-keys"):
        st.write("##### 🔐 API keys")

    if not page.request.user or page.request.user.is_anonymous:
        st.write(
            "**Please [Login](/login/?next=/api/) to generate the `$GOOEY_API_KEY`**"
        )
        return

    manage_api_keys(page.request.user)


@app.post("/{page_slug}/examples/")
@app.post("/{page_slug}/{run_slug}/examples/")
@app.post("/{page_slug}/{run_slug}-{example_id}/examples/")
@st.route
def examples_route(
    request: Request, page_slug: str, run_slug: str = None, example_id: str = None
):
    return render_page(request, page_slug, run_slug, RecipeTabs.examples, example_id)


@app.post("/{page_slug}/api/")
@app.post("/{page_slug}/{run_slug}/api/")
@app.post("/{page_slug}/{run_slug}-{example_id}/api/")
@st.route
def api_route(
    request: Request, page_slug: str, run_slug: str = None, example_id: str = None
):
    return render_page(request, page_slug, run_slug, RecipeTabs.run_as_api, example_id)


@app.post("/{page_slug}/history/")
@app.post("/{page_slug}/{run_slug}/history/")
@app.post("/{page_slug}/{run_slug}-{example_id}/history/")
@st.route
def history_route(
    request: Request, page_slug: str, run_slug: str = None, example_id: str = None
):
    return render_page(request, page_slug, run_slug, RecipeTabs.history, example_id)


@app.post("/{page_slug}/saved/")
@app.post("/{page_slug}/{run_slug}/saved/")
@app.post("/{page_slug}/{run_slug}-{example_id}/saved/")
@st.route
def save_route(
    request: Request, page_slug: str, run_slug: str = None, example_id: str = None
):
    return render_page(request, page_slug, run_slug, RecipeTabs.saved, example_id)


@app.post("/{page_slug}/integrations/add/")
@app.post("/{page_slug}/{run_slug}/integrations/add/")
@app.post("/{page_slug}/{run_slug}-{example_id}/integrations/add/")
@st.route
def add_integrations_route(
    request: Request,
    page_slug: str,
    run_slug: str = None,
    example_id: str = None,
):
    st.session_state["--add-integration"] = True
    return render_page(
        request, page_slug, run_slug, RecipeTabs.integrations, example_id
    )


@app.post("/{page_slug}/integrations/{integration_id}/stats/")
@app.post("/{page_slug}/{run_slug}/integrations/{integration_id}/stats/")
@app.post("/{page_slug}/{run_slug}-{example_id}/integrations/{integration_id}/stats/")
@st.route
def integrations_stats_route(
    request: Request,
    page_slug: str,
    integration_id: str,
    run_slug: str = None,
    example_id: str = None,
):
    from routers.bots_api import api_hashids

    try:
        st.session_state.setdefault("bi_id", api_hashids.decode(integration_id)[0])
    except IndexError:
        raise HTTPException(status_code=404)
    return render_page(request, "stats", run_slug, RecipeTabs.integrations, example_id)


@app.post("/{page_slug}/integrations/{integration_id}/analysis/")
@app.post("/{page_slug}/{run_slug}/integrations/{integration_id}/analysis/")
@app.post(
    "/{page_slug}/{run_slug}-{example_id}/integrations/{integration_id}/analysis/"
)
@st.route
def integrations_analysis_route(
    request: Request,
    page_slug: str,
    integration_id: str,
    run_slug: str = None,
    example_id: str = None,
    graphs: str = None,
):
    from routers.bots_api import api_hashids
    from daras_ai_v2.analysis_results import render_analysis_results_page

    try:
        bi = BotIntegration.objects.get(id=api_hashids.decode(integration_id)[0])
    except (IndexError, BotIntegration.DoesNotExist):
        raise HTTPException(status_code=404)

    with page_wrapper(request):
        render_analysis_results_page(bi, graphs)

    return dict(
        meta=raw_build_meta_tags(
            url=get_og_url_path(request),
            title=f"Analysis for {bi.name}",
        ),
    )


@app.post("/{page_slug}/integrations/")
@app.post("/{page_slug}/{run_slug}/integrations/")
@app.post("/{page_slug}/{run_slug}-{example_id}/integrations/")
###
@app.post("/{page_slug}/integrations/{integration_id}/")
@app.post("/{page_slug}/{run_slug}/integrations/{integration_id}/")
@app.post("/{page_slug}/{run_slug}-{example_id}/integrations/{integration_id}/")
@st.route
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
            st.session_state.setdefault("bi_id", api_hashids.decode(integration_id)[0])
        except IndexError:
            raise HTTPException(status_code=404)
    return render_page(
        request, page_slug, run_slug, RecipeTabs.integrations, example_id
    )


@app.post("/{page_slug}/")
@app.post("/{page_slug}/{run_slug}/")
@app.post("/{page_slug}/{run_slug}-{example_id}/")
@st.route
def recipe_page_or_handle(
    request: Request, page_slug: str, run_slug: str = None, example_id: str = None
):
    try:
        handle = Handle.objects.get_by_name(page_slug)
    except Handle.DoesNotExist:
        return render_page(request, page_slug, run_slug, RecipeTabs.run, example_id)
    else:
        return render_page_for_handle(request, handle)


def render_page_for_handle(request: Request, handle: Handle):
    if handle.has_user:
        with page_wrapper(request):
            user_profile_page(request, handle.user)
        return dict(meta=get_meta_tags_for_profile(handle.user))
    elif handle.has_redirect:
        raise RedirectException(handle.redirect_url, status_code=301)
    else:
        logger.error(f"Handle {handle.name} has no user or redirect")
        raise HTTPException(status_code=404)


def render_page(
    request: Request,
    page_slug: str,
    run_slug: str | None,
    tab: "RecipeTabs",
    example_id: str | None,
):
    from daras_ai_v2.all_pages import normalize_slug, page_slug_map

    # lookup the page class
    try:
        page_cls = page_slug_map[normalize_slug(page_slug)]
    except KeyError:
        raise HTTPException(status_code=404)

    # ensure the latest slug is used
    latest_slug = page_cls.slug_versions[-1]
    if latest_slug != page_slug:
        return RedirectResponse(tab.url_path(latest_slug, run_slug))

    # parse the query params and load the state
    query_params = st.get_query_params()
    if not query_params.get("example_id"):
        query_params["example_id"] = example_id
    example_id, run_id, uid = extract_query_params(query_params)
    page = page_cls(tab=tab, request=request, run_user=get_run_user(request, uid))
    if not st.session_state:
        sr = page.get_sr_from_query_params(example_id, run_id, uid)
        st.session_state.update(page.load_state_from_sr(sr))

    with page_wrapper(request):
        page.render()

    return dict(
        meta=build_meta_tags(
            url=get_og_url_path(request),
            page=page,
            state=st.session_state,
            run_id=run_id,
            uid=uid,
            example_id=example_id,
        ),
    )


def get_og_url_path(request) -> str:
    return str(
        (furl(settings.APP_BASE_URL) / request.url.path).add(request.query_params)
    )


def get_run_user(request, uid) -> AppUser | None:
    if not uid:
        return
    if request.user and request.user.uid == uid:
        return request.user
    try:
        return AppUser.objects.get(uid=uid)
    except AppUser.DoesNotExist:
        pass


@contextmanager
def page_wrapper(request: Request):
    context = {
        "request": request,
        "settings": settings,
        "block_incognito": True,
    }
    if request.user and request.user.is_anonymous:
        context["anonymous_user_token"] = auth.create_custom_token(
            request.user.uid
        ).decode()

    st.html(templates.get_template("gtag.html").render(**context))
    st.html(templates.get_template("header.html").render(**context))
    st.html(copy_to_clipboard_scripts)

    with st.div(id="main-content", className="container"):
        yield

    st.html(templates.get_template("footer.html").render(**context))
    st.html(templates.get_template("login_scripts.html").render(**context))


INTEGRATION_IMG = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/c3ba2392-d6b9-11ee-a67b-6ace8d8c9501/image.png"


class TabData(typing.NamedTuple):
    title: str
    label: str
    route: typing.Callable


class RecipeTabs(TabData, Enum):
    run = TabData(
        title=f"{icons.run} Run",
        label="",
        route=recipe_page_or_handle,
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
        title=f'<img align="left" width="24" height="24" style="margin-right: 10px" src="{INTEGRATION_IMG}" alt="Facebook, Whatsapp, Slack, Instagram Icons"> Integrations',
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
        return os.path.join(app.url_path_for(self.route.__name__, **kwargs), "")
