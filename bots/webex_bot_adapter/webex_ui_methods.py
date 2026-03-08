import logging
import os
import time

from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
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
    GUEST_NAME_INPUT_XPATH = (
        "//input[contains(translate(@aria-label, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'name') "
        "or contains(translate(@placeholder, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'name') "
        "or ((@type='text' or not(@type)) and not(@type='hidden'))]"
    )
    JOIN_AS_GUEST_SELECTOR_CANDIDATES = [
        (
            "button_join_as_guest",
            "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'join as guest')]",
        ),
        (
            "link_join_as_guest",
            "//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'join as guest')]",
        ),
        (
            "button_continue_as_guest",
            "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'continue as guest')]",
        ),
        (
            "link_continue_as_guest",
            "//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'continue as guest')]",
        ),
        (
            "button_join_as_a_guest",
            "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'join as a guest')]",
        ),
        (
            "link_join_as_a_guest",
            "//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'join as a guest')]",
        ),
    ]

    def locate_element(self, step, condition, wait_time_seconds=60):
        try:
            return WebDriverWait(self.driver, wait_time_seconds).until(condition)
        except Exception as e:
            logger.info(f"Exception raised in locate_element for {step}")
            if step == "join_as_guest_button":
                logger.info(
                    f"Join-as-guest locate failure details: exception_type={e.__class__.__name__}, "
                    f"url_hint={self.meeting_url.split('?')[0] if self.meeting_url else None}, "
                    f"title_hint=unavailable_during_failure, "
                    f"name_form_visible={self.is_guest_name_form_visible()}"
                )
                self._log_join_as_guest_selector_diagnostics("post_wait_failure")
                ui_signals = self.collect_ui_signals()
                logger.info(
                    f"Join-as-guest post-wait UI signals: iframe_count={ui_signals.get('iframe_count')}, "
                    f"has_sign_in_text={ui_signals.get('has_sign_in_text')}, "
                    f"has_join_meeting_text={ui_signals.get('has_join_meeting_text')}, "
                    f"buttons_sample={ui_signals.get('buttons')}, links_sample={ui_signals.get('links')}"
                )
                # region agent log
                self._debug_emit(
                    "H1",
                    "webex_ui_methods.py:locate_element",
                    "Failed to locate join_as_guest_button",
                    {
                        "step": step,
                        "wait_time_seconds": wait_time_seconds,
                        "current_url_hint": self.meeting_url.split("?")[0] if self.meeting_url else None,
                        "title_hint": "unavailable_during_failure",
                        "name_form_visible": self.is_guest_name_form_visible(),
                    },
                )
                # endregion
            raise UiCouldNotLocateElementException(f"Exception raised in locate_element for {step}", step, e)

    def find_element_by_selector(self, selector_type, selector):
        try:
            return self.driver.find_element(selector_type, selector)
        except NoSuchElementException:
            return None
        except Exception:
            return None

    def capture_flow_screenshot(self, label):
        if os.getenv("WEBEX_FLOW_SCREENSHOTS", "false").lower() != "true":
            return
        timestamp = int(time.time() * 1000)
        screenshots_dir = "/tmp/screenshots"
        screenshot_path = f"{screenshots_dir}/webex_flow_{label}_{timestamp}.png"
        try:
            os.makedirs(screenshots_dir, exist_ok=True)
            self.driver.save_screenshot(screenshot_path)
            screenshot_size = os.path.getsize(screenshot_path) if os.path.exists(screenshot_path) else 0
            logger.info(f"[Webex flow screenshot] label={label} saved path={screenshot_path} size_bytes={screenshot_size}")
            # region agent log
            self._debug_emit(
                "H12",
                "webex_ui_methods.py:capture_flow_screenshot",
                "Webex flow screenshot saved",
                {"label": label, "screenshot_path": screenshot_path, "size_bytes": screenshot_size},
            )
            # endregion
        except Exception as e:
            logger.info(f"[Webex flow screenshot] label={label} failed error={e.__class__.__name__}")
            # region agent log
            self._debug_emit(
                "H12",
                "webex_ui_methods.py:capture_flow_screenshot",
                "Webex flow screenshot failed",
                {"label": label, "error_type": e.__class__.__name__},
            )
            # endregion

    def _log_join_as_guest_selector_diagnostics(self, phase):
        logger.info(f"[Webex guest diagnostics] phase={phase} starting selector scan")
        for selector_name, selector in self.JOIN_AS_GUEST_SELECTOR_CANDIDATES:
            element = self.find_element_by_selector(By.XPATH, selector)
            if element:
                text_preview = (element.text or "").strip().replace("\n", " ")[:120]
                logger.info(
                    f"[Webex guest diagnostics] phase={phase} selector={selector_name} found=true text_preview='{text_preview}'"
                )
            else:
                logger.info(f"[Webex guest diagnostics] phase={phase} selector={selector_name} found=false")

    def click_element(self, element, step):
        try:
            element.click()
        except Exception as e:
            raise UiCouldNotLocateElementException("Could not click element", step, e)

    def click_optional_continue_in_browser(self):
        # region agent log
        self._debug_emit(
            "H13",
            "webex_ui_methods.py:click_optional_continue_in_browser",
            "Entered continue-in-browser flow",
            {"current_url_hint": self.meeting_url.split("?")[0] if self.meeting_url else None},
        )
        # endregion
        selectors = [
            (By.XPATH, "//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'join from this browser')]"),
            (By.XPATH, "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'join from this browser')]"),
            (By.XPATH, "//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'join from your browser')]"),
            (By.XPATH, "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'join from your browser')]"),
            (By.XPATH, "//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'join from browser')]"),
            (By.XPATH, "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'join from browser')]"),
            (By.XPATH, "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'continue in browser')]"),
        ]
        logger.info(f"Scanning for continue-in-browser entry points across {len(selectors)} selectors")
        for selector_type, selector in selectors:
            # region agent log
            self._debug_emit(
                "H13",
                "webex_ui_methods.py:click_optional_continue_in_browser",
                "Querying continue-in-browser selector",
                {"selector": selector},
            )
            # endregion
            try:
                elements = self.driver.find_elements(selector_type, selector)
            except Exception as find_error:
                # region agent log
                self._debug_emit(
                    "H13",
                    "webex_ui_methods.py:click_optional_continue_in_browser",
                    "Selector query failed for continue-in-browser",
                    {"selector": selector, "error_type": find_error.__class__.__name__},
                )
                # endregion
                raise UiCouldNotLocateElementException(
                    "Continue-in-browser selector query failed",
                    "continue_in_browser",
                    find_error,
                )
            # region agent log
            self._debug_emit(
                "H8",
                "webex_ui_methods.py:click_optional_continue_in_browser",
                "Continue-in-browser selector candidates",
                {"selector": selector, "candidate_count": len(elements)},
            )
            # endregion
            for idx, element in enumerate(elements):
                try:
                    # region agent log
                    self._debug_emit(
                        "H8",
                        "webex_ui_methods.py:click_optional_continue_in_browser",
                        "Attempting continue-in-browser candidate click",
                        {"selector": selector, "candidate_index": idx, "strategy": "js_click_first"},
                    )
                    # endregion
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'}); arguments[0].click();", element)
                    # region agent log
                    self._debug_emit(
                        "H8",
                        "webex_ui_methods.py:click_optional_continue_in_browser",
                        "Clicked continue-in-browser candidate",
                        {"selector": selector, "candidate_index": idx, "strategy": "js_click"},
                    )
                    # endregion
                    return True
                except Exception as click_error:
                    if click_error.__class__.__name__ == "ReadTimeoutError":
                        # region agent log
                        self._debug_emit(
                            "H13",
                            "webex_ui_methods.py:click_optional_continue_in_browser",
                            "Webdriver click timed out on continue-in-browser candidate",
                            {"selector": selector, "candidate_index": idx, "error_type": click_error.__class__.__name__},
                        )
                        # endregion
                        raise UiCouldNotLocateElementException(
                            "Continue-in-browser click timed out",
                            "continue_in_browser",
                            click_error,
                        )
                    # region agent log
                    self._debug_emit(
                        "H8",
                        "webex_ui_methods.py:click_optional_continue_in_browser",
                        "Webdriver click failed for continue-in-browser candidate",
                        {"selector": selector, "candidate_index": idx, "error_type": click_error.__class__.__name__},
                    )
                    # endregion
                    try:
                        logger.info("Falling back to webdriver click for continue-in-browser candidate")
                        self.click_element(element, "continue_in_browser")
                        # region agent log
                        self._debug_emit(
                            "H8",
                            "webex_ui_methods.py:click_optional_continue_in_browser",
                            "Clicked continue-in-browser candidate",
                            {"selector": selector, "candidate_index": idx, "strategy": "webdriver_click"},
                        )
                        # endregion
                        return True
                    except Exception as webdriver_click_error:
                        # region agent log
                        self._debug_emit(
                            "H8",
                            "webex_ui_methods.py:click_optional_continue_in_browser",
                            "Webdriver fallback click failed for continue-in-browser candidate",
                            {
                                "selector": selector,
                                "candidate_index": idx,
                                "error_type": webdriver_click_error.__class__.__name__,
                            },
                        )
                        # endregion
                        continue

        # If not found/clickable in top-level document, inspect iframes.
        iframe_elements = self.driver.find_elements(By.TAG_NAME, "iframe")
        # region agent log
        self._debug_emit(
            "H9",
            "webex_ui_methods.py:click_optional_continue_in_browser",
            "Inspecting iframes for continue-in-browser entry point",
            {"iframe_count": len(iframe_elements)},
        )
        # endregion
        for iframe_idx in range(len(iframe_elements)):
            try:
                self.driver.switch_to.default_content()
                iframe_elements = self.driver.find_elements(By.TAG_NAME, "iframe")
                if iframe_idx >= len(iframe_elements):
                    continue
                self.driver.switch_to.frame(iframe_elements[iframe_idx])
            except Exception as iframe_switch_error:
                # region agent log
                self._debug_emit(
                    "H9",
                    "webex_ui_methods.py:click_optional_continue_in_browser",
                    "Failed to switch to iframe",
                    {"iframe_index": iframe_idx, "error_type": iframe_switch_error.__class__.__name__},
                )
                # endregion
                continue

            for selector_type, selector in selectors:
                frame_elements = self.driver.find_elements(selector_type, selector)
                # region agent log
                self._debug_emit(
                    "H9",
                    "webex_ui_methods.py:click_optional_continue_in_browser",
                    "Iframe selector candidates",
                    {"iframe_index": iframe_idx, "selector": selector, "candidate_count": len(frame_elements)},
                )
                # endregion
                for idx, element in enumerate(frame_elements):
                    try:
                        # region agent log
                        self._debug_emit(
                            "H9",
                            "webex_ui_methods.py:click_optional_continue_in_browser",
                            "Attempting iframe continue-in-browser candidate click",
                            {
                                "iframe_index": iframe_idx,
                                "selector": selector,
                                "candidate_index": idx,
                                "strategy": "js_click_first",
                            },
                        )
                        # endregion
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'}); arguments[0].click();", element)
                        # region agent log
                        self._debug_emit(
                            "H9",
                            "webex_ui_methods.py:click_optional_continue_in_browser",
                            "Clicked continue-in-browser candidate in iframe",
                            {"iframe_index": iframe_idx, "selector": selector, "candidate_index": idx, "strategy": "js_click"},
                        )
                        # endregion
                        self.driver.switch_to.default_content()
                        return True
                    except Exception as click_error:
                        # region agent log
                        self._debug_emit(
                            "H9",
                            "webex_ui_methods.py:click_optional_continue_in_browser",
                            "Iframe webdriver click failed",
                            {
                                "iframe_index": iframe_idx,
                                "selector": selector,
                                "candidate_index": idx,
                                "error_type": click_error.__class__.__name__,
                            },
                        )
                        # endregion
                        try:
                            self.click_element(element, "continue_in_browser")
                            # region agent log
                            self._debug_emit(
                                "H9",
                                "webex_ui_methods.py:click_optional_continue_in_browser",
                                "Clicked continue-in-browser candidate in iframe",
                                {"iframe_index": iframe_idx, "selector": selector, "candidate_index": idx, "strategy": "webdriver_click"},
                            )
                            # endregion
                            self.driver.switch_to.default_content()
                            return True
                        except Exception as webdriver_click_error:
                            # region agent log
                            self._debug_emit(
                                "H9",
                                "webex_ui_methods.py:click_optional_continue_in_browser",
                                "Iframe webdriver fallback click failed",
                                {
                                    "iframe_index": iframe_idx,
                                    "selector": selector,
                                    "candidate_index": idx,
                                    "error_type": webdriver_click_error.__class__.__name__,
                                },
                            )
                            # endregion
                            continue

        self.driver.switch_to.default_content()
        logger.info("No continue-in-browser entry point found; continuing with current page state")
        return False

    def click_join_from_this_browser_strict(self):
        logger.info("Trying strict click for 'Join from this browser' button")
        strict_button_xpath = (
            "//button[.//*[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'join from this browser')] "
            "or contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'join from this browser')]"
        )
        strict_link_xpath = (
            "//a[.//*[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'join from this browser')] "
            "or contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'join from this browser')]"
        )

        for selector_type, selector in [(By.XPATH, strict_button_xpath), (By.XPATH, strict_link_xpath)]:
            try:
                elements = self.driver.find_elements(selector_type, selector)
                for element in elements:
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'}); arguments[0].click();", element)
                    logger.info("Strict 'Join from this browser' click succeeded")
                    return True
            except Exception:
                continue

        strict_fallback_xpath = (
            "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'join from this browser')]"
            "|//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'join from this browser')]"
        )
        try:
            element = self.locate_element(
                step="join_from_this_browser_button",
                condition=EC.presence_of_element_located((By.XPATH, strict_fallback_xpath)),
                wait_time_seconds=10,
            )
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'}); arguments[0].click();", element)
            logger.info("Strict 'Join from this browser' click succeeded via fallback")
            return True
        except Exception:
            pass

        logger.info("Strict 'Join from this browser' click not available")
        return False

    def navigate_to_post_landing_page_if_available(self):
        try:
            extended_data_raw = self.driver.execute_script(
                "return document.getElementById('extendedData') ? document.getElementById('extendedData').textContent : null;"
            )
            if not extended_data_raw:
                return False
            import json

            extended_data = json.loads(extended_data_raw)
            post_landing_page = extended_data.get("meetingData", {}).get("postLandingPage")
            if not post_landing_page:
                return False
            logger.info(f"Navigating to Webex postLandingPage fallback: {post_landing_page}")
            self.driver.get(post_landing_page)
            # region agent log
            self._debug_emit(
                "H19",
                "webex_ui_methods.py:navigate_to_post_landing_page_if_available",
                "Navigated to postLandingPage fallback",
                {"post_landing_page": post_landing_page},
            )
            # endregion
            return True
        except Exception as e:
            logger.info(f"Could not navigate to Webex postLandingPage fallback: {e.__class__.__name__}")
            return False

    def dismiss_cookie_banner_if_present(self):
        logger.info("Scanning for cookie banner...")
        selectors = [
            (By.XPATH, "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'reject')]"),
            (By.XPATH, "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'accept')]"),
            (By.XPATH, "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'close')]"),
        ]
        for selector_type, selector in selectors:
            element = self.find_element_by_selector(selector_type, selector)
            if element:
                logger.info("Dismissing cookie banner...")
                # region agent log
                self._debug_emit(
                    "H3",
                    "webex_ui_methods.py:dismiss_cookie_banner_if_present",
                    "Cookie banner dismissed",
                    {"selector": selector},
                )
                # endregion
                self.click_element(element, "dismiss_cookie_banner")
                logger.info("Cookie banner dismissed")
                return
        # region agent log
        self._debug_emit(
            "H3",
            "webex_ui_methods.py:dismiss_cookie_banner_if_present",
            "Cookie banner not found",
            {},
        )
        # endregion

    def check_for_login_required(self, step):
        login_signals = [
            "//input[@name='username' or @name='email']",
            "//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'sign in to join')]",
        ]
        for signal in login_signals:
            if self.find_element_by_selector(By.XPATH, signal):
                logger.info(f"Detected login-required signal during step={step}: {signal}")
                raise UiLoginRequiredException("Login required to join this Webex meeting", step)

    def check_for_meeting_not_found(self, step):
        not_found_signals = [
            "//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'meeting not found')]",
            "//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'invalid meeting')]",
            "//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'expired')]",
        ]
        for signal in not_found_signals:
            if self.find_element_by_selector(By.XPATH, signal):
                logger.info(f"Detected meeting-not-found signal during step={step}: {signal}")
                raise UiMeetingNotFoundException("Webex meeting not found", step)

    def check_for_denied_join(self, step):
        denied_signals = [
            "//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'request to join was denied')]",
            "//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'host denied')]",
            "//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'unable to join')]",
        ]
        for signal in denied_signals:
            if self.find_element_by_selector(By.XPATH, signal):
                logger.info(f"Detected denied-join signal during step={step}: {signal}")
                raise UiRequestToJoinDeniedException("Request to join Webex meeting denied", step)

    def check_for_platform_blocking(self, step):
        if self.find_element_by_selector(By.XPATH, "//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'something went wrong')]"):
            logger.info(f"Detected Webex platform-blocking signal during step={step}")
            raise UiWebexBlockingUsException("Webex blocked the join flow temporarily", step)

    def dismiss_external_app_prompt_if_present(self):
        # Webex may trigger a browser-level "open application" prompt which is not part of page DOM.
        # The "Cancel" button is usually focused; Enter confirms cancel. ESC is a fallback.
        try:
            ActionChains(self.driver).send_keys(Keys.ENTER).perform()
            time.sleep(0.2)
            ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
            logger.info("Attempted to cancel external-app launch prompt via ENTER/ESC")
        except Exception as prompt_error:
            logger.info(f"Could not dismiss external-app prompt: {prompt_error.__class__.__name__}")

    def fill_guest_details(self):
        logger.info("Locating guest details form fields")
        name_input = self.locate_element(
            step="guest_name_input",
            condition=EC.presence_of_element_located(
                (
                    By.XPATH,
                    self.GUEST_NAME_INPUT_XPATH,
                )
            ),
            wait_time_seconds=10,
        )
        name_input.clear()
        name_input.send_keys(self.display_name)
        logger.info("Filled guest display name field")

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
            logger.info("Filled guest email field")
        else:
            logger.info("Guest email field not present; proceeding with name-only form")

    def turn_off_media_inputs(self):
        microphone_button = self.find_element_by_selector(
            By.XPATH,
            "//button[contains(translate(@aria-label, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'microphone') or contains(translate(@aria-label, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'mute')]",
        )
        if microphone_button:
            logger.info("Toggling microphone button before join")
            self.click_element(microphone_button, "turn_off_microphone")
        else:
            logger.info("Microphone toggle button not found before join")

        camera_button = self.find_element_by_selector(
            By.XPATH,
            "//button[contains(translate(@aria-label, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'camera') or contains(translate(@aria-label, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'video')]",
        )
        if camera_button:
            logger.info("Toggling camera button before join")
            self.click_element(camera_button, "turn_off_camera")
        else:
            logger.info("Camera toggle button not found before join")

    def click_join_as_guest(self):
        # region agent log
        self._debug_emit(
            "H1",
            "webex_ui_methods.py:click_join_as_guest",
            "Attempting join_as_guest selector path",
            {"name_form_visible_before_click": self.is_guest_name_form_visible()},
        )
        # endregion
        logger.info("Trying to locate and click 'Join as Guest' button...")
        logger.info(
            f"Join-as-guest pre-wait page context: url_hint={self.meeting_url.split('?')[0] if self.meeting_url else None}, "
            f"title_hint=unavailable_pre_wait, name_form_visible={self.is_guest_name_form_visible()}"
        )
        self._log_join_as_guest_selector_diagnostics("pre_wait")
        logger.info("Waiting up to 30 seconds for join-as-guest selectors")
        join_as_guest = self.locate_element(
            step="join_as_guest_button",
            condition=EC.presence_of_element_located(
                (
                    By.XPATH,
                    (
                        "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'join as guest')]"
                        "|//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'join as guest')]"
                        "|//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'continue as guest')]"
                        "|//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'continue as guest')]"
                        "|//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'join as a guest')]"
                        "|//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'join as a guest')]"
                    ),
                )
            ),
            wait_time_seconds=30,
        )
        logger.info("Join as guest button located; clicking")
        self.click_element(join_as_guest, "join_as_guest_button")

    def is_guest_name_form_visible(self):
        return self.find_element_by_selector(By.XPATH, self.GUEST_NAME_INPUT_XPATH) is not None

    # region agent log
    def collect_ui_signals(self):
        try:
            return self.driver.execute_script(
                """
                const buttons = Array.from(document.querySelectorAll('button'))
                  .map(el => (el.innerText || '').trim().toLowerCase())
                  .filter(Boolean)
                  .slice(0, 12);
                const links = Array.from(document.querySelectorAll('a'))
                  .map(el => (el.innerText || '').trim().toLowerCase())
                  .filter(Boolean)
                  .slice(0, 12);
                const inputs = Array.from(document.querySelectorAll('input'))
                  .map(el => ({
                    type: (el.getAttribute('type') || '').toLowerCase(),
                    name: (el.getAttribute('name') || '').toLowerCase(),
                    ariaLabel: (el.getAttribute('aria-label') || '').toLowerCase(),
                    placeholder: (el.getAttribute('placeholder') || '').toLowerCase()
                  }))
                  .slice(0, 12);
                const bodyText = (document.body && document.body.innerText ? document.body.innerText : '').toLowerCase();
                return {
                  iframe_count: document.querySelectorAll('iframe').length,
                  buttons,
                  links,
                  inputs,
                  has_enter_name_and_join_text: bodyText.includes('enter your name and join'),
                  has_join_meeting_text: bodyText.includes('join meeting'),
                  has_sign_in_text: bodyText.includes('sign in'),
                };
                """
            )
        except Exception as e:
            return {"ui_signal_error": e.__class__.__name__}

    # endregion

    def click_join_meeting_button(self):
        logger.info("Trying to locate and click final 'Join meeting' button")
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
        logger.info("Join meeting button located; clicking")
        self.click_element(join_button, "join_meeting_button")

    def _try_fill_name_and_click_join_meeting_direct_in_current_context(self):
        return self.driver.execute_script(
            """
            const displayName = arguments[0];
            const lower = (v) => (v || '').toString().trim().toLowerCase();
            const isVisible = (el) => !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));

            const labelNodes = Array.from(document.querySelectorAll('label,span,div,p'));
            const labelNode = labelNodes.find((el) => {
              const text = lower(el.innerText || el.textContent);
              return text.includes('name (required)') || text.includes('name required') || text === 'name';
            });

            let nameInput = null;
            if (labelNode && labelNode.tagName && labelNode.tagName.toLowerCase() === 'label') {
              const forId = labelNode.getAttribute('for');
              if (forId) {
                nameInput = document.getElementById(forId);
              }
              if (!nameInput) {
                nameInput = labelNode.querySelector('input');
              }
            }
            if (!nameInput && labelNode) {
              nameInput = labelNode.querySelector('input');
            }
            if (!nameInput) {
              const inputs = Array.from(document.querySelectorAll("input:not([type='hidden'])"))
                .filter((el) => isVisible(el) && !el.disabled);
              nameInput = inputs.find((el) => {
                const attrs = lower(el.getAttribute('aria-label')) + ' ' + lower(el.getAttribute('placeholder')) + ' ' + lower(el.getAttribute('name'));
                return attrs.includes('name');
              }) || inputs[0] || null;
            }

            const setInputValue = (input, value) => {
              if (!input) return false;
              input.focus();
              input.value = '';
              input.dispatchEvent(new Event('input', { bubbles: true }));
              input.value = value;
              input.dispatchEvent(new Event('input', { bubbles: true }));
              input.dispatchEvent(new Event('change', { bubbles: true }));
              return true;
            };

            const inputFilled = setInputValue(nameInput, displayName);

            const buttonCandidates = Array.from(document.querySelectorAll("button,[role='button'],input[type='submit'],input[type='button']"))
              .filter((el) => isVisible(el) && !el.disabled);
            const joinButton = buttonCandidates.find((el) => {
              const text = lower(el.innerText || el.textContent || el.value || el.getAttribute('aria-label'));
              return text.includes('join meeting');
            }) || null;

            if (joinButton) {
              joinButton.click();
            }

            return {
              input_filled: inputFilled,
              join_button_found: !!joinButton,
              join_clicked: !!joinButton && inputFilled,
            };
            """,
            self.display_name,
        )

    def try_fill_name_and_click_join_meeting_direct(self):
        logger.info("Trying direct JS path for 'Name (required)' + 'Join meeting'")
        deadline = time.time() + 20
        last_result = None
        while time.time() < deadline:
            self.driver.switch_to.default_content()
            last_result = self._try_fill_name_and_click_join_meeting_direct_in_current_context()
            if last_result and last_result.get("join_clicked"):
                logger.info(f"Direct JS join path result (default content): {last_result}")
                return True

            iframe_elements = self.driver.find_elements(By.TAG_NAME, "iframe")
            for iframe_idx in range(len(iframe_elements)):
                try:
                    self.driver.switch_to.default_content()
                    iframe_elements = self.driver.find_elements(By.TAG_NAME, "iframe")
                    if iframe_idx >= len(iframe_elements):
                        continue
                    self.driver.switch_to.frame(iframe_elements[iframe_idx])
                    last_result = self._try_fill_name_and_click_join_meeting_direct_in_current_context()
                    if last_result and last_result.get("join_clicked"):
                        logger.info(f"Direct JS join path result (iframe {iframe_idx}): {last_result}")
                        self.driver.switch_to.default_content()
                        return True
                except Exception as iframe_error:
                    logger.info(f"Direct JS join path iframe probe failed at index {iframe_idx}: {iframe_error.__class__.__name__}")
                    continue
                finally:
                    try:
                        self.driver.switch_to.default_content()
                    except Exception:
                        pass

            time.sleep(1)

        logger.info(f"Direct JS join path did not find actionable fields/buttons within timeout. last_result={last_result}")
        return False

    def wait_for_guest_entry_surface(self):
        logger.info("Waiting for guest entry surface after browser-entry click")
        guest_entry_xpath = (
            f"{self.GUEST_NAME_INPUT_XPATH}"
            "|//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'join as guest')]"
            "|//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'join as guest')]"
            "|//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'continue as guest')]"
            "|//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'continue as guest')]"
            "|//input[contains(translate(@aria-label, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'email')]"
            "|//input[contains(translate(@placeholder, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'email')]"
        )
        try:
            WebDriverWait(self.driver, 45).until(
                EC.presence_of_element_located((By.XPATH, guest_entry_xpath))
            )
            # region agent log
            self._debug_emit(
                "H17",
                "webex_ui_methods.py:wait_for_guest_entry_surface",
                "Guest entry surface detected",
                {},
            )
            # endregion
        except TimeoutException as e:
            # region agent log
            self._debug_emit(
                "H17",
                "webex_ui_methods.py:wait_for_guest_entry_surface",
                "Timed out waiting for guest entry surface",
                {},
            )
            # endregion
            raise UiCouldNotLocateElementException("Timed out waiting for guest entry surface", "guest_entry_surface", e)

    def wait_until_joined_or_timeout(self):
        logger.info("Waiting for joined state by polling leave button visibility")
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
                logger.info("Leave button detected; joined state confirmed")
                return

            self.check_for_denied_join("wait_until_joined")
            self.check_for_meeting_not_found("wait_until_joined")
            self.check_for_login_required("wait_until_joined")
            self.check_for_platform_blocking("wait_until_joined")

            waiting_room_timeout_exceeded = time.time() - waiting_room_timeout_started_at > self.automatic_leave_configuration.waiting_room_timeout_seconds
            if waiting_room_timeout_exceeded:
                logger.info("Waiting room timeout exceeded before joined state")
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
        # region agent log
        self._debug_emit(
            "H0",
            "webex_ui_methods.py:attempt_to_join_meeting",
            "Webex instrumentation version marker",
            {"version": "webex-debug-v3"},
        )
        # endregion
        self.capture_flow_screenshot("after_initial_navigation")
        # region agent log
        self._debug_emit(
            "H2",
            "webex_ui_methods.py:attempt_to_join_meeting",
            "Initial navigation state",
            {
                "current_url_hint": self.meeting_url.split("?")[0] if self.meeting_url else None,
                "title_hint": "collected_via_screenshot",
            },
        )
        # endregion
        logger.info("Applying browser permissions for camera/microphone/screen capture")
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

        self.dismiss_cookie_banner_if_present()
        self.capture_flow_screenshot("after_cookie_dismiss_1")
        try:
            clicked_browser_entry = self.click_join_from_this_browser_strict()
            if not clicked_browser_entry:
                clicked_browser_entry = self.click_optional_continue_in_browser()
            if not clicked_browser_entry:
                use_post_landing_fallback = os.getenv("WEBEX_USE_POST_LANDING_FALLBACK", "false").lower() == "true"
                if use_post_landing_fallback:
                    self.navigate_to_post_landing_page_if_available()
                else:
                    logger.info("Skipping postLandingPage fallback; proceeding on current page")
        except UiCouldNotLocateElementException:
            self.capture_flow_screenshot("continue_in_browser_exception")
            raise
        self.capture_flow_screenshot("after_continue_in_browser_attempt")
        self.dismiss_external_app_prompt_if_present()
        post_browser_entry_settle_seconds = int(os.getenv("WEBEX_POST_BROWSER_ENTRY_SETTLE_SECONDS", "12"))
        logger.info(f"Waiting {post_browser_entry_settle_seconds}s for post-browser-entry page transition")
        time.sleep(post_browser_entry_settle_seconds)

        try:
            if self.try_fill_name_and_click_join_meeting_direct():
                self.capture_flow_screenshot("after_direct_name_and_join_click")
                self.wait_until_joined_or_timeout()
                self.ready_to_show_bot_image()
                return
        except Exception as direct_join_error:
            logger.info(f"Direct JS name+join path failed: {direct_join_error.__class__.__name__}")

        # Prefer direct guest form fill immediately after browser-entry click.
        try:
            self.fill_guest_details()
            logger.info("Guest details filled via direct form path")
            self.capture_flow_screenshot("guest_form_direct_path")
        except UiCouldNotLocateElementException:
            logger.info("Direct guest form not available, trying postLandingPage fallback before guest-gate path")
            navigated_to_landing = self.navigate_to_post_landing_page_if_available()
            if navigated_to_landing:
                self.capture_flow_screenshot("after_post_landing_navigation")
                self.fill_guest_details()
            else:
                allow_join_as_guest_fallback = os.getenv("WEBEX_ALLOW_JOIN_AS_GUEST_FALLBACK", "false").lower() == "true"
                if allow_join_as_guest_fallback:
                    logger.info("postLandingPage fallback unavailable, attempting join-as-guest gate path")
                    self.click_join_as_guest()
                    self.dismiss_cookie_banner_if_present()
                    self.capture_flow_screenshot("after_join_as_guest_attempt")
                    self.fill_guest_details()
                else:
                    logger.info("Could not reach direct guest form; join-as-guest fallback disabled")
                    raise
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
