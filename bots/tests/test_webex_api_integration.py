from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import Organization
from bots.models import ApiKey, Project


class TestWebexApiIntegration(TestCase):
    def setUp(self):
        organization = Organization.objects.create(name="Test Organization")
        self.project = Project.objects.create(name="Test Project", organization=organization)
        _, self.api_key = ApiKey.create(project=self.project, name="webex-api-key")
        self.client = APIClient()

    @patch("bots.bots_api_views.launch_bot")
    def test_create_webex_bot_with_api(self, mock_launch_bot):
        response = self.client.post(
            "/api/v1/bots",
            data={
                "meeting_url": "https://acme.webex.com/join/123456789?trackingId=abc",
                "bot_name": "Webex API Bot",
            },
            format="json",
            HTTP_AUTHORIZATION=f"Token {self.api_key}",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["state"], "joining")
        self.assertEqual(response.data["meeting_url"], "https://acme.webex.com/j/123456789?launchApp=false")
        self.assertEqual(response.data["transcription_state"], "not_started")
        self.assertEqual(response.data["recording_state"], "not_started")
        mock_launch_bot.assert_called_once()
