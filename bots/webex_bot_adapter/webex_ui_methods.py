import logging
import os
import time

from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from bots.web_bot_adapter.ui_methods import (
    UiCouldNotJoinMeetingWaitingRoomTimeoutException,
    UiCouldNotLocateElementException,
    UiLoginRequiredException,
    UiMeetingNotFoundException,
    UiRequestToJoinDeniedException,
    UiRetryableExpectedException,
)

logger = logging.getLogger(__name__)


class UiWebexBlockingUsException(UiRetryableExpectedException):
    def __init__(self, message, step=None, inner_exception=None):
        super().__init__(message, step, inner_exception)


class WebexUIMethods:
    def locate_element(self, step, condition, wait_time_seconds=60):
        try:
            return WebDriverWait(self.driver, wait_time_seconds).until(condition)
        except Exception as e:
            logger.info(f"Exception raised in locate_element for {step}")
            raise UiCouldNotLocateElementException(f"Exception raised in locate_element for {step}", step, e)

    def find_element_by_selector(self, selector_type, selector):
        try:
            return self.driver.find_element(selector_type, selector)
        except NoSuchElementException:
            return None
        except Exception:
            return None

    def click_element(self, element, step):
        try:
            element.click()
        except Exception as e:
            raise UiCouldNotLocateElementException("Could not click element", step, e)

    def click_optional_continue_in_browser(self):
        selectors = [
            (By.XPATH, "//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'join from your browser')]"),
            (By.XPATH, "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'join from your browser')]"),
            (By.XPATH, "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'continue in browser')]"),
        ]
        for selector_type, selector in selectors:
            element = self.find_element_by_selector(selector_type, selector)
            if element:
                logger.info("Clicking continue/join in browser entry point")
                self.click_element(element, "continue_in_browser")
                return

    def check_for_login_required(self, step):
        login_signals = [
            "//input[@name='username' or @name='email']",
            "//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'sign in to join')]",
        ]
        for signal in login_signals:
            if self.find_element_by_selector(By.XPATH, signal):
                raise UiLoginRequiredException("Login required to join this Webex meeting", step)

    def check_for_meeting_not_found(self, step):
        not_found_signals = [
            "//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'meeting not found')]",
            "//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'invalid meeting')]",
            "//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'expired')]",
        ]
        for signal in not_found_signals:
            if self.find_element_by_selector(By.XPATH, signal):
                raise UiMeetingNotFoundException("Webex meeting not found", step)

    def check_for_denied_join(self, step):
        denied_signals = [
            "//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'request to join was denied')]",
            "//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'host denied')]",
            "//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'unable to join')]",
        ]
        for signal in denied_signals:
            if self.find_element_by_selector(By.XPATH, signal):
                raise UiRequestToJoinDeniedException("Request to join Webex meeting denied", step)

    def check_for_platform_blocking(self, step):
        if self.find_element_by_selector(By.XPATH, "//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'something went wrong')]"):
            raise UiWebexBlockingUsException("Webex blocked the join flow temporarily", step)

    def fill_guest_details(self):
        name_input = self.locate_element(
            step="guest_name_input",
            condition=EC.presence_of_element_located(
                (
                    By.XPATH,
                    (
                        "//input[contains(translate(@aria-label, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'name') "
                        "or contains(translate(@placeholder, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'name')]"
                    ),
                )
            ),
            wait_time_seconds=20,
        )
        name_input.clear()
        name_input.send_keys(self.display_name)

        email = os.getenv("WEBEX_BOT_GUEST_EMAIL", "webex-bot@example.com")
        email_input = self.find_element_by_selector(
            By.XPATH,
            (
                "//input[contains(translate(@aria-label, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'email') "
                "or contains(translate(@placeholder, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'email')]"
            ),
        )
        if email_input:
            email_input.clear()
            email_input.send_keys(email)

    def turn_off_media_inputs(self):
        microphone_button = self.find_element_by_selector(
            By.XPATH,
            "//button[contains(translate(@aria-label, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'microphone') or contains(translate(@aria-label, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'mute')]",
        )
        if microphone_button:
            self.click_element(microphone_button, "turn_off_microphone")

        camera_button = self.find_element_by_selector(
            By.XPATH,
            "//button[contains(translate(@aria-label, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'camera') or contains(translate(@aria-label, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'video')]",
        )
        if camera_button:
            self.click_element(camera_button, "turn_off_camera")

    def click_join_as_guest(self):
        join_as_guest = self.locate_element(
            step="join_as_guest_button",
            condition=EC.presence_of_element_located(
                (
                    By.XPATH,
                    (
                        "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'join as guest')]"
                        "|//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'join as guest')]"
                    ),
                )
            ),
            wait_time_seconds=30,
        )
        self.click_element(join_as_guest, "join_as_guest_button")

    def click_join_meeting_button(self):
        join_button = self.locate_element(
            step="join_meeting_button",
            condition=EC.presence_of_element_located(
                (
                    By.XPATH,
                    (
                        "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'join meeting')]"
                        "|//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'join')]"
                    ),
                )
            ),
            wait_time_seconds=20,
        )
        self.click_element(join_button, "join_meeting_button")

    def wait_until_joined_or_timeout(self):
        waiting_room_timeout_started_at = time.time()
        while True:
            leave_button = self.find_element_by_selector(
                By.XPATH,
                (
                    "//button[contains(translate(@aria-label, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'leave')]"
                    "|//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'leave meeting')]"
                ),
            )
            if leave_button:
                return

            self.check_for_denied_join("wait_until_joined")
            self.check_for_meeting_not_found("wait_until_joined")
            self.check_for_login_required("wait_until_joined")
            self.check_for_platform_blocking("wait_until_joined")

            waiting_room_timeout_exceeded = time.time() - waiting_room_timeout_started_at > self.automatic_leave_configuration.waiting_room_timeout_seconds
            if waiting_room_timeout_exceeded:
                raise UiCouldNotJoinMeetingWaitingRoomTimeoutException("Waiting room timeout exceeded", "wait_until_joined")

            time.sleep(1)

    def attempt_to_join_meeting(self):
        # For credential-free demos in isolated environments.
        if os.getenv("WEBEX_MOCK_JOIN_FLOW", "false").lower() == "true":
            logger.info("WEBEX_MOCK_JOIN_FLOW=true: skipping UI flow and simulating successful join")
            self.driver.get("about:blank")
            self.ready_to_show_bot_image()
            return

        logger.info(f"Navigating to Webex meeting URL: {self.meeting_url}")
        self.driver.get(self.meeting_url)
        self.driver.execute_cdp_cmd(
            "Browser.grantPermissions",
            {
                "origin": self.meeting_url,
                "permissions": [
                    "geolocation",
                    "audioCapture",
                    "displayCapture",
                    "videoCapture",
                ],
            },
        )

        self.click_optional_continue_in_browser()
        self.check_for_meeting_not_found("initial_navigation")
        self.check_for_login_required("initial_navigation")

        self.click_join_as_guest()
        self.fill_guest_details()
        self.turn_off_media_inputs()
        self.click_join_meeting_button()
        self.wait_until_joined_or_timeout()
        self.ready_to_show_bot_image()

    def click_leave_button(self):
        leave_button = self.locate_element(
            step="leave_button",
            condition=EC.presence_of_element_located(
                (
                    By.XPATH,
                    (
                        "//button[contains(translate(@aria-label, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'leave')]"
                        "|//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'leave meeting')]"
                    ),
                )
            ),
            wait_time_seconds=10,
        )
        self.click_element(leave_button, "leave_button")
