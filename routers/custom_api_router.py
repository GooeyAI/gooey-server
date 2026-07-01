import fastapi
from fastapi.routing import APIRoute
from starlette._utils import is_async_callable

from gooeysite.bg_db_conn import db_middleware


class CustomAPIRoute(APIRoute):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        dependant = self.dependant
        if is_async_callable(dependant.call):
            return
        dependant.call = db_middleware(dependant.call)


class CustomAPIRouter(fastapi.APIRouter):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("route_class", CustomAPIRoute)
        super().__init__(*args, **kwargs)

    def add_api_route(self, path: str, endpoint, **kwargs) -> None:
        super().add_api_route(path, endpoint, **kwargs)
        if path.endswith("/"):
            alt_path = path[:-1]
        else:
            alt_path = path + "/"
        kwargs["include_in_schema"] = False
        kwargs.pop("name", None)
        kwargs.pop("tags", None)
        super().add_api_route(alt_path, endpoint, **kwargs)
