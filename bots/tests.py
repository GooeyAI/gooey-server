from django.test import TestCase
from .models import (
    Message,
    Conversation,
    BotIntegration,
    Platform,
    Workflow,
    ConvoState,
)
from django.db import transaction
from django.contrib import messages

CHATML_ROLE_USER = "user"
CHATML_ROLE_ASSISSTANT = "assistant"

# python manage.py test


class MessageModelTest(TestCase):

    """def test_create_and_save_message(self):

    # Create a new conversation
    conversation = Conversation.objects.create()

    # Create and save a new message
    message = Message(content="Hello, world!", conversation=conversation)
    message.save()

    # Retrieve all messages from the database
    all_messages = Message.objects.all()
    self.assertEqual(len(all_messages), 1)

    # Check that the message's content is correct
    only_message = all_messages[0]
    self.assertEqual(only_message, message)

    # Check the content
    self.assertEqual(only_message.content, "Hello, world!")"""


class BotIntegrationTest(TestCase):
    @classmethod
    def setUpClass(cls):
        super(BotIntegrationTest, cls).setUpClass()
        cls.keepdb = True

    @transaction.atomic
    def test_create_bot_integration_conversation_message(self):
        # Create a new BotIntegration with WhatsApp as the platform
        bot_integration = BotIntegration.objects.create(
            name="My Bot Integration",
            saved_run=None,
            billing_account_uid="fdnacsFSBQNKVW8z6tzhBLHKpAm1",  # digital green's account id
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
        self.assertEqual(Message.objects.count(), 2)
        self.assertEqual(message_u.conversation, conversation)
        self.assertEqual(message_u.role, CHATML_ROLE_USER)
        self.assertEqual(
            message_u.content, "What types of chilies can be grown in Mumbai?"
        )
        self.assertEqual(
            message_u.display_content, "What types of chilies can be grown in Mumbai?"
        )

        # Assert that the Bot Message was created successfully
        self.assertEqual(message_b.conversation, conversation)
        self.assertEqual(message_b.role, CHATML_ROLE_ASSISSTANT)
        self.assertEqual(message_b.content, "Red, green, and yellow grow the best.")
        self.assertEqual(
            message_b.display_content, "Red, green, and yellow grow the best."
        )
