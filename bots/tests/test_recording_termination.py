"""
Unit tests for RecordingManager.terminate_recording() method.
Tests the fix for properly handling recording status when a pod dies (FATAL_ERROR).
"""
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.test import TransactionTestCase
from django.test.utils import override_settings

from bots.models import (
    Bot,
    BotEventTypes,
    BotStates,
    Organization,
    Participant,
    Project,
    Recording,
    RecordingManager,
    RecordingStates,
    RecordingTranscriptionStates,
    RecordingTypes,
    Utterance,
)


def mock_file_field_delete_sets_name_to_none(instance, save=True):
    """Mock FieldFile.delete to simulate file deletion"""
    instance.name = None
    if save:
        instance.instance.save()


def mock_file_field_save(instance, name, content, save=True):
    """Mock FieldFile.save to simulate file save"""
    instance.name = name
    if save:
        instance.instance.save()


class TestRecordingTermination(TransactionTestCase):
    """Test cases for recording termination logic when a pod dies"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.settings_override = override_settings(SWIFT_CONTAINER_MEETS="test-bucket")
        cls.settings_override.enable()

    def setUp(self):
        """Set up test fixtures"""
        # Setup patches for file operations
        self.delete_patch = patch("django.db.models.fields.files.FieldFile.delete", autospec=True)
        self.save_patch = patch("django.db.models.fields.files.FieldFile.save", autospec=True)

        # Start patches
        self.delete_mock = self.delete_patch.start()
        self.save_mock = self.save_patch.start()

        # Set side effects
        self.delete_mock.side_effect = mock_file_field_delete_sets_name_to_none
        self.save_mock.side_effect = mock_file_field_save

        # Create test organization
        self.organization = Organization.objects.create(name="Test Org")

        # Create test project
        self.project = Project.objects.create(organization=self.organization, name="Test Project")

        # Create a test bot
        self.bot = Bot.objects.create(
            project=self.project,
            name="Test Bot",
            meeting_url="https://test.com/meeting",
            state=BotStates.JOINED_RECORDING,
        )

        # Create a test participant
        self.participant = Participant.objects.create(
            bot=self.bot, uuid="test-participant", full_name="Test Participant"
        )

    def tearDown(self):
        """Clean up patches"""
        self.save_patch.stop()
        self.delete_patch.stop()

    def test_terminate_recording_with_fatal_error_marks_recording_as_failed(self):
        """
        Test that when a FATAL_ERROR event is provided, the recording is marked as FAILED
        even if a file exists (partial write from crashed pod).
        """
        # Create a recording in IN_PROGRESS state with a file
        recording = Recording.objects.create(
            bot=self.bot,
            recording_type=RecordingTypes.AUDIO_AND_VIDEO,
            transcription_type=1,
            state=RecordingStates.IN_PROGRESS,
        )

        # Add a file to simulate partial write from crashed pod
        recording.file.save("partial_recording.mp4", ContentFile(b"partial content"))
        recording.refresh_from_db()

        # Verify file exists
        self.assertTrue(bool(recording.file))

        # Terminate recording with FATAL_ERROR event type
        RecordingManager.terminate_recording(recording, event_type=BotEventTypes.FATAL_ERROR)

        # Verify recording is marked as FAILED (not COMPLETE)
        recording.refresh_from_db()
        self.assertEqual(recording.state, RecordingStates.FAILED)

    def test_terminate_recording_without_event_type_uses_file_existence_logic(self):
        """
        Test that without event_type parameter, the original logic applies:
        if file exists, mark as COMPLETE; if no file, mark as FAILED.
        """
        # Create a recording in IN_PROGRESS state with a file
        recording = Recording.objects.create(
            bot=self.bot,
            recording_type=RecordingTypes.AUDIO_AND_VIDEO,
            transcription_type=1,
            state=RecordingStates.IN_PROGRESS,
        )

        # Add a file
        recording.file.save("complete_recording.mp4", ContentFile(b"complete content"))
        recording.refresh_from_db()

        # Terminate recording without event_type (original behavior)
        RecordingManager.terminate_recording(recording)

        # Verify recording is marked as COMPLETE (because file exists)
        recording.refresh_from_db()
        self.assertEqual(recording.state, RecordingStates.COMPLETE)

    def test_terminate_recording_without_file_marks_as_failed(self):
        """
        Test that recording without a file is marked as FAILED
        (unless recording type is NO_RECORDING).
        """
        # Create a recording in IN_PROGRESS state without a file
        recording = Recording.objects.create(
            bot=self.bot,
            recording_type=RecordingTypes.AUDIO_AND_VIDEO,
            transcription_type=1,
            state=RecordingStates.IN_PROGRESS,
        )

        # Don't add a file

        # Terminate recording
        RecordingManager.terminate_recording(recording)

        # Verify recording is marked as FAILED (no file and not NO_RECORDING type)
        recording.refresh_from_db()
        self.assertEqual(recording.state, RecordingStates.FAILED)

    def test_terminate_recording_no_recording_type_marked_complete(self):
        """
        Test that NO_RECORDING type recordings are marked as COMPLETE
        even without a file.
        """
        # Configure bot to have NO_RECORDING format
        self.bot.settings = {
            "recording_settings": {
                "format": "none"  # RecordingFormats.NONE
            }
        }
        self.bot.save()

        # Create a recording with NO_RECORDING type
        recording = Recording.objects.create(
            bot=self.bot,
            recording_type=RecordingTypes.NO_RECORDING,
            transcription_type=1,
            state=RecordingStates.IN_PROGRESS,
        )

        # Don't add a file

        # Terminate recording
        RecordingManager.terminate_recording(recording)

        # Verify recording is marked as COMPLETE (NO_RECORDING type doesn't need a file)
        recording.refresh_from_db()
        self.assertEqual(recording.state, RecordingStates.COMPLETE)

    def test_terminate_recording_paused_state_with_fatal_error(self):
        """
        Test that PAUSED recordings are also handled correctly with FATAL_ERROR.
        """
        # Create a paused recording with a file
        recording = Recording.objects.create(
            bot=self.bot,
            recording_type=RecordingTypes.AUDIO_AND_VIDEO,
            transcription_type=1,
            state=RecordingStates.PAUSED,
        )

        # Add a file
        recording.file.save("paused_recording.mp4", ContentFile(b"paused content"))
        recording.refresh_from_db()

        # Terminate recording with FATAL_ERROR
        RecordingManager.terminate_recording(recording, event_type=BotEventTypes.FATAL_ERROR)

        # Verify recording is marked as FAILED
        recording.refresh_from_db()
        self.assertEqual(recording.state, RecordingStates.FAILED)

    def test_terminate_recording_handles_transcription_state(self):
        """
        Test that transcription state is properly handled during termination.
        """
        # Create a recording with IN_PROGRESS transcription
        recording = Recording.objects.create(
            bot=self.bot,
            recording_type=RecordingTypes.AUDIO_AND_VIDEO,
            transcription_type=1,
            state=RecordingStates.IN_PROGRESS,
            transcription_state=RecordingTranscriptionStates.IN_PROGRESS,
        )

        # Add a file
        recording.file.save("recording_with_transcription.mp4", ContentFile(b"content"))
        recording.refresh_from_db()

        # Create an utterance that is still in progress (no transcription yet)
        Utterance.objects.create(
            recording=recording,
            participant=self.participant,
            audio_blob=b"audio data",
            timestamp_ms=1000,
            duration_ms=500,
        )

        # Terminate recording with FATAL_ERROR
        RecordingManager.terminate_recording(recording, event_type=BotEventTypes.FATAL_ERROR)

        # Verify recording state is FAILED
        recording.refresh_from_db()
        self.assertEqual(recording.state, RecordingStates.FAILED)

        # Verify transcription state is FAILED (has in-progress utterances)
        self.assertEqual(recording.transcription_state, RecordingTranscriptionStates.FAILED)

    def test_terminate_recording_fatal_error_vs_other_event_types(self):
        """
        Test that only FATAL_ERROR event type triggers the special handling.
        Other event types should use the normal file-existence logic.
        """
        # Create two recordings with files
        recording_fatal = Recording.objects.create(
            bot=self.bot,
            recording_type=RecordingTypes.AUDIO_AND_VIDEO,
            transcription_type=1,
            state=RecordingStates.IN_PROGRESS,
        )
        recording_fatal.file.save("recording_fatal.mp4", ContentFile(b"content"))
        recording_fatal.refresh_from_db()

        recording_normal = Recording.objects.create(
            bot=self.bot,
            recording_type=RecordingTypes.AUDIO_AND_VIDEO,
            transcription_type=1,
            state=RecordingStates.IN_PROGRESS,
        )
        recording_normal.file.save("recording_normal.mp4", ContentFile(b"content"))
        recording_normal.refresh_from_db()

        # Terminate with FATAL_ERROR
        RecordingManager.terminate_recording(recording_fatal, event_type=BotEventTypes.FATAL_ERROR)

        # Terminate with MEETING_ENDED (normal event)
        RecordingManager.terminate_recording(recording_normal, event_type=BotEventTypes.MEETING_ENDED)

        # Verify FATAL_ERROR -> FAILED
        recording_fatal.refresh_from_db()
        self.assertEqual(recording_fatal.state, RecordingStates.FAILED)

        # Verify MEETING_ENDED -> COMPLETE (because file exists)
        recording_normal.refresh_from_db()
        self.assertEqual(recording_normal.state, RecordingStates.COMPLETE)

    def test_terminate_recording_preserves_completed_at_timestamp(self):
        """
        Test that completed_at timestamp is set when recording is completed.
        """
        recording = Recording.objects.create(
            bot=self.bot,
            recording_type=RecordingTypes.AUDIO_AND_VIDEO,
            transcription_type=1,
            state=RecordingStates.IN_PROGRESS,
        )
        recording.file.save("recording.mp4", ContentFile(b"content"))
        recording.refresh_from_db()

        # Verify completed_at is None before termination
        self.assertIsNone(recording.completed_at)

        # Terminate recording normally (should mark as COMPLETE)
        RecordingManager.terminate_recording(recording)

        recording.refresh_from_db()

        # Verify completed_at is set
        self.assertIsNotNone(recording.completed_at)
        self.assertEqual(recording.state, RecordingStates.COMPLETE)
