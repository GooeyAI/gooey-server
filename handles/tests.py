from pytest_subtests import subtests

from app_users.models import AppUser
from daras_ai_v2.crypto import get_random_doc_id
from .models import Handle


def create_default_handle_by_name_and_email(name, email):
    user = AppUser.objects.create(
        display_name=name,
        email=email,
        balance=0,
        is_anonymous=False,
        uid=get_random_doc_id(),
    )
    return Handle.create_default_for_user(user)


def test_default_handle_when_user_is_anonymous(transactional_db):
    user = AppUser.objects.create(
        display_name="John Doe",
        email="johndoe@example.com",
        balance=0,
        is_anonymous=True,
        uid=get_random_doc_id(),
    )
    handle = Handle.create_default_for_user(user)
    assert handle is None


def test_default_handle_when_user_has_common_email(transactional_db):
    # without conflicts
    handle1 = create_default_handle_by_name_and_email("John Does", "johndoe@gmail.com")
    assert handle1 is not None
    assert handle1.name == "johndoe"

    # with prefix conflict
    handle2 = create_default_handle_by_name_and_email("John Does", "johndoe@yahoo.com")
    assert handle2 is not None
    assert handle2.name == "JohnDoes"

    # with both prefix and name conflict ...
    handle3 = create_default_handle_by_name_and_email(
        "John Does", "johndoe@hotmail.com"
    )
    assert handle3 is not None
    assert handle3.name == "JohnDoes1"

    handle4 = create_default_handle_by_name_and_email(
        "John Does", "johndoe@outlook.com"
    )
    assert handle4 is not None
    assert handle4.name == "JohnDoes2"

    # no name
    handle5 = create_default_handle_by_name_and_email("", "johndoe@aol.com")
    assert handle5 is None


def test_default_handle_when_user_has_private_email(transactional_db):
    # without conflicts
    handle1 = create_default_handle_by_name_and_email(
        "John Does", "johndoe1@privaterelay.appleid.com"
    )
    assert handle1 is not None
    assert handle1.name == "JohnDoes"

    # with name conflict
    handle2 = create_default_handle_by_name_and_email(
        "John Does", "johndoe2@privaterelay.appleid.com"
    )
    assert handle2 is not None
    assert handle2.name == "JohnDoes1"

    # no name
    handle3 = create_default_handle_by_name_and_email(
        "", "johndoe3@privaterelay.appleid.com"
    )
    assert handle3 is None


def test_default_handle_when_user_has_org_email(transactional_db):
    # without conflicts
    handle1 = create_default_handle_by_name_and_email("John Doe", "john@dara.network")
    assert handle1 is not None
    assert handle1.name == "JohnDoe"

    # with name conflict
    handle2 = create_default_handle_by_name_and_email("John Doe", "john@gooey.ai")
    assert handle2 is not None
    assert handle2.name == "JohnGooey"

    handle3 = create_default_handle_by_name_and_email(
        "John Doe", "john@gooey.example.com"
    )
    assert handle3 is not None
    assert handle3.name == "JohnGooey1"

    # with name conflict - with dots and dashes in email
    handle4 = create_default_handle_by_name_and_email(
        "John Doe", "john.doe@gooey-ai.example.com"
    )
    assert handle4 is not None
    assert handle4.name == "John.doeGooey-ai"


def test_default_handle_when_user_has_unicode_name(transactional_db):
    create_default_handle_by_name_and_email("", "johndoe@gmail.com")

    handle1 = create_default_handle_by_name_and_email(
        "john🚀does", "johndoe@googlemail.com"
    )
    assert handle1 is not None
    assert handle1.name == "JohnDoes"

    handle2 = create_default_handle_by_name_and_email("🚀", "johndoe@yahoo.com")
    assert handle2 is None
