import requests
from furl import furl
from loguru import logger
from vespa.application import ApplicationPackage
from vespa.package import (
    Schema,
    Document,
    Field,
    HNSW,
    RankProfile,
    FieldSet,
    Function,
    GlobalPhaseRanking,
)

from daras_ai_v2 import settings
from daras_ai_v2.exceptions import raise_for_status
from daras_ai_v2.vector_search import EMBEDDING_SIZE

EMBEDDING_TYPE = f"tensor<float>(x[{EMBEDDING_SIZE}])"

package = ApplicationPackage(
    "gooey",
    schema=[
        Schema(
            name=settings.VESPA_SCHEMA,
            document=Document(
                fields=[
                    Field(
                        name="id",
                        type="string",
                        indexing=["attribute", "summary"],
                        attribute=["fast-search"],
                        rank="filter",
                    ),
                    Field(
                        name="file_id",
                        type="string",
                        indexing=["attribute", "summary"],
                        attribute=["fast-search"],
                        rank="filter",
                    ),
                    Field(
                        name="embedding",
                        type=EMBEDDING_TYPE,
                        indexing=["index", "attribute"],
                        ann=HNSW(distance_metric="dotproduct"),
                    ),
                    Field(
                        name="created_at",
                        type="long",
                        indexing=["attribute"],
                        attribute=["fast-access"],
                    ),
                    Field(
                        name="title",
                        type="string",
                        indexing=["index", "summary"],
                        index="enable-bm25",
                    ),
                    Field(
                        name="snippet",
                        type="string",
                        indexing=["index", "summary"],
                        index="enable-bm25",
                    ),
                ]
            ),
            fieldsets=[FieldSet(name="default", fields=["title", "snippet"])],
            rank_profiles=[
                RankProfile(
                    name="bm25",
                    first_phase="bm25(title) + bm25(snippet)",
                ),
                RankProfile(
                    name="semantic",
                    inputs=[("query(queryEmbedding)", EMBEDDING_TYPE)],
                    first_phase="closeness(field, embedding)",
                ),
                RankProfile(
                    name="fusion",
                    inputs=[
                        ("query(queryEmbedding)", EMBEDDING_TYPE),
                        ("query(semanticWeight)", "double"),
                    ],
                    functions=[
                        Function(
                            name="bm25sum",
                            expression="bm25(title) + bm25(snippet)",
                        ),
                    ],
                    first_phase="bm25sum",
                    global_phase=GlobalPhaseRanking(
                        expression="reciprocal_rank(bm25sum) * (1 - query(semanticWeight)) + reciprocal_rank(closeness(field, embedding)) * query(semanticWeight)",
                        rerank_count=1000,
                    ),
                ),
            ],
        )
    ],
)


def run():
    r = requests.post(
        str(
            furl(settings.VESPA_CONFIG_SERVER_URL)
            / "application/v2/tenant/default/prepareandactivate"
        ),
        data=package.to_zip(),
        headers={"Content-Type": "application/zip"},
    )
    raise_for_status(r)
    logger.debug(r.text)
