from django.test import TestCase

from bots.meeting_url_utils import meeting_type_from_url, normalize_meeting_url
from bots.models import MeetingTypes


class TestWebexMeetingUrlNormalization(TestCase):
    def test_webex_j_url_normalized_and_tracking_removed(self):
        meeting_type, normalized_url = normalize_meeting_url("https://acme.webex.com/j/123456789?trackingId=abc&utm_source=x")
        self.assertEqual(meeting_type, MeetingTypes.WEBEX)
        self.assertEqual(normalized_url, "https://acme.webex.com/j/123456789?launchApp=false")

    def test_webex_join_alias_url_normalized_to_j(self):
        meeting_type, normalized_url = normalize_meeting_url("https://acme.webex.com/join/987654321?pwd=secret")
        self.assertEqual(meeting_type, MeetingTypes.WEBEX)
        self.assertEqual(normalized_url, "https://acme.webex.com/j/987654321?pwd=secret&launchApp=false")

    def test_webex_personal_room_url_keeps_meet_path(self):
        meeting_type, normalized_url = normalize_meeting_url("https://acme.webex.com/meet/jane.doe")
        self.assertEqual(meeting_type, MeetingTypes.WEBEX)
        self.assertEqual(normalized_url, "https://acme.webex.com/meet/jane.doe?launchApp=false")

    def test_webex_collab_url_supported(self):
        meeting_type, normalized_url = normalize_meeting_url("https://acme.webex.com/webapp/collab?MTID=abc123")
        self.assertEqual(meeting_type, MeetingTypes.WEBEX)
        self.assertEqual(normalized_url, "https://acme.webex.com/webapp/collab?MTID=abc123&launchApp=false")

    def test_webex_instant_connect_url_supported(self):
        meeting_type, normalized_url = normalize_meeting_url("https://instant.webex.com/gen/v1/room?data=encrypted&utm_source=x")
        self.assertEqual(meeting_type, MeetingTypes.WEBEX)
        self.assertEqual(normalized_url, "https://instant.webex.com/gen/v1/room?data=encrypted")

    def test_meeting_type_from_url_webex(self):
        self.assertEqual(meeting_type_from_url("https://acme.webex.com/j/123456789"), MeetingTypes.WEBEX)
