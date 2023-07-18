import typing
import json
from enum import Enum
from abc import ABC, abstractmethod

import gooey_ui as st
from daras_ai_v2.functional import map_parallel
from daras_ai_v2.redis_cache import redis_cache_decorator

DEFAULT_GLOSSARY_URL = "https://docs.google.com/spreadsheets/d/1IRHKcOC86oZXwMB0hR7eej7YVg5kUHpriZymwYQcQX4/edit?usp=sharing"  # only viewing access
GOOGLE_V3_ENDPOINT = "https://translate.googleapis.com/v3/projects/"


class Translator(ABC):
    # enum name - should be alphanumeric (no spaces or special characters)
    name: str = "Translator"
    # enum value and display name - can be anything
    value: str = "translator"
    description: str = "A translator"
    _can_transliterate: list[str] = {}

    @classmethod
    @abstractmethod
    def detect_languages(cls, texts: list[str]) -> list[str]:
        pass

    @classmethod
    def parse_detected_language(cls, language_code: str):
        is_romanized = language_code.endswith("-Latn")
        language_code = language_code.replace("-Latn", "")
        return is_romanized, language_code

    @classmethod
    @abstractmethod
    def supported_languages(cls) -> dict[str, str]:
        pass

    @classmethod
    def translate(
        cls,
        texts: list[str],
        target_language: str,
        source_language: str | None = None,
        enable_transliteration: bool = True,
        glossary_url: str | None = None,
    ) -> list[str]:
        # prevent incorrect API calls
        if source_language == target_language:
            return texts

        # detect languages and romanization information if not provided
        if not source_language:
            language_codes = cls.detect_languages(texts)
        elif not enable_transliteration:
            language_codes = [source_language] * len(texts)
        else:  # transliteration is enabled and we are provided a source language
            is_specified_as_romanized, _ = cls.parse_detected_language(source_language)
            if is_specified_as_romanized:
                language_codes = [source_language] * len(texts)
            else:  # check whether it is romanized
                language_codes = cls.detect_languages(texts)

        return map_parallel(
            lambda text, source: cls._translate_text(
                text, source, target_language, enable_transliteration, glossary_url
            ),
            texts,
            language_codes,
        )

    @classmethod
    @abstractmethod
    def _translate_text(
        cls,
        text: str,
        source_language: str,
        target_language: str,
        enable_transliteration: bool = True,
        glossary_url: str | None = None,
    ) -> str:
        pass

    @classmethod
    def language_selector(
        cls,
        label: str = "###### Translate To",
        key: str = "target_language",
        allow_none=True,
    ):
        languages = cls.supported_languages()
        TranslateUI.translate_language_selector(
            languages,
            label=label,
            key=key,
            allow_none=allow_none,
        )


# declared separately for caching since python support for caching classmethods is limited
@st.cache_data()
def _Google_supported_languages() -> dict[str, str]:
    from google.cloud import translate

    parent = f"projects/dara-c1b52/locations/global"
    client = translate.TranslationServiceClient()
    supported_languages = client.get_supported_languages(
        parent=parent, display_language_code="en"
    )
    return {
        lang.language_code: lang.display_name
        for lang in supported_languages.languages
        if lang.support_target
    }


class GoogleTranslate(Translator):
    name = "GoogleTranslate"
    value = "Google Translate"
    description = "We call the latest Google Translate API which leverages Google's neural machine translation models (https://en.wikipedia.org/wiki/Google_Neural_Machine_Translation)"
    _can_transliterate = {
        # "ar",
        # "bn",
        # "gu",
        "hi",
        # "ja",
        # "kn",
        # "ru",
        # "ta",
        # "te",
    }  # only enable transliteration for hindu since the glossary is more important in other languages
    _session = None

    @classmethod
    def get_google_auth_session(cls):
        """Gets a session with Google Cloud authentication which takes care of refreshing the token and adding it to request headers."""
        if cls._session is None:
            import google.auth
            from google.auth.transport.requests import AuthorizedSession

            creds, project = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
            cls._session = AuthorizedSession(credentials=creds), project

        return cls._session

    @classmethod
    def detect_languages(cls, texts: list[str]) -> list[str]:
        from google.cloud import translate_v2

        translate_client = translate_v2.Client()
        detections = translate_client.detect_language(texts)
        return [detection["language"] for detection in detections]

    @classmethod
    def supported_languages(cls) -> dict[str, str]:
        return _Google_supported_languages()

    @classmethod
    def _translate_text(
        cls,
        text: str,
        source_language: str,
        target_language: str,
        enable_transliteration: bool = True,
        glossary_url: str | None = None,
    ):
        is_romanized, source_language = cls.parse_detected_language(source_language)
        enable_transliteration = (
            is_romanized
            and enable_transliteration
            and source_language in cls._can_transliterate
        )
        # prevent incorrect API calls
        if source_language == target_language:
            return text

        config = {
            "source_language_code": source_language,
            "target_language_code": target_language,
            "contents": text,
            "mime_type": "text/plain",
            "transliteration_config": {
                "enable_transliteration": enable_transliteration
            },
        }

        if glossary_url and not enable_transliteration:
            # glossary does not work with transliteration
            uri = _update_or_create_glossary(glossary_url)
            config.update(
                {
                    "glossaryConfig": {
                        "glossary": uri,
                        "ignoreCase": True,
                    }
                }
            )

        authed_session, project = cls.get_google_auth_session()
        res = authed_session.post(
            f"{GOOGLE_V3_ENDPOINT}{project}/locations/global:translateText",
            json.dumps(config),
            headers={
                "Content-Type": "application/json",
            },
        )
        res.raise_for_status()
        data = res.json()
        result = data["translations"][0]

        return result["translatedText"]


