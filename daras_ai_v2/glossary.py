from daras_ai_v2.asr import google_translate_target_languages

from daras_ai_v2.doc_search_settings_widgets import document_uploader


def validate_glossary_document(document: str):
    """
    Throws AssertionError for the most common errors in a glossary document.
    I.e. the glossary must have at least 2 columns, top row must be language codes or "description" or "pos"
    """
    import langcodes
    from daras_ai_v2.vector_search import (
        download_content_bytes,
        bytes_to_str_df,
        doc_url_to_file_metadata,
    )

    metadata = doc_url_to_file_metadata(document)
    f_bytes, mime_type = download_content_bytes(
        f_url=document, mime_type=metadata.mime_type
    )
    df = bytes_to_str_df(f_name=metadata.name, f_bytes=f_bytes, mime_type=mime_type)

    if len(df.columns) < 2:
        raise AssertionError(
            f"Invalid glossary: must have at least 2 columns, but has {len(df.columns)}."
        )
    for col in df.columns:
        if col not in ["description", "pos"]:
            try:
                langcodes.Language.get(col).language
            except langcodes.LanguageTagError:
                raise AssertionError(
                    f'Invalid glossary: column header "{col}" is not a valid language code.'
                )


def glossary_input(
    label: str = "##### Glossary",
    key: str = "glossary_document",
) -> str:
    return document_uploader(
        label=label,
        key=key,
        accept=[".csv", ".xlsx", ".xls", ".gsheet", ".ods", ".tsv"],
        accept_multiple_files=False,
    )  # type: ignore


def create_glossary(
    *,
    language_codes: list[str],
    input_uri: str,
    project_id: str,
    location: str,
    glossary_name: str,
    timeout: int = 180,
) -> "translate.Glossary":
    """
    From https://cloud.google.com/translate/docs/advanced/glossary#equivalent_term_sets_glossary

    Create a equivalent term sets glossary. Glossary can be words or
    short phrases (usually fewer than five words).
    https://cloud.google.com/translate/docs/advanced/glossary#format-glossary
    """
    from google.cloud import translate_v3 as translate
    from google.api_core.exceptions import AlreadyExists

    client = translate.TranslationServiceClient()

    name = client.glossary_path(project_id, location, glossary_name)
    language_codes_set = translate.types.Glossary.LanguageCodesSet(
        language_codes=language_codes
    )

    gcs_source = translate.types.GcsSource(input_uri=input_uri)
    input_config = translate.types.GlossaryInputConfig(gcs_source=gcs_source)
    glossary = translate.types.Glossary(
        name=name, language_codes_set=language_codes_set, input_config=input_config
    )

    parent = f"projects/{project_id}/locations/{location}"
    try:
        operation = client.create_glossary(parent=parent, glossary=glossary)
        operation.result(timeout)
        print("Glossary created:", name)
    except AlreadyExists:
        pass


def delete_glossary(
    *,
    project_id: str,
    glossary_name: str,
    location: str,
    timeout: int = 180,
) -> "translate.Glossary":
    """
    From https://cloud.google.com/translate/docs/advanced/glossary#delete-glossary

    Delete a specific glossary based on the glossary ID.

    Args:
        project_id: The ID of the GCP project that owns the glossary.
        glossary_name: The name of the glossary to delete.
        location: The location of the glossary.
        timeout: The timeout for this request.

    Returns:
        The glossary that was deleted.
    """

    from google.cloud import translate_v3 as translate
    from google.api_core.exceptions import NotFound

    client = translate.TranslationServiceClient()
    name = client.glossary_path(project_id, location, glossary_name)
    try:
        operation = client.delete_glossary(name=name)
        operation.result(timeout)
        print("Glossary deleted:", name)
    except NotFound:
        pass


def get_langcodes_from_df(df: "pd.DataFrame") -> list[str]:
    import langcodes

    supported = {
        langcodes.Language.get(code).language
        for code in google_translate_target_languages()
    }
    ret = []
    for col in df.columns:
        try:
            lang = langcodes.Language.get(col).language
            if lang in supported:
                ret.append(col)
        except langcodes.LanguageTagError:
            pass
    return ret
