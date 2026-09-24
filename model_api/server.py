__import__("gooeysite.wsgi")  # Note: this must always be at the top

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.requests import Request

from model_api import chat_completions
from model_api.chat_completions import error_response

app = FastAPI(
    title="Gooey.AI Model API", docs_url=None, redoc_url=None, openapi_url=None
)
app.include_router(chat_completions.router)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    message = exc.detail
    if isinstance(message, dict):
        # APIAuth errors carry {"error": msg}
        message = message.get("error", message)
    return error_response(exc.status_code, str(message))


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return error_response(400, str(exc.errors()))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "model_api.server:app", port=8090, reload=True, reload_dirs=["model_api"]
    )