# add new apis to this list:
_all_apis: list[Translator] = [GoogleTranslate]


@st.cache_data()
def _all_languages() -> dict[str, str]:
    dict = {}
    for api in _all_apis:
        dict.update(api.supported_languages())
    return dict


# Types that show up nicely in API docs
TRANSLATE_API_TYPE = typing.TypeVar(
    "TRANSLATE_API_TYPE", bound=typing.Literal[tuple(api.name for api in _all_apis)]
)
LANGUAGE_CODE_TYPE = typing.TypeVar(
    "LANGUAGE_CODE_TYPE",
    bound=typing.Literal[tuple(code for code, _ in _all_languages().items())],
)


class Translate:
    apis: dict[TRANSLATE_API_TYPE, Translator] = {api.name: api for api in _all_apis}
    APIs = APIs = Enum("APIs", {api.name: api.value for api in _all_apis})

    @classmethod
    def detect_languages(
        cls, texts: list[str], api: TRANSLATE_API_TYPE | None = None
    ) -> list[str]:
        return cls.apis.get(api, GoogleTranslate).detect_languages(texts)

    @classmethod
    def run(
        cls,
        texts: list[str],
        target_language: str,
        api: TRANSLATE_API_TYPE = None,
        source_language: str | None = None,
        enable_transliteration: bool = True,
        glossary_url: str | None = DEFAULT_GLOSSARY_URL,
    ) -> list[str]:
        translator = cls.apis.get(api, GoogleTranslate)
        return translator.translate(
            texts,
            target_language,
            source_language,
            enable_transliteration,
            glossary_url,
        )


class TranslateUI:
    @staticmethod
    def translate_api_selector(
        label="###### Translate API",
        key="translate_api",
        allow_none=True,
    ) -> Translator:
        options = list(Translate.apis.keys())
        if allow_none:
            options.insert(0, None)
            label += " (_optional_)"
        selected_api = st.selectbox(
            label=label,
            key=key,
            format_func=lambda k: Translate.apis.get(k).value
            if k and k in Translate.apis
            else "———",
            options=options,
        )
        translator = Translate.apis.get(selected_api)
        if translator:
            st.caption(translator.description)
        return translator

    @staticmethod
    def translate_language_selector(
        languages: dict[str, str] = None,
        label="###### Translate To",
        key="target_language",
        key_apiselect="translate_api",
        allow_none=True,
    ):
        if not languages:
            languages = Translate.apis.get(
                st.session_state.get(key_apiselect), GoogleTranslate
            ).supported_languages()
        options = list(languages.keys())
        if allow_none:
            options.insert(0, None)
            label += " (_optional_)"
        return st.selectbox(
            label=label,
            key=key,
            format_func=lambda k: languages[k] if k else "———",
            options=options,
        )

    @staticmethod
    def translate_glossary_input(
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


# ================================ Glossary ================================
# Below follows code for uploading a glossary to Google Cloud Translate.
# Using a glossary is a good approach if you don’t have enough data to train your own model
# when working with minority languages which Google still has a lot of room for improvement
# or when you are working with a domain specific topic.
PROJECT_ID = "dara-c1b52"  # GCP project id
GLOSSARY_NAME = "glossary"  # name you want to give this glossary resource
LOCATION = "us-central1"  # data center location
BUCKET_NAME = "gooey-server-glossary"  # name of bucket
BLOB_NAME = "glossary.csv"  # name of blob
GLOSSARY_URI = (
    "gs://" + BUCKET_NAME + "/" + BLOB_NAME
)  # the uri of the glossary uploaded to Cloud Storage


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
    _update_glossary(f_url, doc_meta)
    return _get_glossary()


@redis_cache_decorator
def _update_glossary(f_url: str, doc_meta) -> "pd.DataFrame":
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
    """Get information about a particular glossary."""
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
    """Delete a specific glossary based on the glossary ID."""
    from google.cloud import translate_v3beta1

    client = translate_v3beta1.TranslationServiceClient()

    name = client.glossary_path(PROJECT_ID, LOCATION, GLOSSARY_NAME)

    operation = client.delete_glossary(name=name)
    result = operation.result(timeout)
    print("Deleted: {}".format(result.name))


def _create_glossary(languages):
    """Creates a GCP glossary resource
    Assumes you've already uploaded a glossary to Cloud Storage bucket
    Args:
        languages: list of languages in the glossary
        project_id: GCP project id
        glossary_name: name you want to give this glossary resource
        glossary_uri: the uri of the glossary you uploaded to Cloud Storage
    """
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
