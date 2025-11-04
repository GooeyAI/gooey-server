import json
import typing

from django.core.exceptions import ValidationError
from django.utils import timezone
from loguru import logger
from sentry_sdk import capture_exception
from twilio.base.exceptions import TwilioRestException
from twilio.twiml.voice_response import VoiceResponse

from bots.models import BotIntegration
from bots.models.bot_integration import validate_phonenumber
from functions.composio_tools import ComposioLLMTool
from functions.models import FunctionScopes
from functions.recipe_functions import (
    BaseLLMTool,
    generate_tool_properties,
    get_external_tool_slug_from_url,
)
from memory.models import MemoryEntry


def get_inbuilt_tools_from_state(state: dict) -> typing.Iterable[BaseLLMTool]:
    from composio import Composio

    from daras_ai_v2.language_model_openai_audio import is_realtime_audio_url

    audio_url = state.get("input_audio")
    if is_realtime_audio_url(audio_url):
        yield CallTransferLLMTool()

    variables = state.get("variables") or {}

    if variables.get("platform_medium") == "VOICE":
        yield VectorSearchLLMTool(state)

    update_gui_state_params = variables.get("update_gui_state_params")
    if update_gui_state_params:
        yield UpdateGuiStateLLMTool(
            state=update_gui_state_params.get("state"),
            page_slug=update_gui_state_params.get("page_slug"),
        )
        yield RunJS()

    collect_feedback = variables.get("collect_feedback")
    if collect_feedback:
        yield FeedbackCollectionLLMTool(
            platform_msg_id=collect_feedback.get("last_bot_message_id"),
            conversation_id=variables.get("conversation_id"),
        )

    functions = state.get("functions")
    if not functions:
        return

    composio_tools = {}
    for function in functions:
        url = function.get("url")
        if not url:
            continue
        tool_slug = get_external_tool_slug_from_url(url)
        if not tool_slug:
            continue
        scope = FunctionScopes.get(function.get("scope"))
        try:
            tool_cls = INBUILT_INTEGRATION_TOOLS[tool_slug]
            yield tool_cls(scope)
        except KeyError:
            composio_tools[tool_slug] = scope
    for tool_spec in Composio().tools.get_raw_composio_tools(
        tools=composio_tools, limit=50
    ):
        yield ComposioLLMTool(tool_spec, composio_tools[tool_spec.slug])


class VectorSearchLLMTool(BaseLLMTool):
    system_prompt = """
## file_search
Before answering a question, call this tool to lookup information from the knowledge base to inform your responses.
- Given the user's question, formulate a natural language search query that is slightly verbose and precise about intent, entities, and constraints.
- Use the Search Results to produce a coherent answer.
- Search results may be incomplete or irrelevant. Don't make assumptions on the Search Results beyond strictly what's returned.
- Leverage information from multiple search results to respond comprehensively
"""

    def __init__(self, state: dict):
        self.state = state
        super().__init__(
            name="file_search",
            label="File Search",
            description="""
Performs semantic search across a collection of files.
Parts of the documents uploaded by users will returned by this tool.
Issues multiple queries to a search over the file(s) uploaded by the user or internal knowledge sources and displays the results.
You can issue up to five queries at a time.
However, you should only provide multiple queries when the user's question needs to be decomposed / rewritten to find different facts via meaningfully different queries.
Otherwise, prefer providing a single well-written query. Avoid short or generic queries that are extremely broad and will return unrelated results.
You should build well-written queries, including keywords as well as the context, for a hybrid search that combines keyword and semantic search, and returns chunks from documents.
            """,
            properties={
                "queries": {
                    "type": "array",
                    "items": {
                        "type": "string",
                    },
                    "description": "The search queries to use.",
                },
            },
            required=["queries"],
        )

    def call(self, queries: list[str]) -> dict[str, list[str]]:
        from daras_ai_v2.language_model_openai_realtime import yield_from
        from daras_ai_v2.vector_search import DocSearchRequest, get_top_k_references

        return {
            query: yield_from(
                get_top_k_references(
                    DocSearchRequest.model_validate(
                        self.state | {"search_query": query}
                    )
                )
            )
            for query in queries
        }


class UpdateGuiStateLLMTool(BaseLLMTool):
    def __init__(self, state, page_slug):
        from daras_ai_v2.all_pages import normalize_slug, page_slug_map

        self.state = state or {}
        try:
            page_cls = page_slug_map[normalize_slug(page_slug)]
        except KeyError:
            request = self.state.get("request", self.state)
            properties = dict(generate_tool_properties(request, {}))
        else:
            schema = page_cls.RequestModel.model_json_schema(ref_template="{model}")
            properties = schema["properties"]

        properties["-submit-workflow"] = {
            "type": "boolean",
            "description": "Submit & Run the workflow.",
        }

        super().__init__(
            name="update_gui_state",
            label="Update GUI State",
            description="Update the current GUI state.",
            properties=properties,
        )

    def call(self, **kwargs) -> str:
        # handled by the frontend in gooey-web-widget
        return "ok"


