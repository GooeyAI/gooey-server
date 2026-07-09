import pytest

from app_users.models import AppUser
from bots.models import BotIntegration, Platform, SavedRun, Workflow
from functions.gooey_builder_deploy_tool import UpdateDeploymentSettingsLLMTool
from recipes.VideoBots import VideoBotsPage
from workspaces.models import Workspace


@pytest.fixture
def wa_deployment(transactional_db):
    user = AppUser.objects.create(uid="test_user", is_anonymous=False, balance=1000)
    workspace = Workspace.objects.create(
        name="myteam", created_by=user, is_personal=True
    )
    sr = SavedRun.objects.create(
        workflow=Workflow.VIDEO_BOTS,
        run_id="test_run",
        uid=user.uid,
        workspace=workspace,
    )
    pr = VideoBotsPage.create_published_run(
        published_run_id="test-pr-id",
        saved_run=sr,
        user=user,
        workspace=workspace,
        title="Test Copilot",
        notes="",
    )
    builder_sr = SavedRun.objects.create(
        workflow=Workflow.VIDEO_BOTS,
        run_id="builder_run",
        uid=user.uid,
        workspace=workspace,
    )
    bi = BotIntegration.objects.create(
        name="Test Copilot",
        created_by=user,
        workspace=workspace,
        platform=Platform.WHATSAPP,
        wa_phone_number="+15550179180",
        wa_phone_number_id="test_wa_phone_id",
        published_run=pr,
    )
    return sr, pr, builder_sr, bi


def test_update_deployment_settings_enable_feedback_buttons(wa_deployment):
    sr, pr, builder_sr, bi = wa_deployment
    assert not bi.show_feedback_buttons

    tool = UpdateDeploymentSettingsLLMTool(VideoBotsPage, sr, pr, builder_sr)
    assert bi.api_integration_id() in tool.properties["integration_id"]["enum"]

    result = tool.call(
        integration_id=bi.api_integration_id(), show_feedback_buttons=True
    )
    assert result["success"]
    assert result["settings"]["show_feedback_buttons"]

    bi.refresh_from_db()
    assert bi.show_feedback_buttons


def test_update_deployment_settings_multiple_fields(wa_deployment):
    sr, pr, builder_sr, bi = wa_deployment
    tool = UpdateDeploymentSettingsLLMTool(VideoBotsPage, sr, pr, builder_sr)

    result = tool.call(
        integration_id=bi.api_integration_id(),
        name="Renamed Copilot",
        streaming_enabled=True,
        ask_detailed_feedback=True,
    )
    assert result["success"]

    bi.refresh_from_db()
    assert bi.name == "Renamed Copilot"
    assert bi.streaming_enabled
    assert bi.ask_detailed_feedback
    # untouched settings are left as-is
    assert not bi.show_feedback_buttons


def test_update_deployment_settings_invalid_integration_id(wa_deployment):
    sr, pr, builder_sr, bi = wa_deployment
    tool = UpdateDeploymentSettingsLLMTool(VideoBotsPage, sr, pr, builder_sr)

    result = tool.call(integration_id="notarealid", show_feedback_buttons=True)
    assert not result["success"]
    bi.refresh_from_db()
    assert not bi.show_feedback_buttons


def test_update_deployment_settings_other_workspace_denied(wa_deployment):
    sr, pr, builder_sr, bi = wa_deployment

    other_user = AppUser.objects.create(
        uid="other_user", is_anonymous=False, balance=1000
    )
    other_workspace = Workspace.objects.create(
        name="otherteam", created_by=other_user, is_personal=True
    )
    other_bi = BotIntegration.objects.create(
        name="Other Copilot",
        created_by=other_user,
        workspace=other_workspace,
        platform=Platform.WHATSAPP,
        wa_phone_number="+15550179181",
        wa_phone_number_id="other_wa_phone_id",
    )

    tool = UpdateDeploymentSettingsLLMTool(VideoBotsPage, sr, pr, builder_sr)
    assert other_bi.api_integration_id() not in (
        tool.properties["integration_id"]["enum"]
    )

    result = tool.call(
        integration_id=other_bi.api_integration_id(), show_feedback_buttons=True
    )
    assert not result["success"]
    other_bi.refresh_from_db()
    assert not other_bi.show_feedback_buttons


def test_update_deployment_settings_no_fields(wa_deployment):
    sr, pr, builder_sr, bi = wa_deployment
    tool = UpdateDeploymentSettingsLLMTool(VideoBotsPage, sr, pr, builder_sr)

    result = tool.call(integration_id=bi.api_integration_id())
    assert not result["success"]
