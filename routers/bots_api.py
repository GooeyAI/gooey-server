import queue
import threading
import uuid
from threading import Thread

import hashids
from fastapi import APIRouter, HTTPException
from furl import furl
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse, Response

from bots.models import Platform, Conversation, BotIntegration, Message
from celeryapp.tasks import err_msg_for_exc
from daras_ai_v2 import settings
from daras_ai_v2.base import RecipeRunState, BasePage, StateKeys
from daras_ai_v2.bots import BotInterface, msg_handler, ButtonPressed
from daras_ai_v2.redis_cache import get_redis_cache
from recipes.VideoBots import VideoBotsPage, ReplyButton
from routers.api import (
    AsyncApiResponseModelV3,
    build_api_response,
    AsyncStatusResponseModelV3,
)

app = APIRouter()

api_hashids = hashids.Hashids(salt=settings.HASHIDS_API_SALT)
MSG_ID_PREFIX = "web-"


class CreateStreamRequest(BaseModel):
    integration_id: str = Field(
        description="Your Integration ID as shown in the Copilot Integrations tab"
    )

    input_text: str = None
    input_audio: str = None
    input_images: list[str] = None
    input_documents: list[str] = None

    button_pressed: ButtonPressed = Field(
        default=None,
        description="The button that was pressed by the user.",
    )

    conversation_id: str = Field(
        default=None,
        description="The gooey conversation ID.\n\n"
        "If not provided, a new conversation will be started and a new ID will be returned in the response. "
        "Use this to maintain the state of the conversation between requests.\n\n"
        "Note that you may not provide a custom ID here, and must only use the `conversation_id` returned in a previous response.",
    )
    user_id: str = Field(
        default=None,
        description="Your app's custom user ID.\n\n"
        "If not provided, a random user will be created and a new ID will be returned in the response. "
        "If a `conversation_id` is provided, this field is automatically set to the user's id associated with that conversation.",
    )

    user_message_id: str = Field(
        default=None,
        description="Your app's custom message ID for the user message.\n\n"
        "If not provided, a random ID will be generated and returned in the response. "
        "This is useful for tracking messages in the conversation.",
    )


class CreateStreamResponse(BaseModel):
    stream_url: str = Field(
        description="The URL to stream the conversation. Use Server-Sent Events (SSE) to stream the response."
    )


@app.post(
    "/v3/integrations/stream/",
    response_model=CreateStreamResponse,
    responses={402: {}},
    operation_id=VideoBotsPage.slug_versions[0] + "__stream_create",
    tags=["Copilot Integrations"],
    name="Copilot Integrations Create Stream",
)
@app.post(
    "/v3/integrations/stream/",
    response_model=CreateStreamResponse,
    responses={402: {}},
    include_in_schema=False,
)
def stream_create(request: CreateStreamRequest, response: Response):
    request_id = str(uuid.uuid4())
    get_redis_cache().set(f"gooey/stream-init/v1/{request_id}", request.json(), ex=600)
    stream_url = str(
        furl(settings.API_BASE_URL)
        / app.url_path_for(stream_response.__name__, request_id=request_id)
    )
    response.headers["Location"] = stream_url
    response.headers["Access-Control-Expose-Headers"] = "Location"
    return CreateStreamResponse(stream_url=stream_url)


class ConversationStart(BaseModel):
    type = Field(
        "conversation_start",
        description="The conversation was started. Save the IDs for future requests.",
    )

    conversation_id: str = Field(
        description="The conversation ID you provided in the request, or a random ID if not provided"
    )
    user_id: str = Field(description="The user ID associated with this conversation")

    user_message_id: str = Field(
        description="The user message ID you provided in the request, or a random ID if not provided."
    )
    bot_message_id: str = Field(
        description="The bot message ID. Use this ID as the `context_msg_id` when sending a `button_pressed`."
    )

    created_at: str = Field(
        description="Time when the conversation was created as ISO format"
    )


class RunStart(AsyncApiResponseModelV3):
    type = Field(
        "run_start",
        description="The run was started. Save the IDs for future requests."
        "Use the `status_url` to check the status of the run and fetch the complete output.",
    )


class MessagePart(BaseModel):
    type = Field(
        "message_part",
        description="The partial outputs from the bot will be streamed in parts. Use this to update the user interface iteratively.",
    )
    status: RecipeRunState = Field(description="Status of the run")
    detail: str = Field(
        description="Details about the status of the run as a human readable string"
    )

    text: str | None
    audio: str | None
    video: str | None
    buttons: list[ReplyButton] | None
    documents: list[str] | None


class FinalResponse(AsyncStatusResponseModelV3[VideoBotsPage.ResponseModel]):
    type = Field(
        "final_response",
        description="The run has completed. Use the `status_url` to check the status of the run and fetch the complete output.",
    )


class StreamError(BaseModel):
    type = Field(
        "error",
        description="An error occurred. The stream has ended.",
    )
    detail: str = Field(description="Details about the error")


StreamEvent = ConversationStart | RunStart | MessagePart | FinalResponse | StreamError


@app.get(
    "/v3/integrations/stream/{request_id}/",
    response_model=StreamEvent,
    responses={402: {}},
    operation_id=VideoBotsPage.slug_versions[0] + "__stream",
    tags=["Copilot Integrations"],
    name="Copilot integrations Stream Response",
)
@app.get(
    "/v3/integrations/stream/{request_id}",
    response_model=StreamEvent,
    responses={402: {}},
    include_in_schema=False,
)
def stream_response(request_id: str):
    r = get_redis_cache().getdel(f"gooey/stream-init/v1/{request_id}")
    if not r:
        return Response(
            status_code=404,
            content="Stream not found. You may have already accessed this stream once.",
        )
    request = CreateStreamRequest.parse_raw(r)
    api = ApiInterface(request)
    thread = Thread(target=api.runner)
    thread.start()
    return StreamingResponse(
        iterqueue(api.queue, thread), media_type="text/event-stream"
    )


