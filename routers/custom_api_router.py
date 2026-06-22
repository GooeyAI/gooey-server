from fastapi import APIRouter
from starlette._utils import is_async_callable

from gooeysite.bg_db_conn import db_middleware


class CustomAPIRouter(APIRouter):
    def add_api_route(self, path: str, endpoint, **kwargs) -> None:
        if not is_async_callable(endpoint):
            endpoint = db_middleware(endpoint)
        super().add_api_route(path, endpoint, **kwargs)
        if path.endswith("/"):
            alt_path = path[:-1]
        else:
            alt_path = path + "/"
        kwargs["include_in_schema"] = False
        kwargs.pop("name", None)
        kwargs.pop("tags", None)
        super().add_api_route(alt_path, endpoint, **kwargs)
