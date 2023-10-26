import datetime
import os.path
import subprocess
import tempfile
import typing
from time import time

from fastapi import Depends
from fastapi import HTTPException
from fastapi.responses import RedirectResponse
from fastapi.routing import APIRouter
from firebase_admin import auth, exceptions
from furl import furl
from starlette.datastructures import FormData
from starlette.requests import Request
from starlette.responses import (
    PlainTextResponse,
    Response,
    FileResponse,
)

import gooey_ui as st
from app_users.models import AppUser
from daras_ai.image_input import upload_file_from_bytes, safe_filename
from daras_ai_v2 import settings
from daras_ai_v2.all_pages import all_api_pages, normalize_slug, page_slug_map
from daras_ai_v2.asr import FFMPEG_WAV_ARGS, check_wav_audio_format
from daras_ai_v2.base import (
    RedirectException,
)
from daras_ai_v2.copy_to_clipboard_button_widget import copy_to_clipboard_scripts
from daras_ai_v2.db import FIREBASE_SESSION_COOKIE
from daras_ai_v2.meta_content import build_meta_tags, raw_build_meta_tags
from daras_ai_v2.query_params_util import extract_query_params
from daras_ai_v2.settings import templates
from routers.api import request_form_files

app = APIRouter()

DEFAULT_LOGIN_REDIRECT = "/explore/"
DEFAULT_LOGOUT_REDIRECT = "/"


@app.get("/sitemap.xml/")
async def get_sitemap():
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


@app.post("/__/file-upload/")
def file_upload(request: Request, form_data: FormData = Depends(request_form_files)):
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
            if not check_wav_audio_format(infile.name):
                with tempfile.NamedTemporaryFile(suffix=".wav") as outfile:
                    args = [
                        "ffmpeg",
                        "-y",
                        "-i",
                        infile.name,
                        *FFMPEG_WAV_ARGS,
                        outfile.name,
                    ]
                    print("\t$ " + " ".join(args))
                    subprocess.check_call(args)

                    filename += ".wav"
                    content_type = "audio/wav"
                    data = outfile.read()

    if content_type.startswith("image/"):
        with Image(blob=data) as img:
            if img.format not in ["png", "jpeg", "jpg", "gif"]:
                img.format = "png"
                content_type = "image/png"
                filename += ".png"
            img.transform(resize=form_data.get("resize", f"{1024**2}@>"))
            data = img.make_blob()

    return {"url": upload_file_from_bytes(filename, data, content_type)}


async def request_json(request: Request):
    return await request.json()


@app.post("/explore/")
def explore_page(request: Request, json_data: dict = Depends(request_json)):
    import explore

    ret = st.runner(
        lambda: page_wrapper(request=request, render_fn=explore.render),
        **json_data,
    )
    ret |= {
        "meta": raw_build_meta_tags(
            url=get_og_url_path(request),
            title=explore.META_TITLE,
            description=explore.META_DESCRIPTION,
        ),
    }
    return ret


@app.post("/")
@app.post("/{page_slug}/")
@app.post("/{page_slug}/{tab}/")
def st_page(
    request: Request,
    page_slug="",
    tab="",
    json_data: dict = Depends(request_json),
):
    try:
        page_cls = page_slug_map[normalize_slug(page_slug)]
    except KeyError:
        raise HTTPException(status_code=404)
    # ensure the latest slug is used
    latest_slug = page_cls.slug_versions[-1]
    if latest_slug != page_slug:
        return RedirectResponse(
            request.url.replace(path=os.path.join("/", latest_slug, tab, ""))
        )

    example_id, run_id, uid = extract_query_params(request.query_params)

    page = page_cls(tab=tab, request=request, run_user=get_run_user(request, uid))

    state = json_data.setdefault("state", {})
    if not state:
        db_state = page.get_sr_from_query_params(example_id, run_id, uid).to_dict()
        if db_state is not None:
            state.update(db_state)
            for k, v in page.sane_defaults.items():
                state.setdefault(k, v)
    if state is None:
        raise HTTPException(status_code=404)

    try:
        ret = st.runner(
            lambda: page_wrapper(request, page.render),
            query_params=dict(request.query_params),
            **json_data,
        )
    except RedirectException as e:
        return RedirectResponse(e.url, status_code=e.status_code)

    # Canonical URLs should not include uid or run_id (don't index specific runs).
    # In the case of examples, all tabs other than "Run" are duplicates of the page
    # without the `example_id`, and so their canonical shouldn't include `example_id`
    canonical_url = str(
        furl(
            str(settings.APP_BASE_URL),
            query_params={"example_id": example_id} if not tab and example_id else {},
        )
        / latest_slug
        / tab
        / "/"  # preserve trailing slash
    )

    ret |= {
        "meta": build_meta_tags(
            url=get_og_url_path(request),
            page=page,
            state=state,
            run_id=run_id,
            uid=uid,
            example_id=example_id,
        )
        + [dict(tagName="link", rel="canonical", href=canonical_url)]
        # + [
        #     dict(tagName="link", rel="icon", href="/static/favicon.ico"),
        #     dict(tagName="link", rel="stylesheet", href="/static/css/app.css"),
        # ],
    }
    return ret


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


def page_wrapper(request: Request, render_fn: typing.Callable, **kwargs):
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
        render_fn(**kwargs)

    st.html(templates.get_template("footer.html").render(**context))
    st.html(templates.get_template("login_scripts.html").render(**context))
