import os.path

import requests
from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import (
    HTMLResponse,
    RedirectResponse,
    Response,
)
from starlette.status import HTTP_308_PERMANENT_REDIRECT

from app_users.models import AppUser
from daras_ai_v2 import settings
from routers.custom_api_router import CustomAPIRouter

app = CustomAPIRouter()


# Static pages must include this comment in their <head>. serve_static_file swaps
# it for a <base> tag pointing at the cdn so relative asset urls don't proxy back
# through here. See static/sovereign/index.html for an example.
BASE_HREF_PLACEHOLDER = "<!-- GOOEY-BASE-HREF -->"


def serve_static_file(request: Request) -> Response | None:
    """Proxy unmatched urls to the `gooey-static-pages` Cloudflare Pages site.

    Pages without a file extension (e.g. `/sovereign`) are fetched as html and
    returned inline so the gooey.ai url stays in the address bar. Anything with a
    file extension is redirected straight to the Cloudflare Pages cdn -- the proxied
    html points its own assets there via an injected `<base>` tag, so this is only a
    fallback for stray asset requests and avoids proxying large files.
    """
    if not settings.CLOUDFLARE_PAGES_URL:
        raise HTTPException(status_code=404)

    relpath = request.url.path.strip("/") or "index"
    cdn_url = os.path.join(settings.CLOUDFLARE_PAGES_URL, relpath)

    # assets are served straight from the cdn
    if os.path.splitext(relpath)[1]:
        return RedirectResponse(cdn_url, status_code=HTTP_308_PERMANENT_REDIRECT)

    # html pages are proxied so the gooey.ai url is preserved
    r = requests.get(cdn_url, headers={"Cache-Control": "no-cache"})
    if not r.ok:
        raise HTTPException(status_code=404)
    return HTMLResponse(
        inject_dynamic_html(request.user, r.text, r.url), status_code=r.status_code
    )


def inject_dynamic_html(user: AppUser | None, html: str, base_href: str) -> str:
    # Swap the `BASE_HREF_PLACEHOLDER` comment for a `<base>` tag.

    # `base_href` is the final (post-redirect) cdn url of the page, e.g.
    # `https://gooey-static-pages.pages.dev/sovereign/`. Without this, the page's
    # relative asset urls would resolve against gooey.ai and round-trip back through
    # this proxy.
    html = html.replace(BASE_HREF_PLACEHOLDER, f'<base href="{base_href}" />', 1)

    # replace login button with user's name if logged in
    if user and not user.is_anonymous:
        html = html.replace(
            ">Login<",
            f">Hi, {user.first_name() or user.email or user.phone_number or 'Anon'}<",
            1,
        )

    return html
