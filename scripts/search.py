import json
from pprint import pformat

from loguru import logger
from daras_ai_v2.vector_search import get_top_k_references, DocSearchRequest


def run(arg, documents):
    logger.info(f"Started {arg=} {documents=}")
    logger.info("Running...")
    iterator = get_top_k_references(
        DocSearchRequest.parse_obj(
            {
                "search_query": arg,
                "documents": json.loads(documents),
                "max_references": 10,
                "dense_weight": 0.0,  # bm25 only
            }
        )
    )
    while True:
        try:
            status = next(iterator)
        except StopIteration as e:
            refs = e.value
            break
        else:
            logger.info(f"[top_k] {status}")

    print(
        json.dumps(
            [
                dict(
                    url=ref["url"],
                    title=ref["title"],
                    # snippet=ref["snippet"],
                    score=ref["score"],
                )
                for ref in refs
            ],
            indent=2,
        )
    )
