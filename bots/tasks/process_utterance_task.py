import logging

import requests
from celery import shared_task

logger = logging.getLogger(__name__)

from bots.models import RecordingManager, TranscriptionFailureReasons, TranscriptionProviders, Utterance, WebhookTriggerTypes
from bots.webhook_payloads import utterance_webhook_payload
from bots.webhook_utils import trigger_webhook


def is_retryable_failure(failure_data):
    return failure_data.get("reason") in [
        TranscriptionFailureReasons.AUDIO_UPLOAD_FAILED,
        TranscriptionFailureReasons.TRANSCRIPTION_REQUEST_FAILED,
        TranscriptionFailureReasons.TIMED_OUT,
        TranscriptionFailureReasons.RATE_LIMIT_EXCEEDED,
        TranscriptionFailureReasons.INTERNAL_ERROR,
    ]


def get_transcription(utterance):
    try:
        if utterance.transcription_provider == TranscriptionProviders.DEEPGRAM:
            transcription, failure_data = get_transcription_via_deepgram(utterance)
        elif utterance.transcription_provider == TranscriptionProviders.GLADIA:
            transcription, failure_data = get_transcription_via_gladia(utterance)
        elif utterance.transcription_provider == TranscriptionProviders.OPENAI:
            transcription, failure_data = get_transcription_via_openai(utterance)
        elif utterance.transcription_provider == TranscriptionProviders.ASSEMBLY_AI:
            transcription, failure_data = get_transcription_via_assemblyai(utterance)
        elif utterance.transcription_provider == TranscriptionProviders.SARVAM:
            transcription, failure_data = get_transcription_via_sarvam(utterance)
        elif utterance.transcription_provider == TranscriptionProviders.ELEVENLABS:
            transcription, failure_data = get_transcription_via_elevenlabs(utterance)
        else:
            raise Exception(f"Unknown transcription provider: {utterance.transcription_provider}")

        return transcription, failure_data
    except Exception as e:
        return None, {"reason": TranscriptionFailureReasons.INTERNAL_ERROR, "error": str(e)}


@shared_task(
    bind=True,
    soft_time_limit=3600,
    autoretry_for=(Exception,),
    retry_backoff=True,  # Enable exponential backoff
    max_retries=6,
)
def process_utterance(self, utterance_id):
    utterance = Utterance.objects.get(id=utterance_id)
    logger.info(f"Processing utterance {utterance_id}")

    recording = utterance.recording

    if utterance.failure_data:
        logger.info(f"process_utterance was called for utterance {utterance_id} but it has already failed, skipping")
        return

    if utterance.transcription is None:
        utterance.transcription_attempt_count += 1

        transcription, failure_data = get_transcription(utterance)

        if failure_data:
            if utterance.transcription_attempt_count < 5 and is_retryable_failure(failure_data):
                utterance.save()
                raise Exception(f"Retryable failure when transcribing utterance {utterance_id}: {failure_data}")
            else:
                # Keep the audio blob around if it fails
                utterance.failure_data = failure_data
                utterance.save()
                logger.info(f"Transcription failed for utterance {utterance_id}, failure data: {failure_data}")
                return

        # The direct audio_blob column on the utterance model is deprecated, but for backwards compatibility, we need to clear it if it exists
        if utterance.audio_blob:
            utterance.audio_blob = b""  # set the audio blob binary field to empty byte string

        # If the utterance has an associated audio chunk, clear the audio blob on the audio chunk.
        # If async transcription data is being saved, do NOT clear it, because we may use it later in an async transcription.
        if utterance.audio_chunk and not utterance.recording.bot.record_async_transcription_audio_chunks():
            utterance_audio_chunk = utterance.audio_chunk
            utterance_audio_chunk.audio_blob = b""
            utterance_audio_chunk.save()

        utterance.transcription = transcription
        utterance.save()

        logger.info(f"Transcription complete for utterance {utterance_id}")

        # Don't send webhook for empty transcript or an async transcription
        if utterance.transcription.get("transcript") and utterance.async_transcription is None:
            trigger_webhook(
                webhook_trigger_type=WebhookTriggerTypes.TRANSCRIPT_UPDATE,
                bot=recording.bot,
                payload=utterance_webhook_payload(utterance),
            )

    # If the utterance is for an async transcription, we don't need to do anything with the recording state.
    if utterance.async_transcription is not None:
        return

    # If the recording is in a terminal state and there are no more utterances to transcribe, set the recording's transcription state to complete
    if RecordingManager.is_terminal_state(utterance.recording.state) and Utterance.objects.filter(recording=utterance.recording, transcription__isnull=True).count() == 0:
        RecordingManager.set_recording_transcription_complete(utterance.recording)


def get_transcription_via_gladia(utterance):
    logger.error("Removed by Lia to stay lean.")

    return utterance, None


def get_transcription_via_deepgram(utterance):
    logger.error("Removed by Lia to stay lean.")

    return utterance, None

def get_transcription_via_openai(utterance):
    logger.error("Removed by Lia to stay lean.")

    return utterance, None

def get_transcription_via_assemblyai(utterance):
    logger.error("Removed by Lia to stay lean.")

    return utterance, None


def get_transcription_via_sarvam(utterance):
    logger.error("Removed by Lia to stay lean.")

    return utterance, None


def get_transcription_via_elevenlabs(utterance):
    logger.error("Removed by Lia to stay lean.")

    return utterance, None
