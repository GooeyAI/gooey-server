from contextlib import nullcontext
from unittest.mock import Mock, patch

from starlette.background import BackgroundTasks

from bots import tasks
from daras_ai_v2.facebook_bots import WhatsappBot
from routers import facebook_api


def test_fb_webhook_batches_whatsapp_images():
    metadata = {"phone_number_id": "phone-number-id"}
    unsupported_message = {
        "from": "15550000000",
        "id": "unsupported-message-id",
        "timestamp": "1785488661",
        "type": "unsupported",
        "errors": [{"code": 131051}],
    }
    first_image = _image_message("first-message-id", "first-image-id")
    second_image = _image_message("second-message-id", "second-image-id")
    stored_entries = []
    scheduled_tasks = []
    redis_cache = Mock()
    redis_cache.rpush.side_effect = lambda _, entry: stored_entries.append(entry)
    redis_cache.lrange.side_effect = lambda *_: stored_entries.copy()
    redis_cache.delete.side_effect = lambda *_: stored_entries.clear()

    with (
        patch.object(tasks, "get_redis_cache", return_value=redis_cache),
        patch.object(tasks, "redis_lock", side_effect=lambda _: nullcontext()),
        patch.object(
            tasks.process_whatsapp_media_batch,
            "apply_async",
            side_effect=lambda **kwargs: scheduled_tasks.append(kwargs),
        ),
    ):
        first_background_tasks = BackgroundTasks()
        second_background_tasks = BackgroundTasks()
        first_response = facebook_api.fb_webhook(
            first_background_tasks,
            _wa_webhook([unsupported_message, first_image], metadata),
        )
        second_response = facebook_api.fb_webhook(
            second_background_tasks, _wa_webhook(second_image, metadata)
        )

        bot = Mock()
        with (
            patch.object(tasks, "WhatsappBot", return_value=bot) as whatsapp_bot,
            patch.object(tasks, "msg_handler") as msg_handler,
        ):
            for scheduled_task in scheduled_tasks:
                tasks.process_whatsapp_media_batch.run(**scheduled_task["kwargs"])

    assert first_response.body == b"OK"
    assert second_response.body == b"OK"
    assert not first_background_tasks.tasks
    assert not second_background_tasks.tasks
    assert [task["countdown"] for task in scheduled_tasks] == [3, 3, 3]
    whatsapp_bot.assert_called_once_with([first_image, second_image], metadata)
    msg_handler.assert_called_once_with(bot)
    assert not stored_entries


def test_whatsapp_bot_downloads_all_batched_images():
    bot = object.__new__(WhatsappBot)
    bot.input_messages = [
        _image_message("first-message-id", "first-image-id"),
        _image_message("second-message-id", "second-image-id"),
    ]
    bot._download_wa_media = Mock(
        side_effect=lambda media_id: f"https://example.com/{media_id}.jpg"
    )

    assert bot.get_input_images() == [
        "https://example.com/first-image-id.jpg",
        "https://example.com/second-image-id.jpg",
    ]


def _image_message(message_id: str, image_id: str) -> dict:
    return {
        "from": "15550000000",
        "id": message_id,
        "timestamp": "1785488661",
        "type": "image",
        "image": {"id": image_id},
    }


def _wa_webhook(message: dict | list[dict], metadata: dict) -> dict:
    messages = message if isinstance(message, list) else [message]
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": metadata,
                            "messages": messages,
                        }
                    }
                ]
            }
        ],
    }
