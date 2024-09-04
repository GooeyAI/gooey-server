from fastapi import APIRouter


class CustomAPIRouter(APIRouter):
    def add_api_route(self, path: str, *args, **kwargs) -> None:
        super().add_api_route(path, *args, **kwargs)
        if path.endswith("/"):
            path = path[:-1]
        else:
            path += "/"
        kwargs["include_in_schema"] = False
        kwargs.pop("name", None)
        kwargs.pop("tags", None)
        super().add_api_route(path, *args, **kwargs)
