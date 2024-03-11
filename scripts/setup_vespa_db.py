import requests
from furl import furl
from vespa.application import ApplicationPackage
from vespa.deployment import VespaDocker
from vespa.package import (
    Schema,
    Document,
    Field,
    FieldSet,
    HNSW,
    RankProfile,
    Function,
    GlobalPhaseRanking,
    QueryTypeField,
)

from daras_ai_v2 import settings
from daras_ai_v2.exceptions import raise_for_status

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
                    Field(name="url", type="string", indexing=["attribute", "summary"]),
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
                    Field(
                        name="embedding",
                        type="tensor<float>(x[1536])",
                        indexing=["index", "attribute"],
                        ann=HNSW(distance_metric="dotproduct"),
                    ),
                    Field(
                        name="doc_tag",
                        type="string",
                        indexing=["index", "attribute", "summary"],
                    ),
                ]
            ),
            fieldsets=[FieldSet(name="default", fields=["title", "snippet"])],
            rank_profiles=[
                RankProfile(
                    name="bm25",
                    inputs=[
                        ("query(q)", "tensor<float>(x[1536])"),
                    ],
                    functions=[
                        Function(
                            name="bm25sum", expression="bm25(title) + bm25(snippet)"
                        )
                    ],
                    first_phase="bm25sum",
                ),
                RankProfile(
                    name="semantic",
                    inputs=[
                        ("query(q)", "tensor<float>(x[1536])"),
                    ],
                    first_phase="closeness(field, embedding)",
                ),
                RankProfile(
                    name="fusion",
                    inherits="bm25",
                    inputs=[
                        ("query(q)", "tensor<float>(x[1536])"),
                        ("query(semanticWeight)", "float"),
                    ],
                    first_phase="closeness(field, embedding)",
                    global_phase=GlobalPhaseRanking(
                        expression="""
                        if (closeness(field, embedding)>0.6,
                            reciprocal_rank(bm25sum) * (1 - query(semanticWeight)) +
                            reciprocal_rank(closeness(field, embedding)) * query(semanticWeight),
                            0)
                    """,
                        rerank_count=1000,
                    ),
                ),
                RankProfile(
                    name="fusion2",  # with bm25 first
                    inherits="bm25",
                    inputs=[
                        ("query(q)", "tensor<float>(x[1536])"),
                        ("query(semanticWeight)", "float"),
                    ],
                    first_phase="closeness(field, embedding)",
                    global_phase=GlobalPhaseRanking(
                        expression="""
                        if (bm25sum>0.6,
                            reciprocal_rank(bm25sum) * (1 - query(semanticWeight)) +
                            reciprocal_rank(closeness(field, embedding)) * query(semanticWeight),
                            0)
                    """,
                        rerank_count=1000,
                    ),
                ),
            ],
        )
    ],
)
package.query_profile_type.add_fields(
    QueryTypeField(
        name="ranking.features.query(q)",
        type="tensor<float>(x[1536])",
    ),
)


def run():
    if settings.DEBUG:
        vespa_docker = VespaDocker(port=8085)
        vespa_docker.deploy(
            package,
            debug=settings.DEBUG,
        )
    else:
        r = requests.post(
            str(
                furl(settings.VESPA_CONFIG_SERVER_URL)
                / "application/v2/tenant/default/prepareandactivate"
            ),
            files={"applicationZipFile": package.to_zip()},
            headers={"Content-Type": "application/zip"},
        )
        raise_for_status(r)
