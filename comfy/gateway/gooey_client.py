"""Server-to-server client for gooey-server's internal comfy API."""

import httpx

from gateway import settings


class InsufficientCredits(Exception):
    pass


class GooeyAuthError(Exception):
    pass


_client = httpx.AsyncClient(
    base_url=settings.GOOEY_API_BASE_URL,
    headers={"Authorization": f"Bearer {settings.COMFY_SERVICE_TOKEN}"},
    timeout=30,
)


async def verify_sso(token: str) -> dict:
    r = await _client.post("/__/comfy/api/verify-sso/", json={"token": token})
    if r.status_code == 401:
        raise GooeyAuthError(_error_msg(r))
    r.raise_for_status()
    return r.json()


async def get_user(uid: str) -> dict:
    r = await _client.get(f"/__/comfy/api/users/{uid}/")
    if r.status_code == 401:
        raise GooeyAuthError(_error_msg(r))
    r.raise_for_status()
    return r.json()


async def record_usage(
    *, uid: str, workspace_id: int, gpu_ms: int, invoice_id: str, note: str = ""
) -> dict:
    r = await _client.post(
        "/__/comfy/api/usage/",
        json={
            "uid": uid,
            "workspace_id": workspace_id,
            "gpu_ms": gpu_ms,
            "invoice_id": invoice_id,
            "note": note,
        },
    )
    if r.status_code == 402:
        raise InsufficientCredits(_error_msg(r))
    if r.status_code == 401:
        raise GooeyAuthError(_error_msg(r))
    r.raise_for_status()
    return r.json()


async def get_balance(*, uid: str, workspace_id: int) -> int:
    r = await _client.get(
        f"/__/comfy/api/workspaces/{workspace_id}/balance/", params={"uid": uid}
    )
    if r.status_code == 401:
        raise GooeyAuthError(_error_msg(r))
    r.raise_for_status()
    return r.json()["balance"]


def _error_msg(r: httpx.Response) -> str:
    try:
        return r.json()["detail"]["error"]
    except Exception:
        return r.text
