import redis.asyncio as redis
from fastapi import APIRouter
from furl import furl
from starlette.responses import StreamingResponse

from daras_ai_v2 import settings

router = APIRouter()


@router.get("/key-events", include_in_schema=False)
async def key_events(topic: str):
    async def stream():
        r = redis.Redis()
        async with r.pubsub() as pubsub:
            await pubsub.subscribe(topic)
            async for _ in pubsub.listen():
                yield "data: pong\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


def get_key_events_url(redis_key: str) -> furl:
    return furl(
        settings.API_BASE_URL, query_params={"topic": redis_key}
    ) / router.url_path_for(key_events.__name__)
