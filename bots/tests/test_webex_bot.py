import os
import threading
import time
from unittest.mock import MagicMock, patch

from django.db import connection
from django.test import TransactionTestCase

from bots.bot_controller.bot_controller import BotController
from bots.models import (
    Bot,
    BotEventManager,
    BotEventTypes,
    BotStates,
    Organization,
    Project,
    Recording,
    RecordingStates,
    RecordingTypes,
    TranscriptionProviders,
    TranscriptionTypes,
)
from bots.tests.mock_data import create_mock_file_uploader


def create_mock_webex_driver():
    mock_driver = MagicMock()

    def execute_script_side_effect(script, *args, **kwargs):
        if script == "return performance.timeOrigin;":
            return 12345
        return None

    mock_driver.execute_script.side_effect = execute_script_side_effect
    return mock_driver


class TestWebexBot(TransactionTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        os.environ["SWIFT_CONTAINER_MEETS"] = "test-bucket"
        os.environ["CHARGE_CREDITS_FOR_BOTS"] = "false"
        os.environ["WEBEX_MOCK_JOIN_FLOW"] = "true"

    def setUp(self):
        self.organization = Organization.objects.create(name="Test Org")
        self.project = Project.objects.create(name="Test Project", organization=self.organization)

        self.bot = Bot.objects.create(
            project=self.project,
            name="Test Webex Bot",
            meeting_url="https://acme.webex.com/j/123456789",
            state=BotStates.READY,
        )

        self.recording = Recording.objects.create(
            bot=self.bot,
            recording_type=RecordingTypes.AUDIO_AND_VIDEO,
            transcription_type=TranscriptionTypes.NON_REALTIME,
            transcription_provider=TranscriptionProviders.DEEPGRAM,
            is_default_recording=True,
        )

        # Transition from READY -> JOINING
        BotEventManager.create_event(self.bot, BotEventTypes.JOIN_REQUESTED)

        # Create a non-empty recording file so upload path can be validated.
        self.recording_file_path = f"/tmp/{self.recording.object_id}.mp4"
        with open(self.recording_file_path, "wb") as recording_file:
            recording_file.write(b"webex-test-recording")

    @patch("bots.models.Bot.create_debug_recording", return_value=False)
    @patch("bots.web_bot_adapter.web_bot_adapter.Display")
    @patch("bots.web_bot_adapter.web_bot_adapter.webdriver.Chrome")
    @patch("bots.bot_controller.bot_controller.FileUploader")
    @patch("bots.bot_controller.bot_controller.ScreenAndAudioRecorder")
    def test_webex_bot_can_join_and_upload_recording(
        self,
        MockScreenRecorder,
        MockFileUploader,
        MockChromeDriver,
        MockDisplay,
        _mock_create_debug_recording,
    ):
        mock_uploader = create_mock_file_uploader()
        mock_uploader.upload_success = True
        MockFileUploader.return_value = mock_uploader

        mock_driver = create_mock_webex_driver()
        MockChromeDriver.return_value = mock_driver

        mock_display = MagicMock()
        MockDisplay.return_value = mock_display
        MockScreenRecorder.return_value = MagicMock()

        controller = BotController(self.bot.id)

        bot_thread = threading.Thread(target=controller.run)
        bot_thread.daemon = True
        bot_thread.start()

        def simulate_auto_leave():
            if not self.wait_for_adapter_ready(controller, timeout=15):
                raise Exception("Controller adapter not ready within timeout")

            # Trigger auto-leave quickly after join.
            controller.adapter.only_one_participant_in_meeting_at = time.time() - 100000
            time.sleep(4)
            connection.close()

        threading.Timer(2, simulate_auto_leave).start()
        bot_thread.join(timeout=15)

        self.bot.refresh_from_db()
        self.recording.refresh_from_db()

        self.assertEqual(self.bot.state, BotStates.ENDED)
        self.assertEqual(self.recording.state, RecordingStates.COMPLETE)
        mock_uploader.upload_file.assert_called_once()
        mock_uploader.wait_for_upload.assert_called_once()
        mock_uploader.delete_file.assert_called_once()

        controller.cleanup()
        bot_thread.join(timeout=5)
        connection.close()

    def wait_for_adapter_ready(self, controller, timeout=10):
        start_time = time.time()
        while time.time() - start_time < timeout:
            if hasattr(controller, "adapter") and controller.adapter is not None:
                return True
            time.sleep(0.1)
        return False
