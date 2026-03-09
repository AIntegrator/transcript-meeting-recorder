import json
import os
import tempfile
from unittest import TestCase
from unittest.mock import patch

from bots.web_bot_adapter.web_bot_adapter import WebBotAdapter


class DummyChromeOptions:
    def __init__(self):
        self.arguments = []

    def add_argument(self, value):
        self.arguments.append(value)


class TestWebBotAdapterPolicyBlocklist(TestCase):
    def setUp(self):
        self.adapter = WebBotAdapter.__new__(WebBotAdapter)

    def test_external_protocol_url_blocklist_patterns_include_default_webex_schemes(self):
        with patch.dict(
            os.environ,
            {
                "EXTERNAL_PROTOCOL_SCHEME_BLOCKLIST": "",
                "EXTERNAL_PROTOCOL_SCHEME_BLOCKLIST_EXTRA": "",
                "EXTERNAL_PROTOCOL_URL_BLOCKLIST_PATTERNS": "",
            },
            clear=False,
        ):
            patterns = self.adapter.external_protocol_url_blocklist_patterns()

        self.assertIn("webex://*", patterns)
        self.assertIn("cisco-spark://*", patterns)
        self.assertIn("wbxmtg://*", patterns)

    def test_install_external_protocol_blocklist_policies_writes_managed_and_test_policy_files(self):
        with tempfile.TemporaryDirectory() as managed_dir, tempfile.TemporaryDirectory() as temp_dir:
            policy_test_file = os.path.join(temp_dir, "chrome-enterprise-policy.json")
            options = DummyChromeOptions()

            with patch.dict(
                os.environ,
                {
                    "CHROME_MANAGED_POLICY_DIRECTORIES": managed_dir,
                    "CHROME_ENTERPRISE_POLICY_TEST_FILE": policy_test_file,
                    "EXTERNAL_PROTOCOL_SCHEME_BLOCKLIST": "webex,cisco-spark",
                    "EXTERNAL_PROTOCOL_SCHEME_BLOCKLIST_EXTRA": "",
                    "EXTERNAL_PROTOCOL_URL_BLOCKLIST_PATTERNS": "custom-proto://*",
                },
                clear=False,
            ):
                self.adapter.install_external_protocol_blocklist_policies(options)

            managed_policy_path = os.path.join(managed_dir, "external_protocol_blocklist.json")
            self.assertTrue(os.path.exists(managed_policy_path))
            self.assertTrue(os.path.exists(policy_test_file))
            self.assertIn(f"--enterprise-policy-test-file={policy_test_file}", options.arguments)

            with open(managed_policy_path, "r", encoding="utf-8") as managed_policy_file:
                managed_payload = json.load(managed_policy_file)

            self.assertEqual(
                managed_payload["URLBlocklist"],
                [
                    "webex://*",
                    "cisco-spark://*",
                    "custom-proto://*",
                ],
            )