class RunJS(BaseLLMTool):
    def __init__(self):
        super().__init__(
            name="run_js",
            label="Run JS",
            description="Run arbitrary JS code on the frontend",
            properties={
                "js_code": {
                    "type": "string",
                    "description": "The JS code to run on the frontend.",
                }
            },
        )

    def call(self, js_code: str) -> str:
        # handled by the frontend in gooey-web-widget
        return "ok"


class CallTransferLLMTool(BaseLLMTool):
    """In-Built tool for transferring phone calls."""

    system_prompt = """
## transfer_call
You can transfer the user's call to another phone number using this tool. Some examples of when to use this tool:
- When the user has directly asked to transfer their call or connect them with a phone number.
- When responding with a phone number, offer to transfer their call, even if they haven't explicitly asked to be transferred.
- Before transferring the call, say "Transferring you now..." and then call this tool.
- You MUST NOT make up telephone numbers. You MUST ensure you know the phone number is explicitly from a Knowledge Base before offering to transfer or providing it.
""".strip()

    def __init__(self):
        super().__init__(
            name="transfer_call",
            label="Transfer Call",
            description=(
                "Transfer the active phone call to another phone number. "
                "This will immediately end the current conversation and connect the caller to the specified number. "
                "Use this when the user requests to speak with someone else, "
                "needs to be transferred to a different department, "
                "or when you cannot help them and they need human assistance."
            ),
            properties={
                "phone_number": {
                    "type": "string",
                    "description": (
                        "The destination phone number to transfer the call to. "
                        "Must be in E.164 international format. "
                        "E.164 is the international telephone numbering plan that ensures each device on the PSTN has globally unique number. "
                        "This number allows phone calls and text messages can be correctly routed to individual phones in different countries. "
                        "E.164 numbers are formatted [+] [country code] [subscriber number including area code] and can have a maximum of fifteen digits."
                    ),
                }
            },
            required=["phone_number"],
            await_audio_completed=True,
        )

    def bind(self, *, call_sid: str, bi_id: str):
        self.call_sid = call_sid
        self.bi_id = bi_id
        return self

    def call(self, phone_number: str) -> dict:
        from daras_ai_v2.fastapi_tricks import get_api_route_url
        from routers.bots_api import api_hashids
        from routers.twilio_api import twilio_voice_call_status

        try:
            self.call_sid, self.bi_id
        except AttributeError:
            raise RuntimeError(f"This {self.__class__} instance is not yet bound")

        # Validate the phone number before attempting transfer
        try:
            validate_phonenumber(phone_number)
        except ValidationError as e:
            return {
                "success": False,
                "error": f"Invalid phone number format: {str(e)} number should be in E.164 format, try again",
            }

        try:
            bi_id_decoded = api_hashids.decode(self.bi_id)[0]
            bi = BotIntegration.objects.get(id=bi_id_decoded)
        except (IndexError, BotIntegration.DoesNotExist) as e:
            logger.debug(
                f"could not find bot integration with bot_id={self.bi_id}, call_sid={self.call_sid} {e}"
            )
            capture_exception(e)
            return {
                "success": False,
                "error": f"Bot integration not found for bi_id={self.bi_id}",
            }

        client = bi.get_twilio_client()

        resp = VoiceResponse()
        resp.dial(phone_number, action=get_api_route_url(twilio_voice_call_status))

        try:
            # try to transfer the call
            client.calls(self.call_sid).update(twiml=str(resp))
        except TwilioRestException as e:
            logger.error(f"Failed to transfer call: {e}")
            capture_exception(e)
            return {
                "success": False,
                "error": f"Failed to transfer call: {str(e)}",
            }
        else:
            logger.info(f"Successfully initiated transfer to {phone_number}")
            return {
                "success": True,
                "message": f"Successfully initiated transfer to {phone_number}",
            }


