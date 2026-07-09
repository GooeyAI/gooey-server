from __future__ import annotations

import json
from bots.models.published_run import PublishedRun
from daras_ai_v2.bot_integration_connect import create_deployment
from bots.models import Platform
import typing

from app_users.models import AppUser
from daras_ai_v2.exceptions import UserError
from django.core.exceptions import ValidationError

from bots.models import SavedRun
from daras_ai_v2.base import BasePage


from daras_ai_v2.bot_integration_add import has_available_country_codes
from functions.gooey_builder_workflow_tools import GooeyBuilderLLMTool
from number_cycling.models import SharedPhoneNumber
from bots.models import BotIntegration
from daras_ai_v2.bot_integration_add import deploy_choices


class DeployWorkflowLLMTool(GooeyBuilderLLMTool):
    def __init__(
        self,
        page_cls: typing.Type[BasePage],
        sr: SavedRun,
        pr: PublishedRun,
        builder_sr: SavedRun,
    ):
        self.page_cls = page_cls
        self.sr = sr
        self.pr = pr
        self.builder_sr = builder_sr

        description = "Deploy the current saved agent workflow to an end-user channel so real users can talk to it. "

        if self.sr.state != self.pr.saved_run.state:
            description += (
                "The current workflow is not saved. Call `save_workflow` / `save_as_new_workflow` "
                "before deploying or else the deployment's users will see an older version of the workflow."
            )
            properties = {}
        else:
            qs = BotIntegration.objects.filter(
                published_run=self.pr,
                workspace=self.sr.workspace,
            ).order_by("platform", "-created_at")
            existing = [bi_info_result_for_llm(bi) for bi in qs]

            if existing:
                description += (
                    "\n\nExisting deployments already connected to this workflow: "
                    + json.dumps(existing)
                    + "\n\nIf an existing deployment already exists for a platform, "
                    "print the test_link, phone_number, and deployment_url for the existing deployments as markdown. "
                    "Don't call this tool as it will create a duplicate deployment. "
                    f"To change the settings of an existing deployment (e.g. feedback buttons, streaming), "
                    f"call `{UpdateDeploymentSettingsLLMTool.name}` instead. "
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
                        SharedPhoneNumber.objects.available_country_codes(
                            Platform.TWILIO
                        )
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
                        SharedPhoneNumber.objects.available_country_codes(
                            Platform.WHATSAPP
                        )
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
        for platform_enum in Platform:
            if platform_enum.name.lower() == platform.lower():
                break
        else:
            return {"success": False, "error": "Invalid platform"}

        try:
            bi, redirect_url = create_deployment(
                platform=platform_enum,
                workspace=self.sr.workspace,
                user=AppUser.objects.get(uid=self.sr.uid),
                published_run=self.pr,
                country_code=twilio_country_code or whatsapp_country_code,
                telegram_bot_token=telegram_bot_token,
            )
        except UserError as e:
            return {"success": False, "error": str(e)}

        if bi:
            self.url = bi.get_deployment_url()
            result = bi_info_result_for_llm(bi)
            result["success"] = True
            return result
        else:
            return {"success": True, "connect_url": redirect_url}


class UpdateDeploymentSettingsLLMTool(GooeyBuilderLLMTool):
    name = "update_deployment_settings"

    def __init__(
        self,
        page_cls: typing.Type[BasePage],
        sr: SavedRun,
        pr: PublishedRun,
        builder_sr: SavedRun,
    ):
        self.page_cls = page_cls
        self.sr = sr
        self.pr = pr
        self.builder_sr = builder_sr

        description = (
            "Update the settings of an existing deployment connected to this workflow. "
            "Call this when the user asks to rename a deployment, or enable/disable feedback buttons, "
            "detailed feedback, or streaming on a deployed channel "
            "(Web, WhatsApp, Telegram, Slack, Facebook Messenger). "
            "Only the settings you pass are changed; the rest are left as-is. "
        )

        qs = BotIntegration.objects.filter(
            published_run=self.pr,
            workspace=self.sr.workspace,
        ).order_by("platform", "-created_at")
        existing = [bi_info_result_for_llm(bi) for bi in qs]
        if existing:
            description += (
                "\n\nExisting deployments connected to this workflow: "
                + json.dumps(existing)
            )
            properties = {
                "integration_id": {
                    "type": "string",
                    "enum": [bi.api_integration_id() for bi in qs],
                    "description": "The `integration_id` of the deployment to update.",
                },
                "name": {
                    "type": "string",
                    "description": "New display name for the deployment.",
                },
                "streaming_enabled": {
                    "type": "boolean",
                    "description": (
                        "Stream responses to the user in real-time. "
                        "Not applicable to TWILIO voice/SMS deployments."
                    ),
                },
                "show_feedback_buttons": {
                    "type": "boolean",
                    "description": (
                        "Show 👍/👎 feedback buttons with every response so users can rate it. "
                        "Not applicable to TWILIO voice/SMS deployments."
                    ),
                },
                "ask_detailed_feedback": {
                    "type": "boolean",
                    "description": (
                        "When users give a thumbs down, ask them to explain what was wrong "
                        "and how it could be improved. Requires `show_feedback_buttons` to be enabled. "
                        "Not applicable to TWILIO voice/SMS deployments."
                    ),
                },
            }
            required = ["integration_id"]
        else:
            description += (
                "\n\nThere are no deployments connected to this workflow yet. "
                "Call `deploy_workflow` first."
            )
            properties = {}
            required = None

        super().__init__(
            name=self.name,
            label="Update Deployment Settings",
            description=description,
            properties=properties,
            required=required,
        )

    def call(
        self,
        integration_id: str = "",
        name: str | None = None,
        streaming_enabled: bool | None = None,
        show_feedback_buttons: bool | None = None,
        ask_detailed_feedback: bool | None = None,
    ) -> dict:
        from routers.bots_api import api_hashids

        try:
            bi = BotIntegration.objects.get(
                id=api_hashids.decode(integration_id)[0],
                published_run=self.pr,
                workspace=self.sr.workspace,
            )
        except (IndexError, BotIntegration.DoesNotExist):
            return {
                "success": False,
                "error": "Deployment not found. Pass the `integration_id` of one of the existing deployments connected to this workflow.",
            }

        updates = dict(
            name=name,
            streaming_enabled=streaming_enabled,
            show_feedback_buttons=show_feedback_buttons,
            ask_detailed_feedback=ask_detailed_feedback,
        )
        update_fields = []
        for field, value in updates.items():
            if value is None:
                continue
            setattr(bi, field, value)
            update_fields.append(field)
        if not update_fields:
            return {"success": False, "error": "No settings provided to update."}

        try:
            bi.full_clean()
        except ValidationError as e:
            return {"success": False, "error": str(e)}
        bi.save(update_fields=update_fields + ["updated_at"])

        self.url = bi.get_deployment_url()
        result = bi_info_result_for_llm(bi)
        result["success"] = True
        return result


def bi_info_result_for_llm(bi) -> dict:
    info = dict(
        integration_id=bi.api_integration_id(),
        platform=Platform(bi.platform).name,
        name=bi.get_display_name(),
        workflow_url=bi.published_run and bi.published_run.get_app_url(),
        test_link=bi.get_bot_test_link(),
        deployment_url=bi.get_deployment_url(),
        settings=dict(
            name=bi.name,
            streaming_enabled=bi.streaming_enabled,
            show_feedback_buttons=bi.show_feedback_buttons,
            ask_detailed_feedback=bi.ask_detailed_feedback,
        ),
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
