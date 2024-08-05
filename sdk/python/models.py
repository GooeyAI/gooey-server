import typing
from pydantic import BaseModel, Field
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname((os.path.abspath(__file__))))))
from daras_ai_v2.asr import AsrModels, TranslationModels
from daras_ai_v2.embedding_model import EmbeddingModels
from daras_ai_v2.functions import LLMTools
from daras_ai_v2.language_model import ConversationEntry, LargeLanguageModels
from daras_ai_v2.lipsync_api import LipsyncModel, LipsyncSettings, SadTalkerSettings
from daras_ai_v2.pydantic_validation import FieldHttpUrl
from daras_ai_v2.search_ref import CitationStyles, SearchReference
from daras_ai_v2.text_to_speech_settings_widgets import OPENAI_TTS_MODELS_T, OPENAI_TTS_VOICES_T, TextToSpeechProviders

class NotGiven(BaseModel):
  pass

class LipsyncSettings(BaseModel):
    input_face: FieldHttpUrl | NotGiven = None

    # wav2lip
    face_padding_top: int | NotGiven = None
    face_padding_bottom: int | NotGiven = None
    face_padding_left: int | NotGiven = None
    face_padding_right: int | NotGiven = None

    sadtalker_settings: SadTalkerSettings | NotGiven = None
    
class MetaInfoResponse(BaseModel):
    id: str
    url: str
    created_at: str

class VideoBotsRequest(LipsyncSettings, BaseModel):
  bot_script: str | None | NotGiven

  input_prompt: str
  input_audio: str | None | NotGiven 
  input_images: list[FieldHttpUrl] | None | NotGiven
  input_documents: list[FieldHttpUrl] | None | NotGiven
  doc_extract_url: str | None | NotGiven = Field(
      title="📚 Document Extract Workflow",
      description="Select a workflow to extract text from documents and images.",
  )

  # conversation history/context
  messages: list[ConversationEntry] | None | NotGiven

  # tts settings
  tts_provider: (
      typing.Literal[tuple(e.name for e in TextToSpeechProviders)] | None | NotGiven
  )
  uberduck_voice_name: str | None | NotGiven
  uberduck_speaking_rate: float | None | NotGiven
  google_voice_name: str | None | NotGiven
  google_speaking_rate: float | None | NotGiven
  google_pitch: float | None | NotGiven
  bark_history_prompt: str | None | NotGiven
  elevenlabs_voice_name: str | None | NotGiven
  elevenlabs_api_key: str | None | NotGiven
  elevenlabs_voice_id: str | None | NotGiven
  elevenlabs_model: str | None | NotGiven
  elevenlabs_stability: float | None | NotGiven
  elevenlabs_similarity_boost: float | None | NotGiven
  azure_voice_name: str | None | NotGiven
  openai_voice_name: OPENAI_TTS_VOICES_T | None | NotGiven
  openai_tts_model: OPENAI_TTS_MODELS_T | None | NotGiven

  # llm settings
  selected_model: (
      typing.Literal[tuple(e.name for e in LargeLanguageModels)] | None | NotGiven
  )
  document_model: str | None | NotGiven = Field(
      title="🩻 Photo / Document Intelligence",
      description="When your copilot users upload a photo or pdf, what kind of document are they mostly likely to upload? "
      "(via [Azure](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/how-to-guides/use-sdk-rest-api?view=doc-intel-3.1.0&tabs=linux&pivots=programming-language-rest-api))",
  )
  avoid_repetition: bool | None | NotGiven
  num_outputs: int | None | NotGiven
  quality: float | None | NotGiven
  max_tokens: int | None | NotGiven
  sampling_temperature: float | None | NotGiven

  # doc search
  task_instructions: str | None | NotGiven
  query_instructions: str | None | NotGiven
  keyword_instructions: str | None | NotGiven
  documents: list[FieldHttpUrl] | None | NotGiven
  max_references: int | None | NotGiven
  max_context_words: int | None | NotGiven
  scroll_jump: int | None | NotGiven

  embedding_model: typing.Literal[tuple(e.name for e in EmbeddingModels)] | None | NotGiven
  dense_weight: float | None | NotGiven

  citation_style: typing.Literal[tuple(e.name for e in CitationStyles)] | None | NotGiven
  use_url_shortener: bool | None | NotGiven

  asr_model: typing.Literal[tuple(e.name for e in AsrModels)] | None | NotGiven = Field(
      title="Speech-to-Text Provider",
      description="Choose a model to transcribe incoming audio messages to text.",
  )
  asr_language: str | None | NotGiven = Field(
      title="Spoken Language",
      description="Choose a language to transcribe incoming audio messages to text.",
  )

  translation_model: (
      typing.Literal[tuple(e.name for e in TranslationModels)] | None | NotGiven
  )
  user_language: str | None | NotGiven = Field(
      title="User Language",
      description="Choose a language to translate incoming text & audio messages to English and responses back to your selected language. Useful for low-resource languages.",
  )
  # llm_language: str | None = "en" <-- implicit since this is hardcoded everywhere in the code base (from facebook and bots to slack and copilot etc.)
  input_glossary_document: FieldHttpUrl | None | NotGiven = Field(
      title="Input Glossary",
      description="""
Translation Glossary for User Langauge -> LLM Language (English)
      """,
  )
  output_glossary_document: FieldHttpUrl | None | NotGiven = Field(
      title="Output Glossary",
      description="""
Translation Glossary for LLM Language (English) -> User Langauge
      """,
  )

  lipsync_model: typing.Literal[tuple(e.name for e in LipsyncModel)] | NotGiven = (
      LipsyncModel.Wav2Lip.name
  )

  variables: dict[str, typing.Any] | None | NotGiven

  tools: list[LLMTools] | None | NotGiven = Field(
      title="🛠️ Tools",
      description="Give your copilot superpowers by giving it access to tools. Powered by [Function calling](https://platform.openai.com/docs/guides/function-calling).",
  )

class VideoBotsResponse(BaseModel):
  final_prompt: str | list[ConversationEntry] = []

  output_text: list[str] = []
  output_audio: list[FieldHttpUrl] = []
  output_video: list[FieldHttpUrl] = []

  # intermediate text
  raw_input_text: str | None
  raw_tts_text: list[str] | None
  raw_output_text: list[str] | None

  # doc search
  references: list[SearchReference] | None
  final_search_query: str | None
  final_keyword_query: str | list[str] | None

  # function calls
  output_documents: list[FieldHttpUrl] | None
  reply_buttons: list | None

  finish_reason: list[str] | None