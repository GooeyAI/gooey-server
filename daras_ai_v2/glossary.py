import gooey_ui as gui
from daras_ai_v2.asr import google_translate_languages


def glossary_input(
    label="##### Glossary\nUpload a google sheet, csv, or xlsx file.",
    key="glossary_document",
):
    from daras_ai_v2.doc_search_settings_widgets import document_uploader

    glossary_url = document_uploader(
        label=label,
        key=key,
        accept=[".csv", ".xlsx", ".xls", ".gsheet", ".ods", ".tsv"],
        accept_multiple_files=False,
    )
    gui.caption(
        f"If not specified or invalid, no glossary will be used. Read about the expected format [here](https://docs.google.com/document/d/1TwzAvFmFYekloRKql2PXNPIyqCbsHRL8ZtnWkzAYrh8/edit?usp=sharing)."
    )
    return glossary_url


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
        langcodes.Language.get(code).language for code in google_translate_languages()
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