def iterqueue(api_queue: queue.Queue, thread: threading.Thread):
    while True:
        if not thread.is_alive():
            return
        try:
            event: StreamEvent | None = api_queue.get(timeout=30)
        except queue.Empty:
            continue
        if not event:
            return
        if isinstance(event, StreamError):
            yield b"event: error\n"
        yield b"data: " + event.json(exclude_none=True).encode() + b"\n\n"


class ApiInterface(BotInterface):
    platform = Platform.WEB

    run_id: str = None
    uid: str = None

    def __init__(self, request: CreateStreamRequest):
        self.request = request
        try:
            self.bot_id = api_hashids.decode(request.integration_id)[0]
            assert BotIntegration.objects.filter(id=self.bot_id).exists()
        except (IndexError, AssertionError):
            raise HTTPException(
                status_code=404,
                detail=f"Bot Integration with id={request.integration_id} not found",
            )

        if request.conversation_id:
            try:
                self.convo = Conversation.objects.get(
                    id=api_hashids.decode(request.conversation_id)[0]
                )
            except (IndexError, Conversation.DoesNotExist):
                raise HTTPException(
                    status_code=404,
                    detail=f"Conversation with id={request.conversation_id} not found",
                )
            else:
                if self.convo.bot_integration_id != self.bot_id:
                    raise HTTPException(
                        status_code=400,
                        detail="Bot Integration mismatch. The provided integration ID does not match the integration ID associated with this conversation.",
                    )
                if request.user_id and request.user_id != self.convo.web_user_id:
                    raise HTTPException(
                        status_code=400,
                        detail="User ID mismatch. The provided user ID does not match the user ID associated with this conversation.",
                    )
        else:
            self.convo = Conversation.objects.create(
                bot_integration_id=self.bot_id,
                web_user_id=request.user_id or str(uuid.uuid4()),
            )

        if (
            request.user_message_id
            and Message.objects.filter(
                platform_msg_id=MSG_ID_PREFIX + request.user_message_id,
                conversation=self.convo,
            ).exists()
        ):
            raise HTTPException(
                status_code=400,
                detail=f"Message with id={request.user_message_id} already exists",
            )

        self.user_id = request.user_id or self.convo.web_user_id
        self.user_msg_id = MSG_ID_PREFIX + (
            request.user_message_id or str(uuid.uuid4())
        )
        self.bot_message_id = MSG_ID_PREFIX + str(uuid.uuid4())

        self.queue = queue.Queue()

        self.queue.put(
            ConversationStart(
                conversation_id=api_hashids.encode(self.convo.id),
                user_id=self.convo.web_user_id,
                user_message_id=self.user_msg_id.lstrip(MSG_ID_PREFIX),
                bot_message_id=self.bot_message_id.lstrip(MSG_ID_PREFIX),
                created_at=self.convo.created_at.isoformat(),
            )
        )

        if request.input_text:
            self.input_type = "text"
        elif request.input_audio:
            self.input_type = "audio"
        elif request.input_images:
            self.input_type = "image"
        elif request.input_documents:
            self.input_type = "document"
        elif request.button_pressed:
            self.input_type = "interactive"
        else:
            raise HTTPException(
                status_code=400, detail="No input provided. Please provide input."
            )

        self._unpack_bot_integration()

    def runner(self):
        try:
            msg_handler(self)
            # raise ValueError("Stream ended")
            if self.run_id and self.uid:
                sr = self.page_cls.run_doc_sr(run_id=self.run_id, uid=self.uid)
                state = sr.to_dict()
                self.queue.put(
                    FinalResponse(
                        run_id=self.run_id,
                        web_url=sr.get_app_url(),
                        created_at=sr.created_at.isoformat(),
                        run_time_sec=sr.run_time.total_seconds(),
                        status=self.page_cls.get_run_state(state),
                        detail=state.get(StateKeys.run_status) or "",
                        output=VideoBotsPage.ResponseModel.parse_obj(state),
                    )
                )
        except Exception as e:
            self.queue.put(StreamError(detail=err_msg_for_exc(e)))
        finally:
            self.queue.put(None)

    def on_run_created(
        self, page: BasePage, result: "celery.result.AsyncResult", run_id: str, uid: str
    ):
        self.run_id = run_id
        self.uid = uid
        self.queue.put(
            RunStart(
                **build_api_response(
                    page=page, result=result, run_async=True, run_id=run_id, uid=uid
                ),
            )
        )

    def send_run_status(self, update_msg_id: str | None) -> str | None:
        self.queue.put(
            MessagePart(status=self.recipe_run_state, detail=self.run_status)
        )
        return None

    def send_msg(
        self,
        *,
        text: str | None = None,
        audio: str = None,
        video: str = None,
        buttons: list[ReplyButton] = None,
        documents: list[str] = None,
        should_translate: bool = False,
        update_msg_id: str = None,
    ) -> str | None:
        response = MessagePart(
            status=self.recipe_run_state,
            detail=self.run_status,
            text=text,
            audio=audio,
            video=video,
            buttons=buttons,
            documents=documents,
        )
        self.queue.put(response)
        return self.bot_message_id

    def mark_read(self):
        pass

    def get_input_text(self) -> str | None:
        return self.request.input_text

    def get_input_audio(self) -> str | None:
        return self.request.input_audio

    def get_input_images(self) -> list[str] | None:
        return self.request.input_images

    def get_input_documents(self) -> list[str] | None:
        return self.request.input_documents

    def get_interactive_msg_info(self) -> ButtonPressed | None:
        return self.request.button_pressed