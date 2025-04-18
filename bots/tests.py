import random
import uuid

from app_users.models import AppUser
from daras_ai_v2.functional import map_parallel
from recipes.VideoBotsStats import get_tabular_data
from workspaces.models import Workspace
from .models import (
    Message,
    Conversation,
    BotIntegration,
    Platform,
    ConvoState,
)

CHATML_ROLE_USER = "user"
CHATML_ROLE_ASSISSTANT = "assistant"


def test_add_balance(transactional_db):
    workspace = Workspace(
        name="myteam",
        created_by=AppUser.objects.create(is_anonymous=False),
        is_personal=True,
    )
    workspace.create_with_owner()
    pk = workspace.pk
    amounts = [[random.randint(-100, 10_000) for _ in range(100)] for _ in range(5)]

    def worker(amts):
        workspace = Workspace.objects.get(pk=pk)
        for amt in amts:
            workspace.add_balance(amt, invoice_id=uuid.uuid1())

    map_parallel(worker, amounts)

    assert Workspace.objects.get(pk=pk).balance == sum(map(sum, amounts))


def test_add_balance_txn(transactional_db):
    workspace = Workspace(
        name="myteam",
        created_by=AppUser.objects.create(is_anonymous=False),
        is_personal=True,
    )
    workspace.create_with_owner()
    pk = workspace.pk
    amounts = [[random.randint(-100, 10_000) for _ in range(100)] for _ in range(5)]

    def worker(amts):
        workspace = Workspace.objects.get(pk=pk)
        invoice_id = str(uuid.uuid1())
        for amt in amts:
            workspace.add_balance(amt, invoice_id=invoice_id)

    map_parallel(worker, amounts)

    assert Workspace.objects.get(pk=pk).balance == sum([amt[0] for amt in amounts])


def test_create_bot_integration_conversation_message(transactional_db):
    # Create a new BotIntegration with WhatsApp as the platform
    bot_integration = BotIntegration.objects.create(
        name="My Bot Integration",
        saved_run=None,
        user_language="en",
        show_feedback_buttons=True,
        platform=Platform.WHATSAPP,
        wa_phone_number="my_whatsapp_number",
        wa_phone_number_id="my_whatsapp_number_id",
    )

    # Create a Conversation that uses the BotIntegration
    conversation = Conversation.objects.create(
        bot_integration=bot_integration,
        state=ConvoState.INITIAL,
        wa_phone_number="user_whatsapp_number",
    )

    # Create a User Message within the Conversation
    message_u = Message.objects.create(
        conversation=conversation,
        role=CHATML_ROLE_USER,
        content="What types of chilies can be grown in Mumbai?",
        display_content="What types of chilies can be grown in Mumbai?",
    )

    # Create a Bot Message within the Conversation
    message_b = Message.objects.create(
        conversation=conversation,
        role=CHATML_ROLE_ASSISSTANT,
        content="Red, green, and yellow grow the best.",
        display_content="Red, green, and yellow grow the best.",
    )

    # Assert that the User Message was created successfully
    assert Message.objects.count() == 2
    assert message_u.conversation == conversation
    assert message_u.role == CHATML_ROLE_USER
    assert message_u.content == "What types of chilies can be grown in Mumbai?"
    assert message_u.display_content == "What types of chilies can be grown in Mumbai?"

    # Assert that the Bot Message was created successfully
    assert message_b.conversation == conversation
    assert message_b.role == CHATML_ROLE_ASSISSTANT
    assert message_b.content == "Red, green, and yellow grow the best."
    assert message_b.display_content == "Red, green, and yellow grow the best."


def test_stats_get_tabular_data_invalid_sorting_options(transactional_db):
    # setup
    bi = BotIntegration.objects.create(
        name="My Bot Integration",
        saved_run=None,
        user_language="en",
        show_feedback_buttons=True,
        platform=Platform.WHATSAPP,
        wa_phone_number="my_whatsapp_number",
        wa_phone_number_id="my_whatsapp_number_id",
    )
    convos = Conversation.objects.filter(bot_integration=bi)
    msgs = Message.objects.filter(conversation__in=convos)

    # valid option but no data
    df = get_tabular_data(
        bi=bi,
        conversations=convos,
        messages=msgs,
        details="Answered Successfully",
        sort_by="Name",
    )
    assert df.shape[0] == 0

    # valid option and data
    convo = Conversation.objects.create(
        bot_integration=bi,
        state=ConvoState.INITIAL,
        wa_phone_number="+919876543210",
    )
    Message.objects.create(
        conversation=convo,
        role=CHATML_ROLE_USER,
        content="What types of chilies can be grown in Mumbai?",
        display_content="What types of chilies can be grown in Mumbai?",
    )
    Message.objects.create(
        conversation=convo,
        role=CHATML_ROLE_ASSISSTANT,
        content="Red, green, and yellow grow the best.",
        display_content="Red, green, and yellow grow the best.",
        analysis_result={"Answered": True},
    )
    convos = Conversation.objects.filter(bot_integration=bi)
    msgs = Message.objects.filter(conversation__in=convos)
    assert msgs.count() == 2
    df = get_tabular_data(
        bi=bi,
        conversations=convos,
        messages=msgs,
        details="Answered Successfully",
        sort_by="Name",
    )
    assert df.shape[0] == 1
    assert "Name" in df.columns

    # invalid sort option should be ignored
    df = get_tabular_data(
        bi=bi,
        conversations=convos,
        messages=msgs,
        details="Answered Successfully",
        sort_by="Invalid",
    )
    assert df.shape[0] == 1
    assert "Name" in df.columns


def test_create_fb_test_bot_integration(transactional_db):
    # Create a new BotIntegration with WhatsApp as the platform
    user = AppUser.objects.create(is_anonymous=False)
    bot_integration = BotIntegration.objects.create(
        name="FB dev app test",
        created_by=user,
        workspace=Workspace.objects.create(
            name="myteam",
            created_by=user,
            is_personal=True,
        ),
        saved_run=None,
        user_language="en",
        show_feedback_buttons=True,
        platform=Platform.WHATSAPP,
        wa_phone_number="+1 (555) 017-9180",
        wa_phone_number_id="my_whatsapp_number_id",
    )
    bot_integration.full_clean()
