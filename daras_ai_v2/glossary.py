import gooey_ui as st
from daras_ai_v2.redis_cache import redis_cache_decorator
from contextlib import contextmanager
from glossary_resources.models import GlossaryResource
from django.db.models import F
import requests
from time import sleep

DEFAULT_GLOSSARY_URL = "https://docs.google.com/spreadsheets/d/1IRHKcOC86oZXwMB0hR7eej7YVg5kUHpriZymwYQcQX4/edit?usp=sharing"  # only viewing access
PROJECT_ID = "dara-c1b52"  # GCP project id
LOCATION = "us-central1"  # data center location
BUCKET_NAME = "gooey-server-glossary"  # name of bucket
MAX_GLOSSARY_RESOURCES = 10_000  # https://cloud.google.com/translate/quotas


# ================================ Glossary UI ================================
def glossary_input(
    label="##### Glossary\nUpload a google sheet, csv, or xlsx file.",
    key="glossary_document",
):
    from daras_ai_v2.doc_search_settings_widgets import document_uploader

    st.session_state.setdefault(key, DEFAULT_GLOSSARY_URL)
    glossary_url = document_uploader(
        label=label,
        key=key,
        accept=[".csv", ".xlsx", ".xls", ".gsheet", ".ods", ".tsv"],
        accept_multiple_files=False,
    )
    st.caption(
        f"If not specified or invalid, no glossary will be used. Read about the expected format [here](https://docs.google.com/document/d/1TwzAvFmFYekloRKql2PXNPIyqCbsHRL8ZtnWkzAYrh8/edit?usp=sharing)."
    )
    return glossary_url


# ================================ Glossary Logic ================================
@contextmanager
def glossary_resource(f_url: str = DEFAULT_GLOSSARY_URL, max_tries=3):
    """
    Obtains a glossary resource for use in translation requests.
    """
    from daras_ai_v2.vector_search import doc_url_to_metadata
    from google.api_core.exceptions import NotFound

    if not f_url:
        yield None
        return

    resource, created = GlossaryResource.objects.get_or_create(f_url=f_url)

    # make sure we don't exceed the max number of glossary resources allowed by GCP (we add a safety buffer of 100 for local development)
    if created and GlossaryResource.objects.count() > MAX_GLOSSARY_RESOURCES - 100:
        for gloss in GlossaryResource.objects.order_by("useage_count", "last_updated")[
            :10
        ]:
            try:
                _delete_glossary(glossary_name=gloss.get_clean_name())
            except NotFound:
                pass  # glossary already deleted, let's delete the model and move on
            finally:
                gloss.delete()

    doc_meta = doc_url_to_metadata(f_url)
    # create glossary if it doesn't exist, update if it has changed
    _update_glossary(f_url, doc_meta, glossary_name=resource.get_clean_name())
    path = _get_glossary(glossary_name=resource.get_clean_name())

    try:
        yield path
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 400 and e.response.json().get("error", {}).get(
            "message", ""
        ).startswith("Invalid resource name"):
            sleep(1)
            yield glossary_resource(f_url, max_tries - 1)
        else:
            raise e
    finally:
        GlossaryResource.objects.filter(pk=resource.pk).update(
            useage_count=F("useage_count") + 1
        )


@redis_cache_decorator
def _update_glossary(
    f_url: str, doc_meta, glossary_name: str = "glossary"
) -> "pd.DataFrame":
    """Goes through the full process of uploading the glossary from the url"""
    from daras_ai_v2.vector_search import download_table_doc
    from google.api_core.exceptions import NotFound

    df = download_table_doc(f_url, doc_meta)

    _upload_glossary_to_bucket(df, glossary_name=glossary_name)
    # delete existing glossary
    try:
        _delete_glossary(glossary_name=glossary_name)
    except NotFound:
        pass  # glossary already deleted, moving on
    # create new glossary
    languages = [
        lan_code
        for lan_code in df.columns.tolist()
        if lan_code not in ["pos", "description"]
    ]  # "pos" and "description" are not languages but still allowed by the google spec in the glossary csv
    _create_glossary(languages, glossary_name=glossary_name)

    return df


def _get_glossary(glossary_name: str = "glossary"):
    """Get information about the glossary."""
    from google.cloud import translate_v3beta1

    client = translate_v3beta1.TranslationServiceClient()

    path = client.glossary_path(PROJECT_ID, LOCATION, glossary_name)

    response = client.get_glossary(name=path)
    print("Glossary name: {}".format(response.name))
    print("Entry count: {}".format(response.entry_count))
    print("Input URI: {}".format(response.input_config.gcs_source.input_uri))
    return path


def _upload_glossary_to_bucket(df, glossary_name: str = "glossary"):
    """Uploads a pandas DataFrame to the bucket."""
    # import gcloud storage
    from google.cloud import storage

    csv = df.to_csv(index=False)

    # initialize the storage client and give it the bucket and the blob name
    BLOB_NAME, _ = _parse_glossary_name(glossary_name)
    storage_client = storage.Client()
    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(BLOB_NAME)

    # upload the file to the bucket
    blob.upload_from_string(csv)


def _delete_glossary(timeout=180, glossary_name: str = "glossary"):
    """Delete the glossary resource so a new one can be created."""
    from google.cloud import translate_v3beta1

    client = translate_v3beta1.TranslationServiceClient()

    path = client.glossary_path(PROJECT_ID, LOCATION, glossary_name)

    operation = client.delete_glossary(name=path)
    result = operation.result(timeout)
    print("Deleted: {}".format(result.name))


def _create_glossary(languages, glossary_name: str = "glossary"):
    """Creates a GCP glossary resource."""
    from google.cloud import translate_v3beta1
    from google.api_core.exceptions import AlreadyExists

    # Instantiates a client
    client = translate_v3beta1.TranslationServiceClient()

    # Set glossary resource name
    _, GLOSSARY_URI = _parse_glossary_name(glossary_name)
    path = client.glossary_path(PROJECT_ID, LOCATION, glossary_name)

    # Set language codes
    language_codes_set = translate_v3beta1.Glossary.LanguageCodesSet(
        language_codes=languages
    )

    gcs_source = translate_v3beta1.GcsSource(input_uri=GLOSSARY_URI)

    input_config = translate_v3beta1.GlossaryInputConfig(gcs_source=gcs_source)

    # Set glossary resource information
    glossary = translate_v3beta1.Glossary(
        name=path, language_codes_set=language_codes_set, input_config=input_config
    )

    parent = f"projects/{PROJECT_ID}/locations/{LOCATION}"

    # Create glossary resource
    # Handle exception for case in which a glossary
    #  with glossary_name already exists
    try:
        operation = client.create_glossary(parent=parent, glossary=glossary)
        operation.result(timeout=90)
        print("Created glossary " + glossary_name + ".")
    except AlreadyExists:
        print(
            "The glossary "
            + glossary_name
            + " already exists. No new glossary was created."
        )


def _parse_glossary_name(glossary_name: str = "glossary"):
    """
    Parses the glossary name into the bucket name and blob name.
    Args:
        glossary_name: name of the glossary resource
    Returns:
        blob_name: name of the blob
        glossary_uri: uri of the glossary uploaded to Cloud Storage
    """
    blob_name = glossary_name + ".csv"
    glossary_uri = "gs://" + BUCKET_NAME + "/" + blob_name
    return blob_name, glossary_uri
