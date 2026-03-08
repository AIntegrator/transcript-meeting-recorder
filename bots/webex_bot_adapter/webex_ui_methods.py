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
        "or @autocomplete='name']"
        "|//*[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'name (required)')]/following::input[1]"
        "|//label[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'name')]/following::input[1]"
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
    _webex_form_context_idx = None

    def install_external_protocol_guard(self):
        guard_script = """
        (() => {
          if (window.__webexExternalProtocolGuardInstalled) return;
          window.__webexExternalProtocolGuardInstalled = true;
          window.__webexGuardBlockedUrls = window.__webexGuardBlockedUrls || [];
          const lower = (v) => (v || '').toString().trim().toLowerCase();
          const isAllowed = (url) => {
            try {
              const parsed = new URL(url, window.location.href);
              const protocol = lower(parsed.protocol);
              return protocol === 'http:' || protocol === 'https:' || protocol === 'about:' || protocol === 'blob:' || protocol === 'data:';
            } catch (e) {
              return true;
            }
          };

          const wrapLocationMethod = (name) => {
            const original = window.location[name] ? window.location[name].bind(window.location) : null;
            if (!original) return;
            window.location[name] = (url) => {
              if (url && !isAllowed(url)) {
                window.__webexGuardBlockedUrls.push({ source: 'location.' + name, url: String(url) });
                console.debug('[webex-guard] blocked location.' + name, url);
                return;
              }
              return original(url);
            };
          };
          wrapLocationMethod('assign');
          wrapLocationMethod('replace');

          const originalOpen = window.open ? window.open.bind(window) : null;
          if (originalOpen) {
            window.open = (url, ...args) => {
              if (url && !isAllowed(url)) {
                window.__webexGuardBlockedUrls.push({ source: 'window.open', url: String(url) });
                console.debug('[webex-guard] blocked window.open', url);
                return null;
              }
              return originalOpen(url, ...args);
            };
          }

          const stopIfExternal = (rawUrl, event) => {
            if (!rawUrl) return false;
            if (isAllowed(rawUrl)) return false;
            if (event) {
              event.preventDefault();
              event.stopImmediatePropagation();
            }
            window.__webexGuardBlockedUrls.push({ source: 'link_activation', url: String(rawUrl) });
            console.debug('[webex-guard] blocked external link activation', rawUrl);
            return true;
          };

          document.addEventListener('click', (event) => {
            const target = event.target && event.target.closest ? event.target.closest('a[href],button[data-href]') : null;
            if (!target) return;
            const href = target.getAttribute('href') || target.getAttribute('data-href');
            stopIfExternal(href, event);
          }, true);
        })();
        """
        try:
            self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": guard_script})
            self.driver.execute_script(guard_script)
            logger.info("Installed external protocol guard for Webex pages")
        except Exception as e:
            logger.info(f"Failed to install external protocol guard: {e.__class__.__name__}")

    def log_external_protocol_guard_state(self, label):
        try:
            blocked = self.driver.execute_script("return (window.__webexGuardBlockedUrls || []).slice(-10);")
            logger.info(f"[webex-guard:{label}] blocked_urls={blocked}")
        except Exception as e:
            logger.info(f"[webex-guard:{label}] failed_to_read_state error={e.__class__.__name__}")

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

    def _switch_to_context(self, context_idx):
        self.driver.switch_to.default_content()
        if context_idx is None:
            return True
        try:
            iframe_elements = self.driver.find_elements(By.TAG_NAME, "iframe")
            if context_idx >= len(iframe_elements):
                return False
            self.driver.switch_to.frame(iframe_elements[context_idx])
            return True
        except Exception:
            self.driver.switch_to.default_content()
            return False

    def _iter_context_indices(self):
        self.driver.switch_to.default_content()
        iframe_count = len(self.driver.find_elements(By.TAG_NAME, "iframe"))
        contexts = [None]
        contexts.extend(range(iframe_count))
        return contexts

    def _find_visible_element_in_any_context(self, selector_type, selector, preferred_context_idx=None):
        contexts = self._iter_context_indices()
        if preferred_context_idx in contexts:
            contexts = [preferred_context_idx] + [ctx for ctx in contexts if ctx != preferred_context_idx]

        for context_idx in contexts:
            if not self._switch_to_context(context_idx):
                continue
            try:
                elements = self.driver.find_elements(selector_type, selector)
            except Exception:
                continue
            for element in elements:
                try:
                    if element.is_displayed():
                        return element, context_idx
                except Exception:
                    continue
        self.driver.switch_to.default_content()
        return None, None

    def click_visible_button_by_text_in_any_context(self, text, preferred_context_idx=None):
        text_lower = text.lower()
        xpath = (
            "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '"
            + text_lower
            + "')]"
            "|//*[@role='button' and contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '"
            + text_lower
            + "')]"
        )
        element, context_idx = self._find_visible_element_in_any_context(By.XPATH, xpath, preferred_context_idx)
        if element is None:
            return False
        if not self._switch_to_context(context_idx):
            return False
        try:
            disabled_attr = (element.get_attribute("disabled") or "").lower()
            aria_disabled = (element.get_attribute("aria-disabled") or "").lower()
            is_disabled = disabled_attr in {"true", "disabled"} or aria_disabled == "true"
            if is_disabled:
                return False
            try:
                self.click_element(element, f"button_text_{text_lower}")
            except Exception:
                ActionChains(self.driver).move_to_element(element).click().perform()
            logger.info(f"Clicked visible button by text='{text_lower}' in context={context_idx}")
            self._webex_form_context_idx = context_idx
            return True
        finally:
            try:
                self.driver.switch_to.default_content()
            except Exception:
                pass

    def _click_shadow_button_by_text_in_current_context(self, text):
        text_lower = text.lower()
        try:
            result = self.driver.execute_script(
                """
                const targetText = arguments[0];
                const lower = (v) => (v || '').toString().trim().toLowerCase();
                const isVisible = (el) => !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
                const roots = [document];
                const nodes = [];
                while (roots.length) {
                  const root = roots.shift();
                  const all = root.querySelectorAll('*');
                  for (const el of all) {
                    nodes.push(el);
                    if (el.shadowRoot) roots.push(el.shadowRoot);
                  }
                }

                const clickables = nodes.filter((el) => {
                  const tag = lower(el.tagName);
                  const role = lower(el.getAttribute('role'));
                  const type = lower(el.getAttribute('type'));
                  const clickable = tag === 'button' || tag === 'a' || role === 'button' || (tag === 'input' && (type === 'submit' || type === 'button'));
                  return clickable && isVisible(el);
                });
                const candidate = clickables.find((el) => {
                  const txt = lower((el.innerText || el.textContent || el.value || '') + ' ' + (el.getAttribute('aria-label') || ''));
                  return txt.includes(targetText);
                });
                if (!candidate) return { clicked: false, reason: 'not_found' };

                const disabledAttr = lower(candidate.getAttribute('disabled'));
                const ariaDisabled = lower(candidate.getAttribute('aria-disabled'));
                const disabled = disabledAttr === 'true' || disabledAttr === 'disabled' || ariaDisabled === 'true' || !!candidate.disabled;
                if (disabled) return { clicked: false, reason: 'disabled' };

                candidate.click();
                return { clicked: true };
                """,
                text_lower,
            )
            return bool(result and result.get("clicked"))
        except Exception:
            return False

    def click_shadow_button_by_text_in_any_context(self, text, preferred_context_idx=None):
        contexts = self._iter_context_indices()
        if preferred_context_idx in contexts:
            contexts = [preferred_context_idx] + [ctx for ctx in contexts if ctx != preferred_context_idx]
        for context_idx in contexts:
            if not self._switch_to_context(context_idx):
                continue
            try:
                if self._click_shadow_button_by_text_in_current_context(text):
                    logger.info(f"Clicked shadow button by text='{text.lower()}' in context={context_idx}")
                    self._webex_form_context_idx = context_idx
                    return True
            finally:
                try:
                    self.driver.switch_to.default_content()
                except Exception:
                    pass
        return False

    def click_any_visible_text_target_in_any_context(self, text, preferred_context_idx=None):
        text_lower = text.lower()
        contexts = self._iter_context_indices()
        if preferred_context_idx in contexts:
            contexts = [preferred_context_idx] + [ctx for ctx in contexts if ctx != preferred_context_idx]
        for context_idx in contexts:
            if not self._switch_to_context(context_idx):
                continue
            try:
                result = self.driver.execute_script(
                    """
                    const targetText = arguments[0];
                    const lower = (v) => (v || '').toString().trim().toLowerCase();
                    const isVisible = (el) => !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));

                    const all = Array.from(document.querySelectorAll('*'))
                      .filter((el) => isVisible(el));
                    const candidates = all.filter((el) => {
                      const txt = lower(el.innerText || el.textContent || '');
                      return txt.includes(targetText);
                    });
                    if (!candidates.length) return { clicked: false };

                    const scored = candidates
                      .map((el) => {
                        const tag = lower(el.tagName);
                        const role = lower(el.getAttribute('role'));
                        const txt = lower(el.innerText || el.textContent || '');
                        const isButtonLike = tag === 'button' || tag === 'a' || role === 'button';
                        const hasDisabled = lower(el.getAttribute('disabled')) === 'true' || lower(el.getAttribute('aria-disabled')) === 'true' || !!el.disabled;
                        const score = (isButtonLike ? 1000 : 0) - (hasDisabled ? 500 : 0) - txt.length;
                        return { el, score, hasDisabled, txt };
                      })
                      .sort((a, b) => b.score - a.score);

                    const chosen = scored.find((c) => !c.hasDisabled) || scored[0];
                    if (!chosen || chosen.hasDisabled) return { clicked: false };
                    chosen.el.click();
                    return { clicked: true, text: chosen.txt.slice(0, 120) };
                    """,
                    text_lower,
                )
                if result and result.get("clicked"):
                    logger.info(f"Clicked visible text target='{text_lower}' in context={context_idx}; result={result}")
                    self._webex_form_context_idx = context_idx
                    return True
            finally:
                try:
                    self.driver.switch_to.default_content()
                except Exception:
                    pass
        return False

    def _find_name_input_in_current_context(self):
        selectors = [
            (By.CSS_SELECTOR, "input[data-test='Name (required)']"),
            (By.CSS_SELECTOR, "input[autocomplete='name']"),
            (
                By.XPATH,
                "//*[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'name (required)')]/following::input[1]",
            ),
        ]
        for selector_type, selector in selectors:
            try:
                candidates = self.driver.find_elements(selector_type, selector)
            except Exception:
                continue
            for candidate in candidates:
                try:
                    if candidate.is_displayed() and candidate.is_enabled():
                        return candidate
                except Exception:
                    continue
        return None

    def _trigger_name_blur_sequence_in_current_context(self):
        name_input = self._find_name_input_in_current_context()
        if not name_input:
            return False
        try:
            name_input.click()
            name_input.send_keys(Keys.CONTROL, "a")
            name_input.send_keys(self.display_name)
            # Tab out to trigger client-side validation that enables Join.
            name_input.send_keys(Keys.TAB)
            time.sleep(0.2)
            try:
                body = self.driver.find_element(By.TAG_NAME, "body")
                body.click()
            except Exception:
                self.driver.execute_script("if (document.activeElement) { document.activeElement.blur(); }")
            logger.info("Triggered name-input blur/unfocus sequence")
            return True
        except Exception as e:
            logger.info(f"Failed name blur sequence: {e.__class__.__name__}")
            return False

    def _ensure_name_input_populated_in_current_context(self, join_button=None):
        try:
            result = self.driver.execute_script(
                """
                const joinBtn = arguments[0] || null;
                const displayName = arguments[1];
                const lower = (v) => (v || '').toString().trim().toLowerCase();
                const isVisible = (el) => !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));

                const allVisibleInputs = Array.from(document.querySelectorAll("input:not([type='hidden'])"))
                  .filter((el) => isVisible(el) && !el.disabled);
                if (!allVisibleInputs.length) return { filled: false, reason: 'no_visible_inputs' };

                const directSelectors = [
                  "input[data-test='Name (required)']",
                  "input[data-test*='Name']",
                  "input[autocomplete='name']",
                ];
                let byDirectSelector = null;
                for (const selector of directSelectors) {
                  const candidate = Array.from(document.querySelectorAll(selector))
                    .find((el) => isVisible(el) && !el.disabled);
                  if (candidate) {
                    byDirectSelector = candidate;
                    break;
                  }
                }

                const byLabel = allVisibleInputs.find((el) => {
                  const attrs = lower(el.getAttribute('aria-label')) + ' ' + lower(el.getAttribute('placeholder')) + ' ' + lower(el.getAttribute('name')) + ' ' + lower(el.getAttribute('data-test'));
                  return attrs.includes('name');
                });

                let byLayout = null;
                if (joinBtn && isVisible(joinBtn)) {
                  const jr = joinBtn.getBoundingClientRect();
                  byLayout = allVisibleInputs.find((el) => {
                    const r = el.getBoundingClientRect();
                    const roughlyAboveJoin = r.bottom <= (jr.top + 90);
                    const horizontallyAligned = Math.abs(r.left - jr.left) < 120;
                    return roughlyAboveJoin && horizontallyAligned;
                  }) || null;
                }

                const target = byDirectSelector || byLabel || byLayout || allVisibleInputs[0];
                const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
                if (setter) setter.call(target, '');
                else target.value = '';
                target.dispatchEvent(new Event('input', { bubbles: true }));

                if (setter) setter.call(target, displayName);
                else target.value = displayName;
                target.dispatchEvent(new Event('input', { bubbles: true }));
                target.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true, key: 'x' }));
                target.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, key: 'x' }));
                target.dispatchEvent(new Event('change', { bubbles: true }));
                target.blur();

                return {
                  filled: (target.value || '').trim().length > 0,
                  value_after: target.value || '',
                  strategy: byDirectSelector ? 'direct_selector' : (byLabel ? 'label' : (byLayout ? 'layout' : 'first_visible')),
                };
                """,
                join_button,
                self.display_name,
            )
            logger.info(f"Name-input populate result: {result}")
            return bool(result and result.get("filled"))
        except Exception:
            return False

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

    def click_join_from_browser_shadow_dom(self):
        logger.info("Trying shadow-DOM-aware click for browser-entry button")
        try:
            result = self.driver.execute_script(
                """
                const lower = (v) => (v || '').toString().trim().toLowerCase();
                const isVisible = (el) => !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
                const isDisabled = (el) => !!(el.disabled || el.getAttribute('aria-disabled') === 'true');

                const roots = [document];
                const all = [];
                while (roots.length) {
                  const root = roots.shift();
                  const nodes = root.querySelectorAll('*');
                  for (const n of nodes) {
                    all.push(n);
                    if (n.shadowRoot) roots.push(n.shadowRoot);
                  }
                }

                const candidates = [];
                for (const el of all) {
                  const tag = lower(el.tagName);
                  const role = lower(el.getAttribute('role'));
                  const type = lower(el.getAttribute('type'));
                  const clickable =
                    tag === 'button' ||
                    tag === 'a' ||
                    role === 'button' ||
                    (tag === 'input' && (type === 'submit' || type === 'button'));
                  if (!clickable || !isVisible(el) || isDisabled(el)) continue;

                  const text = lower(
                    (el.innerText || el.textContent || el.value || '') + ' ' + (el.getAttribute('aria-label') || '')
                  );
                  let score = -1;
                  if (text.includes('join from this browser')) score = 300;
                  else if (text.includes('join from your browser')) score = 250;
                  else if (text.includes('join from browser')) score = 200;
                  if (score < 0) continue;
                  if (text.includes('download')) score -= 100;

                  const rect = el.getBoundingClientRect();
                  candidates.push({
                    el,
                    text: text.slice(0, 120),
                    score,
                    top: rect.top || 0,
                    left: rect.left || 0,
                  });
                }

                candidates.sort((a, b) => {
                  if (b.score !== a.score) return b.score - a.score;
                  if (a.top !== b.top) return a.top - b.top;
                  return a.left - b.left;
                });

                if (!candidates.length) {
                  return { clicked: false, candidate_count: 0 };
                }

                const chosen = candidates[0];
                chosen.el.scrollIntoView({ block: 'center' });
                chosen.el.click();
                return {
                  clicked: true,
                  candidate_count: candidates.length,
                  chosen_text: chosen.text,
                  chosen_score: chosen.score,
                  chosen_href: chosen.el.getAttribute('href') || null,
                  chosen_onclick: chosen.el.getAttribute('onclick') || null,
                };
                """
            )
            logger.info(f"Shadow-DOM browser-entry click result: {result}")
            return bool(result and result.get("clicked"))
        except Exception as e:
            logger.info(f"Shadow-DOM browser-entry click failed: {e.__class__.__name__}")
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
        # Do NOT press Enter first here because that can confirm opening xdg-open on some builds.
        # Prefer dismiss/cancel semantics (alert dismiss + ESC), then proceed with browser-join flow.
        try:
            try:
                alert = self.driver.switch_to.alert
                alert.dismiss()
                logger.info("Dismissed external-app prompt via browser alert dismiss")
            except Exception:
                pass

            for _ in range(3):
                ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                time.sleep(0.15)
                ActionChains(self.driver).key_down(Keys.SHIFT).send_keys(Keys.TAB).key_up(Keys.SHIFT).perform()
                time.sleep(0.1)
                ActionChains(self.driver).send_keys(Keys.ENTER).perform()
                time.sleep(0.1)
                ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                time.sleep(0.1)

            logger.info("Attempted to cancel external-app launch prompt via ESC + SHIFT+TAB + ENTER strategy")
        except Exception as prompt_error:
            logger.info(f"Could not dismiss external-app prompt: {prompt_error.__class__.__name__}")

    def fill_guest_details(self):
        logger.info("Locating guest details form fields")
        name_input, context_idx = self._find_visible_element_in_any_context(By.XPATH, self.GUEST_NAME_INPUT_XPATH, self._webex_form_context_idx)
        if name_input is None:
            raise UiCouldNotLocateElementException("Exception raised in locate_element for guest_name_input", "guest_name_input")
        self._webex_form_context_idx = context_idx
        if not self._switch_to_context(context_idx):
            raise UiCouldNotLocateElementException("Could not switch to guest form context", "guest_name_input")
        name_input.clear()
        name_input.send_keys(self.display_name)
        name_input.send_keys(Keys.TAB)
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
        self.driver.switch_to.default_content()

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
        deadline = time.time() + 20
        last_prompt_cancel_at = 0
        last_blur_attempt_at = 0
        while time.time() < deadline:
            contexts = self._iter_context_indices()
            if self._webex_form_context_idx in contexts:
                contexts = [self._webex_form_context_idx] + [ctx for ctx in contexts if ctx != self._webex_form_context_idx]

            for context_idx in contexts:
                now = time.time()
                if now - last_prompt_cancel_at >= 6:
                    self.driver.switch_to.default_content()
                    self.dismiss_external_app_prompt_if_present()
                    last_prompt_cancel_at = now
                if not self._switch_to_context(context_idx):
                    continue
                try:
                    name_fill_result = self.driver.execute_script(
                        """
                        const displayName = arguments[0];
                        const lower = (v) => (v || '').toString().trim().toLowerCase();
                        const isVisible = (el) => !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
                        const roots = [document];
                        const nodes = [];
                        while (roots.length) {
                          const root = roots.shift();
                          const all = root.querySelectorAll('*');
                          for (const el of all) {
                            nodes.push(el);
                            if (el.shadowRoot) roots.push(el.shadowRoot);
                          }
                        }

                        const visibleInputs = nodes
                          .filter((el) => lower(el.tagName) === 'input' && isVisible(el) && !el.disabled && lower(el.getAttribute('type')) !== 'hidden');
                        const nameInput = visibleInputs.find((el) => {
                          const attrs =
                            lower(el.getAttribute('data-test')) + ' ' +
                            lower(el.getAttribute('autocomplete')) + ' ' +
                            lower(el.getAttribute('aria-label')) + ' ' +
                            lower(el.getAttribute('placeholder')) + ' ' +
                            lower(el.getAttribute('name'));
                          return attrs.includes('name');
                        }) || visibleInputs[0] || null;

                        if (nameInput) {
                          const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
                          if (setter) setter.call(nameInput, '');
                          else nameInput.value = '';
                          nameInput.dispatchEvent(new Event('input', { bubbles: true }));
                          if (setter) setter.call(nameInput, displayName);
                          else nameInput.value = displayName;
                          nameInput.dispatchEvent(new Event('input', { bubbles: true }));
                          nameInput.dispatchEvent(new Event('change', { bubbles: true }));
                          nameInput.blur();
                        }

                        const clickables = nodes.filter((el) => {
                          const tag = lower(el.tagName);
                          const role = lower(el.getAttribute('role'));
                          const type = lower(el.getAttribute('type'));
                          const clickable = tag === 'button' || tag === 'a' || role === 'button' || (tag === 'input' && (type === 'submit' || type === 'button'));
                          return clickable && isVisible(el);
                        });
                        return {
                          name_input_found: !!nameInput,
                          name_value: nameInput ? (nameInput.value || '') : null,
                          name_rect: nameInput ? (() => {
                            const r = nameInput.getBoundingClientRect();
                            return { top: r.top, left: r.left, bottom: r.bottom, right: r.right };
                          })() : null,
                        };
                        """,
                        self.display_name,
                    )

                    join_probe = self.driver.execute_script(
                        """
                        const lower = (v) => (v || '').toString().trim().toLowerCase();
                        const isVisible = (el) => !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
                        const roots = [document];
                        const nodes = [];
                        while (roots.length) {
                          const root = roots.shift();
                          const all = root.querySelectorAll('*');
                          for (const el of all) {
                            nodes.push(el);
                            if (el.shadowRoot) roots.push(el.shadowRoot);
                          }
                        }

                        const clickables = nodes.filter((el) => {
                          const tag = lower(el.tagName);
                          const role = lower(el.getAttribute('role'));
                          const type = lower(el.getAttribute('type'));
                          const clickable = tag === 'button' || tag === 'a' || role === 'button' || (tag === 'input' && (type === 'submit' || type === 'button'));
                          return clickable && isVisible(el);
                        });
                        const joinCandidates = clickables.filter((el) => {
                          const txt = lower((el.innerText || el.textContent || el.value || '') + ' ' + (el.getAttribute('aria-label') || ''));
                          return txt.includes('join meeting') || txt === 'join' || txt.startsWith('join ');
                        });
                        if (!joinCandidates.length) return { found: false };

                        const nameRect = arguments[0];
                        const score = (el) => {
                          const r = el.getBoundingClientRect();
                          if (!nameRect) return Math.abs(r.top) + Math.abs(r.left);
                          const verticalDelta = Math.max(0, r.top - nameRect.bottom);
                          const horizontalDelta = Math.abs(r.left - nameRect.left);
                          const abovePenalty = r.top < nameRect.bottom ? 10000 : 0;
                          return abovePenalty + (verticalDelta * 2) + horizontalDelta;
                        };
                        joinCandidates.sort((a, b) => score(a) - score(b));
                        const chosen = joinCandidates[0];
                        const rect = chosen.getBoundingClientRect();
                        const disabledAttr = lower(chosen.getAttribute('disabled'));
                        const ariaDisabled = lower(chosen.getAttribute('aria-disabled'));
                        const disabled = disabledAttr === 'true' || disabledAttr === 'disabled' || ariaDisabled === 'true' || !!chosen.disabled;
                        return {
                          found: true,
                          disabled,
                          center_x: rect.left + (rect.width / 2),
                          center_y: rect.top + (rect.height / 2),
                          text: lower(chosen.innerText || chosen.textContent || chosen.value || ''),
                        };
                        """,
                        (name_fill_result or {}).get("name_rect"),
                    )

                    if not join_probe or not join_probe.get("found"):
                        now = time.time()
                        if now - last_blur_attempt_at >= 1.5:
                            self._trigger_name_blur_sequence_in_current_context()
                            last_blur_attempt_at = now
                        continue

                    if join_probe.get("disabled"):
                        logger.info(
                            f"Join meeting button still disabled in context={context_idx}; "
                            f"name_fill_result={name_fill_result}; join_probe={join_probe}"
                        )
                        self._webex_form_context_idx = context_idx
                        now = time.time()
                        if now - last_blur_attempt_at >= 1.5:
                            self._trigger_name_blur_sequence_in_current_context()
                            last_blur_attempt_at = now
                        continue

                    x = float(join_probe.get("center_x"))
                    y = float(join_probe.get("center_y"))
                    self.driver.execute_cdp_cmd("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y, "button": "left"})
                    self.driver.execute_cdp_cmd("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
                    self.driver.execute_cdp_cmd("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})
                    logger.info(
                        f"Join meeting clicked via CDP mouse event in context={context_idx}; "
                        f"name_fill_result={name_fill_result}; join_probe={join_probe}"
                    )
                    self._webex_form_context_idx = context_idx
                    self.driver.switch_to.default_content()
                    return
                except Exception as click_js_error:
                    logger.info(f"JS join attempt failed in context={context_idx}: {click_js_error.__class__.__name__}")
                finally:
                    try:
                        self.driver.switch_to.default_content()
                    except Exception:
                        pass
            time.sleep(0.5)
        raise UiCouldNotLocateElementException("Timed out waiting for enabled join meeting button", "join_meeting_button")

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
        leave_button_xpath = (
            "//button[contains(translate(@aria-label, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'leave')]"
            "|//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'leave meeting')]"
        )
        last_wait_debug_capture_at = 0
        last_retry_click_at = 0
        while True:
            leave_button, _ = self._find_visible_element_in_any_context(By.XPATH, leave_button_xpath, self._webex_form_context_idx)
            if leave_button:
                logger.info("Leave button detected; joined state confirmed")
                self.driver.switch_to.default_content()
                return

            # Webex sometimes lands on recoverable transient overlays after clicking join.
            self.click_visible_button_by_text_in_any_context("got it", self._webex_form_context_idx)
            self.click_shadow_button_by_text_in_any_context("got it", self._webex_form_context_idx)
            self.click_any_visible_text_target_in_any_context("got it", self._webex_form_context_idx)
            if self.click_visible_button_by_text_in_any_context("try again", self._webex_form_context_idx) or self.click_shadow_button_by_text_in_any_context("try again", self._webex_form_context_idx):
                logger.info("Clicked 'Try again' while waiting for joined state")
            elif self.click_any_visible_text_target_in_any_context("try again", self._webex_form_context_idx):
                logger.info("Clicked generic 'Try again' target while waiting for joined state")

            now = time.time()
            if now - last_retry_click_at >= 8:
                if self.click_visible_button_by_text_in_any_context("join meeting", self._webex_form_context_idx) or self.click_shadow_button_by_text_in_any_context("join meeting", self._webex_form_context_idx):
                    logger.info("Re-clicked 'Join meeting' while waiting for joined state")
                    last_retry_click_at = now

            if now - last_wait_debug_capture_at >= 15:
                last_wait_debug_capture_at = now
                timestamp = int(now * 1000)
                screenshots_dir = "/tmp/screenshots"
                os.makedirs(screenshots_dir, exist_ok=True)
                try:
                    screenshot_path = f"{screenshots_dir}/webex_wait_join_{timestamp}.png"
                    self.driver.save_screenshot(screenshot_path)
                    logger.info(f"Captured wait-until-joined screenshot: {screenshot_path}")
                except Exception as screenshot_error:
                    logger.info(f"Failed to capture wait-until-joined screenshot: {screenshot_error.__class__.__name__}")
                try:
                    ui_signals = self.collect_ui_signals()
                    logger.info(f"wait_until_joined ui_signals={ui_signals}")
                except Exception as ui_signal_error:
                    logger.info(f"Failed to collect wait-until-joined ui_signals: {ui_signal_error.__class__.__name__}")

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
        self.install_external_protocol_guard()
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
        self.dismiss_external_app_prompt_if_present()
        try:
            clicked_browser_entry = self.click_join_from_this_browser_strict()
            if not clicked_browser_entry:
                clicked_browser_entry = self.click_join_from_browser_shadow_dom()
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
        self.log_external_protocol_guard_state("after_continue_in_browser")
        self.dismiss_external_app_prompt_if_present()
        post_browser_entry_settle_seconds = int(os.getenv("WEBEX_POST_BROWSER_ENTRY_SETTLE_SECONDS", "12"))
        logger.info(f"Waiting {post_browser_entry_settle_seconds}s for post-browser-entry page transition")
        time.sleep(post_browser_entry_settle_seconds)
        self.log_external_protocol_guard_state("after_settle")

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
            use_post_landing_fallback = os.getenv("WEBEX_USE_POST_LANDING_FALLBACK", "false").lower() == "true"
            if use_post_landing_fallback:
                navigated_to_landing = self.navigate_to_post_landing_page_if_available()
                if navigated_to_landing:
                    self.capture_flow_screenshot("after_post_landing_navigation")
                    self.fill_guest_details()

            allow_join_as_guest_fallback = os.getenv("WEBEX_ALLOW_JOIN_AS_GUEST_FALLBACK", "false").lower() == "true"
            if allow_join_as_guest_fallback:
                logger.info("Attempting join-as-guest gate path")
                self.click_join_as_guest()
                self.dismiss_cookie_banner_if_present()
                self.capture_flow_screenshot("after_join_as_guest_attempt")
                self.fill_guest_details()
            else:
                logger.info("Could not reach direct guest form; optional fallbacks are disabled")
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