class FeedbackCollectionLLMTool(BaseLLMTool):
    """In-Built tool for collecting detailed feedback from users."""

    system_prompt = (
        "If the user is providing any feedback, suggestions or corrections instead of a question, "
        "save the feedback by calling the collect_feedback tool. "
        "Don't give an alternative answer, simply accept the feedback as-is."
    )

    def __init__(self, platform_msg_id: str, conversation_id: str):
        from bots.models.convo_msg import Feedback

        self.platform_msg_id = platform_msg_id
        self.conversation_id = conversation_id

        super().__init__(
            name="collect_feedback",
            label="Collect Feedback",
            description=(
                "Collect and save any feedback from the user. "
                "Use this when the user shares feedback about the quality of your response or corrections / comments on your response."
            ),
            properties={
                "sentiment": {
                    "type": "string",
                    "description": (
                        "The sentiment of the user's last message. "
                        "If the user is appreciating your response, choose positive. "
                        "If the user is not happy, is criticizing or is correcting you, choose negative. "
                        "If you are not sure, choose neutral. "
                    ),
                    "enum": Feedback.Rating.names,
                },
                "feedback_text": {
                    "type": "string",
                    "description": "The feedback text from the user. This will be used to improve the bot's response.",
                },
            },
            required=["feedback_text"],
        )

    def call(self, sentiment: str, feedback_text: str) -> dict:
        from bots.models import Feedback, Message
        from routers.bots_api import api_hashids

        try:
            last_msg = Message.objects.get(
                platform_msg_id=self.platform_msg_id,
                conversation_id=api_hashids.decode(self.conversation_id)[0],
            )
        except (IndexError, Message.DoesNotExist):
            return {
                "success": False,
                "error": f"Message not found for platform_msg_id={self.platform_msg_id} and conversation_id={self.conversation_id}",
            }

        try:
            rating = Feedback.Rating[sentiment]
        except Feedback.DoesNotExist:
            return {
                "success": False,
                "error": f"Invalid sentiment: {sentiment}. Must be one of {Feedback.Rating.names}",
            }

        try:
            feedback = last_msg.feedbacks.get(rating=rating, text="", text_english="")
        except Feedback.DoesNotExist:
            feedback = Feedback(message=last_msg, rating=rating)

        feedback.text_english = feedback_text
        feedback.save()

        return {"success": True}


class GooeyMemoryLLMToolRead(BaseLLMTool):
    name = "GOOEY_MEMORY_READ_VALUE"

    def __init__(self, scope: FunctionScopes | None):
        self.scope = scope
        super().__init__(
            name=self.name,
            label="Read Value from Gooey.AI Memory",
            description="Read the value of a key from the Gooey.AI store.",
            properties={
                "key": {
                    "type": "string",
                    "description": "The key to read from the Gooey.AI store.",
                },
            },
            required=["key"],
        )

    def bind(self, user_id: str):
        self.user_id = user_id
        return self

    def call(self, key: str) -> dict:
        try:
            value = MemoryEntry.objects.get(user_id=self.user_id, key=key).value
        except MemoryEntry.DoesNotExist:
            return {"success": False, "error": f"Key not found: {key}"}
        return {"success": True, "key": key, "value": value}


class GooeyMemoryLLMToolWrite(BaseLLMTool):
    name = "GOOEY_MEMORY_WRITE_VALUE"

    def __init__(self, scope: FunctionScopes):
        self.scope = scope
        super().__init__(
            name=self.name,
            label="Write Value to Gooey.AI Memory",
            description="Write a value to the Gooey.AI store.",
            properties={
                "key": {
                    "type": "string",
                    "description": "The key to write to the Gooey.AI store.",
                },
                "value": {
                    "type": "string",
                    "description": "The value to write to the Gooey.AI store.",
                },
            },
            required=["key", "value"],
        )

    def bind(self, user_id: str):
        self.user_id = user_id
        return self

    def call(self, key: str, value) -> dict:
        from celeryapp.tasks import get_running_saved_run

        saved_run = get_running_saved_run()
        MemoryEntry.objects.update_or_create(
            user_id=self.user_id,
            key=key,
            defaults=dict(value=value, saved_run=saved_run, updated_at=timezone.now()),
        )
        return {"success": True}


class GooeyMemoryLLMToolDelete(BaseLLMTool):
    name = "GOOEY_MEMORY_DELETE_VALUE"

    def __init__(self, scope: FunctionScopes):
        self.scope = scope
        super().__init__(
            name=self.name,
            label="Delete Value from Gooey.AI Memory",
            description="Delete a value from the Gooey.AI store.",
            properties={
                "key": {
                    "type": "string",
                    "description": "The key to delete from the Gooey.AI store.",
                },
            },
            required=["key"],
        )

    def bind(self, user_id: str):
        self.user_id = user_id
        return self

    def call(self, key: str) -> dict:
        MemoryEntry.objects.filter(user_id=self.user_id, key=key).delete()
        return {"success": True}


INBUILT_INTEGRATION_TOOLS = {
    tool.name: tool
    for tool in [
        GooeyMemoryLLMToolRead,
        GooeyMemoryLLMToolWrite,
        GooeyMemoryLLMToolDelete,
    ]
}
