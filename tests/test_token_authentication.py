import pytest
from datetime import timedelta
from auth.token_authentication import (
    generate_ephemeral_api_key,
    verify_ephemeral_api_key,
    AuthenticationError,
    AuthorizationError,
    EPHEMERAL_KEY_PREFIX,
)
from app_users.models import AppUser
from workspaces.models import Workspace
from bots.models.saved_run import SavedRun


@pytest.fixture
def test_user(transactional_db):
    return AppUser.objects.create(
        uid="test_uid", email="test@example.com", is_anonymous=False
    )


@pytest.fixture
def test_workspace(transactional_db, test_user):
    return Workspace.objects.create(created_by=test_user, is_personal=True)


@pytest.fixture
def test_saved_run(transactional_db, test_workspace, test_user):
    return SavedRun.objects.create(
        run_id="test_run_id",
        uid=test_user.uid,
        workspace=test_workspace,
        state={"run_status": "Running..."},
        run_status="Running...",
    )


def test_ephemeral_api_key_success(
    transactional_db, test_user, test_workspace, test_saved_run
):
    token = generate_ephemeral_api_key(
        test_user.id, str(test_workspace.id), test_saved_run.run_id
    )
    assert token.startswith(EPHEMERAL_KEY_PREFIX)
    result = verify_ephemeral_api_key(token)
    assert result.workspace.id == test_workspace.id
    assert result.created_by.id == test_user.id


def test_ephemeral_api_key_anonymous_user(
    transactional_db, test_workspace, test_saved_run
):
    anon_user = AppUser.objects.create(uid="anon_uid", is_anonymous=True)
    test_saved_run.uid = anon_user.uid
    test_saved_run.save()

    token = generate_ephemeral_api_key(
        anon_user.id, str(test_workspace.id), test_saved_run.run_id
    )
    result = verify_ephemeral_api_key(token)
    assert result.created_by.id == anon_user.id
    assert result.created_by.is_anonymous is True


@pytest.mark.parametrize(
    "run_kwargs",
    [
        {"run_id": "completed", "run_time": timedelta(seconds=10)},  # Completed
        {
            "run_id": "failed",
            "error_msg": "Error",
            "state": {"error_msg": "Error"},
        },  # Failed
        {"run_id": "standby", "run_status": ""},  # Standby
    ],
)
def test_ephemeral_api_key_invalid_run_states(
    transactional_db, test_user, test_workspace, run_kwargs
):
    saved_run = SavedRun.objects.create(
        uid=test_user.uid, workspace=test_workspace, **run_kwargs
    )
    token = generate_ephemeral_api_key(
        test_user.id, str(test_workspace.id), saved_run.run_id
    )
    with pytest.raises(AuthenticationError) as exc:
        verify_ephemeral_api_key(token)
    assert "Invalid API Key" in str(exc.value.detail)


def test_ephemeral_api_key_security_failures(
    transactional_db, test_user, test_workspace, test_saved_run
):
    # 1. Invalid Signature
    with pytest.raises(AuthenticationError, match="Invalid API Key"):
        verify_ephemeral_api_key(EPHEMERAL_KEY_PREFIX + "bad_sig")

    # 2. Disabled User
    test_user.is_disabled = True
    test_user.save()
    token = generate_ephemeral_api_key(
        test_user.id, str(test_workspace.id), test_saved_run.run_id
    )
    with pytest.raises(AuthorizationError):
        verify_ephemeral_api_key(token)

    # 3. Deleted User (Race Condition)
    test_user.delete()
    with pytest.raises(AuthenticationError, match="Invalid API Key"):
        verify_ephemeral_api_key(token)
