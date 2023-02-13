EXAMPLE_ID_QUERY_PARAM = "example_id"
RUN_ID_QUERY_PARAM = "run_id"
USER_ID_QUERY_PARAM = "uid"


def extract_query_params(query_params):
    example_id = query_params.get(EXAMPLE_ID_QUERY_PARAM)
    run_id = query_params.get(RUN_ID_QUERY_PARAM)
    uid = query_params.get(USER_ID_QUERY_PARAM)

    if isinstance(example_id, list):
        example_id = example_id[0]
    if isinstance(run_id, list):
        run_id = run_id[0]
    if isinstance(uid, list):
        uid = uid[0]

    return example_id, run_id, uid
