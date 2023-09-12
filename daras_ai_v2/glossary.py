import gooey_ui as st
from daras_ai_v2.redis_cache import redis_cache_decorator

DEFAULT_GLOSSARY_URL = "https://docs.google.com/spreadsheets/d/1IRHKcOC86oZXwMB0hR7eej7YVg5kUHpriZymwYQcQX4/edit?usp=sharing"  # only viewing access
PROJECT_ID = "dara-c1b52"  # GCP project id
GLOSSARY_NAME = "glossary"  # name you want to give this glossary resource
LOCATION = "us-central1"  # data center location
BUCKET_NAME = "gooey-server-glossary"  # name of bucket
BLOB_NAME = "glossary.csv"  # name of blob
GLOSSARY_URI = (
    "gs://" + BUCKET_NAME + "/" + BLOB_NAME
)  # the uri of the glossary uploaded to Cloud Storage


# ================================ Glossary UI ================================
def glossary_input(
    label="##### Glossary\nUpload a google sheet, csv, or xlsx file.",
    key="glossary_url",
):
    from daras_ai_v2.doc_search_settings_widgets import document_uploader

    glossary_url = document_uploader(
        label=label,
        key=key,
        accept=["csv", "xlsx", "xls", "gsheet", "ods", "tsv"],
        accept_multiple_files=False,
    )
    st.caption(
        f"If not specified or invalid, no glossary will be used. Read about the expected format [here](https://docs.google.com/document/d/1TwzAvFmFYekloRKql2PXNPIyqCbsHRL8ZtnWkzAYrh8/edit?usp=sharing)."
    )
    return glossary_url


# ================================ Glossary Logic ================================
def _update_or_create_glossary(f_url: str) -> tuple[str, "pd.DataFrame"]:
    """
    Update or create a glossary resource
    Args:
        f_url: url of the glossary file
    Returns:
        name: path to the glossary resource
        df: pandas DataFrame of the glossary
    """
    from daras_ai_v2.vector_search import doc_url_to_metadata

    print("Updating/Creating glossary...")
    f_url = f_url or DEFAULT_GLOSSARY_URL
    doc_meta = doc_url_to_metadata(f_url)
    df = _update_glossary(f_url, doc_meta)
    return _get_glossary(), df


@redis_cache_decorator
def _update_glossary(f_url: str, doc_meta) -> "pd.DataFrame":
    """Goes through the full process of uploading the glossary from the url"""
    from daras_ai_v2.vector_search import download_table_doc

    df = download_table_doc(f_url, doc_meta)

    _upload_glossary_to_bucket(df)
    # delete existing glossary
    try:
        _delete_glossary()
    except:
        pass
    # create new glossary
    languages = [
        lan_code
        for lan_code in df.columns.tolist()
        if lan_code not in ["pos", "description"]
    ]  # these are not languages
    _create_glossary(languages)

    return df


def _get_glossary():
    """Get information about the glossary."""
    from google.cloud import translate_v3beta1

    client = translate_v3beta1.TranslationServiceClient()

    name = client.glossary_path(PROJECT_ID, LOCATION, GLOSSARY_NAME)

    response = client.get_glossary(name=name)
    print("Glossary name: {}".format(response.name))
    print("Entry count: {}".format(response.entry_count))
    print("Input URI: {}".format(response.input_config.gcs_source.input_uri))
    return name


def _upload_glossary_to_bucket(df):
    """Uploads a pandas DataFrame to the bucket."""
    # import gcloud storage
    from google.cloud import storage

    csv = df.to_csv(index=False)

    # initialize the storage client and give it the bucket and the blob name
    storage_client = storage.Client()
    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(BLOB_NAME)

    # upload the file to the bucket
    blob.upload_from_string(csv)


def _delete_glossary(timeout=180):
    """Delete the glossary resource so a new one can be created."""
    from google.cloud import translate_v3beta1

    client = translate_v3beta1.TranslationServiceClient()

    name = client.glossary_path(PROJECT_ID, LOCATION, GLOSSARY_NAME)

    operation = client.delete_glossary(name=name)
    result = operation.result(timeout)
    print("Deleted: {}".format(result.name))


def _create_glossary(languages):
    """Creates a GCP glossary resource."""
    from google.cloud import translate_v3beta1
    from google.api_core.exceptions import AlreadyExists

    # Instantiates a client
    client = translate_v3beta1.TranslationServiceClient()

    # Set glossary resource name
    name = client.glossary_path(PROJECT_ID, LOCATION, GLOSSARY_NAME)

    # Set language codes
    language_codes_set = translate_v3beta1.Glossary.LanguageCodesSet(
        language_codes=languages
    )

    gcs_source = translate_v3beta1.GcsSource(input_uri=GLOSSARY_URI)

    input_config = translate_v3beta1.GlossaryInputConfig(gcs_source=gcs_source)

    # Set glossary resource information
    glossary = translate_v3beta1.Glossary(
        name=name, language_codes_set=language_codes_set, input_config=input_config
    )

    parent = f"projects/{PROJECT_ID}/locations/{LOCATION}"

    # Create glossary resource
    # Handle exception for case in which a glossary
    #  with glossary_name already exists
    try:
        operation = client.create_glossary(parent=parent, glossary=glossary)
        operation.result(timeout=90)
        print("Created glossary " + GLOSSARY_NAME + ".")
    except AlreadyExists:
        print(
            "The glossary "
            + GLOSSARY_NAME
            + " already exists. No new glossary was created."
        )


# def _translate_text(
#     cls,
#     text: str,
#     source_language: str,
#     target_language: str,
#     enable_transliteration: bool = True,
#     glossary_url: str | None = None,
# ):
#     is_romanized, source_language = cls.parse_detected_language(source_language)
#     enable_transliteration = (
#         is_romanized
#         and enable_transliteration
#         and source_language in cls._can_transliterate
#     )
#     # prevent incorrect API calls
#     if source_language == target_language:
#         return text

#     config = {
#         "source_language_code": source_language,
#         "target_language_code": target_language,
#         "contents": text,
#         "mime_type": "text/plain",
#         "transliteration_config": {
#             "enable_transliteration": enable_transliteration
#         },
#     }

#     if glossary_url and not enable_transliteration:
#         # glossary does not work with transliteration
#         uri = _update_or_create_glossary(glossary_url)
#         config.update(
#             {
#                 "glossaryConfig": {
#                     "glossary": uri,
#                     "ignoreCase": True,
#                 }
#             }
#         )

#     authed_session, project = cls.get_google_auth_session()
#     res = authed_session.post(
#         f"{GOOGLE_V3_ENDPOINT}{project}/locations/{LOCATION}:translateText",
#         json.dumps(config),
#         headers={
#             "Content-Type": "application/json",
#         },
#     )
#     res.raise_for_status()
#     data = res.json()
#     result = data["glossaryTranslations"][0] if uri else data["translations"][0]

#     return result["translatedText"]
