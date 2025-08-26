import typing

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

    variables = state.get("variables") or {}

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


class UpdateGuiStateLLMTool(BaseLLMTool):
    def __init__(self, state, page_slug):
        from daras_ai_v2.all_pages import page_slug_map, normalize_slug

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
## Transfer Call
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
        from routers.bots_api import api_hashids
        from daras_ai_v2.fastapi_tricks import get_api_route_url
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
