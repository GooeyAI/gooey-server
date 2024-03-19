from daras_ai.image_input import gs_url_to_uri


def gcp_asr_v1(audio_url: str, language: str) -> str:
    from google.cloud import speech

    client = speech.SpeechClient()
    audio = speech.RecognitionAudio(uri=gs_url_to_uri(audio_url))
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=16000,
        audio_channel_count=1,
        language_code=language,
        model="default",
    )
    # Make the request
    operation = client.long_running_recognize(config=config, audio=audio)
    # Wait for operation to complete
    response = operation.result(timeout=600)
    print(response)
    return "\n\n".join(
        result.alternatives[0].transcript
        for result in response.results
        if result.alternatives
    )
