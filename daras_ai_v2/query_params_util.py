import typing


EXAMPLE_ID_QUERY_PARAM = "example_id"
RUN_ID_QUERY_PARAM = "run_id"
USER_ID_QUERY_PARAM = "uid"


def extract_query_params(
    query_params: typing.Mapping[str, str], default: str = ""
) -> tuple[str, str, str]:
    example_id = query_params.get(EXAMPLE_ID_QUERY_PARAM, default)
    run_id = query_params.get(RUN_ID_QUERY_PARAM, default)
    uid = query_params.get(USER_ID_QUERY_PARAM, default)

    return example_id, run_id, uid
