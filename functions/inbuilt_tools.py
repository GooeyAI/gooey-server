import typing
import uuid
import random

import gooey_gui as gui
from django.core.exceptions import ValidationError
from loguru import logger
from sentry_sdk import capture_exception
from twilio.base.exceptions import TwilioRestException
from twilio.twiml.voice_response import VoiceResponse

from bots.models import BotIntegration
from bots.models.bot_integration import validate_phonenumber
from functions.recipe_functions import BaseLLMTool, generate_tool_properties


def get_inbuilt_tools_from_state(state: dict) -> typing.Iterable[BaseLLMTool]:
    from daras_ai_v2.language_model_openai_audio import is_realtime_audio_url

    audio_url = state.get("input_audio")
    if is_realtime_audio_url(audio_url):
        yield CallTransferLLMTool()

    update_gui_state_params = (state.get("variables") or {}).get(
        "update_gui_state_params"
    )
    if update_gui_state_params:
        yield UpdateGuiStateLLMTool(
            update_gui_state_params.get("channel"),
            update_gui_state_params.get("state"),
            update_gui_state_params.get("page_slug"),
        )

    # Add feedback collection tool if needed
    feedback_collection_params = (state.get("variables") or {}).get(
        "feedback_collection_params"
    )
    if feedback_collection_params:
        feedback_type = feedback_collection_params.get("feedback_type")
        if feedback_type in ["thumbs_up", "thumbs_down"]:
            yield FeedbackCollectionLLMTool(feedback_type)


class UpdateGuiStateLLMTool(BaseLLMTool):
    def __init__(self, channel, state, page_slug):
        from daras_ai_v2.all_pages import page_slug_map, normalize_slug

        self.channel = channel
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

    def call(self, **kwargs) -> dict:
        if not self.channel:
            return {"success": False, "error": "update channel not found"}

        # collect all updates from the tool call into a single dict that can be pushed to the UI
        updates = self.state.setdefault("updates", {})
        # sometimes the state is nested in the kwargs, so we need to get the state from the kwargs
        updates.update(kwargs.get("state", kwargs))

        # generate a nonce so UI can detect if the state has changed or not
        nonce_info = {"-gooey-builder-nonce": str(uuid.uuid4())}
        # push the state back to the UI, expire in 1 minute
        gui.realtime_push(self.channel, updates | nonce_info, ex=60)

        return {"success": True, "updated": list(updates.keys())}


class CallTransferLLMTool(BaseLLMTool):
    """In-Built tool for transferring phone calls."""

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
        from routers.bots_api import api_hashids

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
        resp.dial(phone_number)

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

    # Predefined feedback messages for thumbs down
    THUMBS_DOWN_MESSAGES = [
        "🙏  Thank you. I'd love to know what was off about my answer.",
        "🙏 Thanks for the feedback — anything to be improved?",
        "✅ Noted — feel free to share what didn't work.",
        "🤔 Appreciate the feedback — have any suggestions?",
    ]

    def __init__(self, feedback_type: str):
        self.feedback_type = feedback_type  # "thumbs_up" or "thumbs_down"

        if feedback_type == "thumbs_up":
            description = (
                "Collect detailed feedback about what the user liked about the response"
            )
            instruction = "Ask the user what they liked about the response"
        else:
            description = "Collect detailed feedback about what was wrong with the response and how it could be improved"
            instruction = "Ask the user for detailed feedback using one of the predefined messages"

        super().__init__(
            name="collect_feedback",
            label="Collect Feedback",
            description=description,
            properties={
                "feedback_question": {
                    "type": "string",
                    "description": f"{instruction} and wait for their detailed response",
                }
            },
            required=["feedback_question"],
        )

    def call(self, feedback_question: str) -> dict:
        # Use the exact feedback question provided by the LLM
        return {
            "success": True,
            "message": feedback_question,
            "feedback_question": feedback_question,
        }
