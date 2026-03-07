import logging

from bots.web_bot_adapter import WebBotAdapter
from bots.webex_bot_adapter.webex_ui_methods import WebexUIMethods

logger = logging.getLogger(__name__)


class WebexBotAdapter(WebBotAdapter, WebexUIMethods):
    def get_chromedriver_payload_file_name(self):
        return "webex_bot_adapter/webex_chromedriver_payload.js"

    def get_websocket_port(self):
        return 8877

    def is_sent_video_still_playing(self):
        return False

    def send_video(self, video_url):
        logger.info(f"send_video called with video_url = {video_url}. This is not supported for Webex")
        return

    def send_chat_message(self, text):
        logger.info(f"send_chat_message called with text={text}. This is not supported for Webex yet")
        return

    def get_staged_bot_join_delay_seconds(self):
        return 8

    def subclass_specific_after_bot_joined_meeting(self):
        self.after_bot_can_record_meeting()
