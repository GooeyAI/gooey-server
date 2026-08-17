"""
The comfy.gooey.ai gateway.

Run locally:

```bash
cd comfy
pip install -r requirements.txt
COMFY_BACKEND=static STATIC_COMFY_URL=http://localhost:8188 \\
    SECRET_KEY=dev COMFY_SERVICE_TOKEN=dev \\
    GOOEY_APP_BASE_URL=http://localhost:3000 \\
    GOOEY_API_BASE_URL=http://localhost:8080 \\
    uvicorn gateway.main:app --port 8501 --reload
```
"""

import html
import logging
from contextlib import asynccontextmanager
from urllib.parse import quote

from fastapi import FastAPI, Request, WebSocket
from pydantic import BaseModel
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from gateway import backends, gooey_client, header, proxy, sessions, settings

logging.basicConfig(level=logging.INFO)

backend = backends.make_backend()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await backend.shutdown()


app = FastAPI(title="Gooey ComfyUI Gateway", docs_url=None, redoc_url=None, lifespan=lifespan)


def sso_redirect(next_path: str = "/") -> RedirectResponse:
    return RedirectResponse(
        f"{settings.GOOEY_APP_BASE_URL}/comfy/sso/?next={quote(next_path)}"
    )


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/login")
async def login(request: Request):
    return sso_redirect(request.query_params.get("next") or "/")


@app.get("/auth/callback")
async def auth_callback(token: str, next: str = "/"):
    try:
        user_info = await gooey_client.verify_sso(token)
    except gooey_client.GooeyAuthError as e:
        return _error_page("Login failed", str(e), status_code=401)
    if not next.startswith("/") or next.startswith("//"):
        next = "/"
    response = RedirectResponse(next)
    sessions.set_session(response, sessions.session_from_user_info(user_info))
    return response


@app.get("/gooey/logout")
async def logout():
    response = RedirectResponse(settings.GOOEY_APP_BASE_URL)
    sessions.clear_session(response)
    return response


@app.get("/gooey/api/me")
async def me(request: Request):
    session = sessions.get_session(request)
    if not session:
        return JSONResponse({"error": "not logged in"}, status_code=401)
    try:
        user_info = await gooey_client.get_user(session["uid"])
    except gooey_client.GooeyAuthError as e:
        response = JSONResponse({"error": str(e)}, status_code=401)
        sessions.clear_session(response)
        return response
    session = sessions.session_from_user_info(
        user_info, session["selected_workspace_id"]
    )
    response = JSONResponse(dict(session))
    sessions.set_session(response, session)
    return response


class SwitchWorkspaceRequest(BaseModel):
    workspace_id: int


@app.post("/gooey/switch-workspace")
async def switch_workspace(request: Request, payload: SwitchWorkspaceRequest):
    session = sessions.get_session(request)
    if not session:
        return JSONResponse({"error": "not logged in"}, status_code=401)
    if payload.workspace_id not in [w["id"] for w in session["workspaces"]]:
        return JSONResponse({"error": "not a member of this workspace"}, 403)
    session["selected_workspace_id"] = payload.workspace_id
    response = JSONResponse({"ok": True})
    sessions.set_session(response, session)
    return response


@app.websocket("/ws")
async def websocket_proxy(ws: WebSocket):
    session = sessions.get_session(ws)
    if not session:
        await ws.close(code=4401)
        return
    instance = backend.get(session["selected_workspace_id"])
    if not instance or not instance.ready:
        await ws.close(code=4404)
        return
    instance.touch()
    await proxy.proxy_websocket(ws, instance.url)


@app.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
)
async def comfy_proxy(request: Request, path: str):
    session = sessions.get_session(request)
    if not session:
        if request.method == "GET" and _is_navigation(request):
            return sso_redirect("/" + path)
        return JSONResponse({"error": "not logged in"}, status_code=401)

    workspace_id = session["selected_workspace_id"]
    try:
        instance = await backend.get_or_launch(workspace_id, session["uid"])
    except gooey_client.InsufficientCredits as e:
        return _error_page(
            "Insufficient credits",
            f"{html.escape(str(e))} <br/><br/>"
            f"<a style='color:#fff' href='{settings.GOOEY_APP_BASE_URL}/account/'>"
            "Add credits on Gooey.AI</a>",
            status_code=402,
            escape=False,
        )
    except gooey_client.GooeyAuthError as e:
        response = _error_page("Session expired", str(e), status_code=401)
        sessions.clear_session(response)
        return response

    if not instance.ready:
        return _starting_page()

    instance.touch()
    inject = None
    if request.method == "GET" and _is_navigation(request):
        inject = header.render_snippet(session)
    return await proxy.proxy_http(request, instance.url, inject_html=inject)


def _is_navigation(request: Request) -> bool:
    return "text/html" in request.headers.get("accept", "")


def _starting_page() -> HTMLResponse:
    return HTMLResponse(
        """
        <html><head><meta http-equiv="refresh" content="3">
        <title>Starting ComfyUI — Gooey.AI</title></head>
        <body style="font-family:sans-serif;background:#02023e;color:#fff;
                     display:flex;align-items:center;justify-content:center;
                     height:100vh;margin:0;text-align:center">
          <div>
            <img src="{logo}" style="height:40px"/><br/><br/>
            <h2>Starting your ComfyUI workspace &hellip;</h2>
            <p>Provisioning a GPU &mdash; this usually takes under a minute.<br/>
               This page refreshes automatically.</p>
          </div>
        </body></html>
        """.format(logo=settings.GOOEY_LOGO_IMG_WHITE),
        status_code=503,
    )


def _error_page(
    title: str, message: str, status_code: int, escape: bool = True
) -> HTMLResponse:
    if escape:
        message = html.escape(message)
    return HTMLResponse(
        f"""
        <html><head><title>{html.escape(title)} — Gooey.AI</title></head>
        <body style="font-family:sans-serif;background:#02023e;color:#fff;
                     display:flex;align-items:center;justify-content:center;
                     height:100vh;margin:0;text-align:center">
          <div>
            <h2>{html.escape(title)}</h2>
            <p>{message}</p>
            <p><a style="color:#fff" href="/">Try again</a></p>
          </div>
        </body></html>
        """,
        status_code=status_code,
    )
