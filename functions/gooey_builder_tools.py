from __future__ import annotations

import json
import typing

from app_users.models import AppUser
from daras_ai_v2.exceptions import UserError
from functions.base_llm_tool import (
    BaseLLMTool,
    generate_tool_properties,
)

if typing.TYPE_CHECKING:
    pass


class UpdateGuiStateLLMTool(BaseLLMTool):
    def __init__(self, builder_state: dict, page_slug: str):
        from daras_ai_v2.all_pages import normalize_slug, page_slug_map

        request = builder_state.get("request", builder_state)
        try:
            page_cls = page_slug_map[normalize_slug(page_slug)]
        except KeyError:
            properties = dict(generate_tool_properties(request, {}))
        else:
            properties = page_cls.get_tool_call_schema(request)

        properties["-submit-workflow"] = {
            "type": "boolean",
            "description": "Submit & Run the workflow.",
        }

        super().__init__(
            name="update_gui_state",
            label="Update Workflow",
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


class DeployWorkflowLLMTool(BaseLLMTool):
    def __init__(self, builder_state: dict):
        from daras_ai_v2.bot_integration_add import has_available_country_codes
        from number_cycling.models import SharedPhoneNumber
        from bots.models import BotIntegration, Platform
        from bots.models import SavedRun
        from daras_ai_v2.bot_integration_add import deploy_choices

        self.saved_run = SavedRun.objects.get(
            run_id=builder_state["run_id"], uid=builder_state["uid"]
        )
        self.published_run = self.saved_run.parent_published_run()

        description = "Deploy the current published copilot/workflow to an end-user channel so real users can talk to it. "

        qs = BotIntegration.objects.filter(
            published_run=self.published_run,
            workspace=self.saved_run.workspace,
        ).order_by("platform", "-created_at")
        existing = [bi_info_result_for_llm(bi) for bi in qs]

        if existing:
            description += (
                "\n\nExisting deployments already connected to this workflow: "
                + json.dumps(existing)
                + "\n\nIf an existing deployment already exists for a platform, "
                "print the test_link, phone_number, and deployment_url for the existing deployments as markdown. "
                "Don't call this tool as it will create a duplicate deployment. "
            )

        description += (
            "\n\nCall this when the user asks to deploy, publish, connect, embed, install, or 'add' their "
            "agent/copilot/bot to a channel (Web, WhatsApp, Telegram, Slack, Voice/SMS, Facebook Messenger)."
            "\n\n"
            "If the tool returns a `connect_url`, surface it to the user as a clickable "
            "link and tell them what they will be asked to do on the other side.\n"
            "\n"
            "Once deployed, print the test_link, phone_number, and deployment_url to the user as markdown. "
            "\n\n"
            "Behavior per platform:\n"
            "- WEB: Instantly creates an embeddable web chat widget (inline / popup / fullscreen). Returns a test "
            "link and the deployment page URL where the user can grab the <script> embed snippet. No extra input "
            "needed.\n"
            "- WHATSAPP: Tries to provision a Gooey-managed WhatsApp number for the workspace.\n"
            "- TELEGRAM: Requires `telegram_bot_token`. You MUST ask the user to create a bot via @BotFather on "
            "Telegram (`/newbot`) and paste the token back before calling this tool. Do not invent a token. "
            "Returns the bot's Telegram username and a test link.\n"
            "- SLACK: Returns a `connect_url` that starts the Slack OAuth 'Add to Workspace' flow. The user picks "
            "the channel and approves permissions in Slack; the bot then responds to @mentions, threads, "
            "and Slack audio/video clips in that channel.\n"
            "- TWILIO: Deploys a Voice + SMS agent on a Gooey-managed phone number. Returns the phone number users can call/text.\n"
            "- FACEBOOK: Returns a `connect_url` for the Facebook Login flow to attach a Facebook "
            "Page or Instagram account.\n"
        )

        properties: dict = {
            "platform": {
                "type": "string",
                "enum": [choice.platform.name for choice in deploy_choices],
                "description": "The deployment channel.",
            },
            "telegram_bot_token": {
                "type": "string",
                "description": (
                    "Required when platform is TELEGRAM. The BotFather token for the Telegram bot "
                    "(looks like '123456789:ABC-DEF...'). "
                    "You MUST ask the user to create a bot with @BotFather (`/newbot`) and paste the token; "
                    "never fabricate a token or call this tool for Telegram without one."
                ),
            },
        }
        if has_available_country_codes(Platform.TWILIO):
            properties["twilio_country_code"] = {
                "type": "string",
                "enum": list(
                    SharedPhoneNumber.objects.available_country_codes(Platform.TWILIO)
                ),
                "description": (
                    "Optional ISO 3166-1 alpha-2 country code used when provisioning a Gooey-managed TWILIO voice/SMS number."
                    "and Gooey will assign any available number."
                ),
            }
        if has_available_country_codes(Platform.WHATSAPP):
            properties["whatsapp_country_code"] = {
                "type": "string",
                "enum": list(
                    SharedPhoneNumber.objects.available_country_codes(Platform.WHATSAPP)
                ),
                "description": (
                    "Optional ISO 3166-1 alpha-2 country code used when provisioning a Gooey-managed WHATSAPP number."
                ),
            }

        super().__init__(
            name="deploy_workflow",
            label="Deploy this Workflow",
            description=description,
            properties=properties,
            required=["platform"],
        )

    def call(
        self,
        platform: str,
        name: str | None = None,
        twilio_country_code: str | None = None,
        whatsapp_country_code: str | None = None,
        telegram_bot_token: str | None = None,
    ) -> dict:
        from daras_ai_v2.bot_integration_connect import create_deployment
        from bots.models import Platform

        for platform_enum in Platform:
            if platform_enum.name.lower() == platform.lower():
                break
        else:
            return {"success": False, "error": "Invalid platform"}

        try:
            bi, redirect_url = create_deployment(
                platform=platform_enum,
                workspace=self.saved_run.workspace or self.published_run.workspace,
                user=AppUser.objects.get(uid=self.saved_run.uid),
                published_run=self.published_run,
                country_code=twilio_country_code or whatsapp_country_code,
                telegram_bot_token=telegram_bot_token,
            )
        except UserError as e:
            return {"success": False, "error": str(e)}

        if bi:
            result = bi_info_result_for_llm(bi)
            result["success"] = True
            return result
        else:
            return {"success": True, "connect_url": redirect_url}


def bi_info_result_for_llm(bi) -> dict:
    from bots.models import Platform

    info = dict(
        platform=Platform(bi.platform).name,
        name=bi.get_display_name(),
        workflow_url=bi.published_run and bi.published_run.get_app_url(),
        test_link=bi.get_bot_test_link(),
        deployment_url=bi.get_deployment_url(),
    )
    if bi.extension_number:
        info["extension_number"] = bi.extension_number

    match Platform(bi.platform):
        case Platform.WHATSAPP:
            info["phone_number"] = bi.wa_phone_number and bi.wa_phone_number.as_e164
        case Platform.TWILIO:
            info["phone_number"] = (
                bi.twilio_phone_number and bi.twilio_phone_number.as_e164
            )
        case Platform.TELEGRAM:
            info["telegram_bot_id"] = bi.telegram_bot_id
            info["telegram_bot_user_name"] = bi.telegram_bot_user_name

    return info
