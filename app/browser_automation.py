#!/usr/bin/env python3
"""
Browser automation script for joining Zoom meetings.
Uses Playwright to control a headless Chromium browser.
"""

import os
import sys
import time
import re
import logging
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ZoomBrowserAutomation:
    """Automates joining Zoom meetings via browser."""
    
    def __init__(self, meeting_url, display_name='حمبوله'):
        self.meeting_url = meeting_url
        self.display_name = display_name
        self.browser = None
        self.context = None
        self.page = None
        self.joined = False
    
    def join_meeting(self):
        """Join the Zoom meeting."""
        with sync_playwright() as p:
            # Launch browser
            self.browser = p.chromium.launch(
                headless=False,  # Need visible browser for recording
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-accelerated-2d-canvas',
                    '--disable-gpu',
                    '--window-size=1920,1080',
                    '--start-maximized',
                    '--autoplay-policy=no-user-gesture-required',
                    '--use-fake-ui-for-media-stream',  # Auto-allow media
                    '--use-fake-device-for-media-stream',
                ]
            )
            
            # Create context with permissions
            self.context = self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                permissions=['microphone', 'camera'],
                user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            
            self.page = self.context.new_page()
            # Auto-dismiss any JS dialogs (e.g., xdg-open prompts)
            self.page.on("dialog", lambda dialog: dialog.dismiss())
            
            try:
                target_url = self._to_web_client_url(self.meeting_url)
                logger.info(f"Navigating to: {target_url}")
                self.page.goto(target_url, wait_until='networkidle', timeout=60000)
                
                # Wait for page to load
                time.sleep(3)
                
                # Handle different Zoom join flows
                self._handle_join_flow()
                
                # Monitor for meeting end
                self._monitor_meeting()
                
            except PlaywrightTimeout as e:
                logger.error(f"Timeout during meeting join: {e}")
                raise
            except Exception as e:
                logger.error(f"Error during meeting: {e}")
                raise
            finally:
                if self.browser:
                    self.browser.close()

    def _to_web_client_url(self, url: str) -> str:
        """Prefer the web client join URL to avoid native app prompts."""
        try:
            match = re.search(r'/j/(\d+)', url)
            if not match:
                return url
            meeting_id = match.group(1)
            pwd_match = re.search(r'pwd=([^&]+)', url)
            pwd = pwd_match.group(1) if pwd_match else ''
            base = url.split('/j/')[0]
            wc_url = f"{base}/wc/join/{meeting_id}"
            if pwd:
                wc_url += f"?pwd={pwd}"
            return wc_url
        except Exception:
            return url
    
    def _handle_join_flow(self):
        """Handle the Zoom web client join flow."""
        try:
            # Wait for page to load
            time.sleep(3)
            
            # First, dismiss any browser dialogs by pressing Escape
            try:
                self.page.keyboard.press('Escape')
                time.sleep(0.5)
                self.page.keyboard.press('Escape')
                logger.info("Pressed Escape to dismiss dialogs")
            except Exception:
                pass
            
            # Handle cookie consent - click DECLINE to get rid of it faster
            cookie_selectors = [
                'text="DECLINE COOKIES"',
                'text="Decline Cookies"',
                'text="ACCEPT COOKIES"',
                'text="Accept Cookies"',
                '#onetrust-accept-btn-handler',
            ]
            
            time.sleep(1)
            for selector in cookie_selectors:
                try:
                    element = self.page.locator(selector).first
                    if element.is_visible(timeout=2000):
                        element.click()
                        logger.info(f"Clicked cookie button: {selector}")
                        time.sleep(1)
                        break
                except Exception:
                    continue
            
            # Close the "Did not open Zoom Workplace app?" popup by clicking the X
            try:
                close_popup = self.page.locator('button:has-text("×"), .close, [aria-label="Close"]').first
                if close_popup.is_visible(timeout=2000):
                    close_popup.click()
                    logger.info("Closed popup dialog")
                    time.sleep(1)
            except Exception:
                pass
            
            # CRITICAL: Click "Join from your browser" link
            # This link appears at the bottom of the page
            time.sleep(2)
            
            # Try multiple approaches to find and click the link
            clicked = False
            
            # Method 1: Direct text match
            try:
                link = self.page.get_by_text("Join from your browser", exact=False)
                if link.is_visible(timeout=3000):
                    link.click()
                    clicked = True
                    logger.info("Clicked 'Join from your browser' via get_by_text")
            except Exception as e:
                logger.debug(f"Method 1 failed: {e}")
            
            # Method 2: CSS selector for the link
            if not clicked:
                try:
                    link = self.page.locator('a[href*="wc/join"]').first
                    if link.is_visible(timeout=2000):
                        link.click()
                        clicked = True
                        logger.info("Clicked browser join via href selector")
                except Exception as e:
                    logger.debug(f"Method 2 failed: {e}")
            
            # Method 3: JavaScript click
            if not clicked:
                try:
                    result = self.page.evaluate('''() => {
                        // Find all links and spans containing "browser"
                        const elements = document.querySelectorAll('a, span, div');
                        for (const el of elements) {
                            const text = el.textContent.toLowerCase();
                            if (text.includes('join from your browser') || 
                                (text.includes('browser') && el.tagName === 'A')) {
                                el.click();
                                return 'clicked: ' + el.textContent;
                            }
                        }
                        // Try the specific link pattern
                        const joinLink = document.querySelector('a[href*="/wc/"]');
                        if (joinLink) {
                            joinLink.click();
                            return 'clicked wc link';
                        }
                        return 'not found';
                    }''')
                    logger.info(f"JavaScript click result: {result}")
                    if 'clicked' in result:
                        clicked = True
                except Exception as e:
                    logger.debug(f"Method 3 failed: {e}")
            
            # Method 4: Navigate directly to web client URL
            if not clicked:
                try:
                    current_url = self.page.url
                    # Convert standard URL to web client URL
                    # https://us06web.zoom.us/j/123?pwd=xxx -> https://us06web.zoom.us/wc/join/123?pwd=xxx
                    import re
                    match = re.search(r'/j/(\d+)', current_url)
                    if match:
                        meeting_id = match.group(1)
                        # Extract password if present
                        pwd_match = re.search(r'pwd=([^&]+)', current_url)
                        pwd = pwd_match.group(1) if pwd_match else ''
                        
                        # Build web client URL
                        base = current_url.split('/j/')[0]
                        wc_url = f"{base}/wc/join/{meeting_id}"
                        if pwd:
                            wc_url += f"?pwd={pwd}"
                        
                        logger.info(f"Navigating directly to web client: {wc_url}")
                        self.page.goto(wc_url, wait_until='networkidle', timeout=30000)
                        clicked = True
                except Exception as e:
                    logger.error(f"Method 4 failed: {e}")
            
            time.sleep(5)  # Wait for web client to load
            
            # Now we should be in the web client - enter name
            name_selectors = [
                '#inputname',
                'input[placeholder*="name"]',
                'input[placeholder*="Name"]',
                '#join-confno',
                'input[type="text"]',
            ]
            
            for selector in name_selectors:
                try:
                    element = self.page.locator(selector).first
                    if element.is_visible(timeout=3000):
                        element.clear()
                        element.fill(self.display_name)
                        logger.info(f"Entered name in: {selector}")
                        time.sleep(1)
                        break
                except Exception:
                    continue

            # Turn off mic/cam on the preview toolbar BEFORE joining
            self._ensure_preview_controls_off()
            
            # Click the Join button
            join_selectors = [
                'button:has-text("Join")',
                '#joinBtn',
                'button[type="submit"]',
                '.btn-primary:has-text("Join")',
                'button.preview-join-button',
            ]
            
            for selector in join_selectors:
                try:
                    element = self.page.locator(selector).first
                    if element.is_visible(timeout=3000):
                        element.click()
                        logger.info(f"Clicked join button: {selector}")
                        self.joined = True
                        time.sleep(5)
                        break
                except Exception:
                    continue
            
            # Handle "Join Audio" popup if present
            audio_selectors = [
                'text="Join Audio by Computer"',
                'text="Join with Computer Audio"',
                'button:has-text("Join Audio")',
                'button:has-text("Computer Audio")',
            ]
            
            time.sleep(3)
            for selector in audio_selectors:
                try:
                    element = self.page.locator(selector).first
                    if element.is_visible(timeout=3000):
                        element.click()
                        logger.info(f"Clicked audio join: {selector}")
                        break
                except Exception:
                    continue
            
            # Mute mic and stop camera to avoid broadcasting
            self._mute_and_stop_video()

            # Dismiss any blocking modals (e.g., AI companion transcript notice)
            self._dismiss_popups()

            logger.info("Successfully joined meeting")
            
        except Exception as e:
            logger.error(f"Error in join flow: {e}")
            # Continue anyway - might still be able to record

    def _dismiss_popups(self):
        """Dismiss common blocking popups (e.g., AI companion transcript)."""
        try:
            popup_selectors = [
                'text="This meeting is being transcribed"',
                'text="AI Companion"',
                'text="transcript"',
            ]
            button_selectors = [
                'button:has-text("OK")',
                'button:has-text("Ok")',
                'button:has-text("Got it")',
                '.ReactModal__Content button',
            ]
            # If popup text exists, click OK
            for psel in popup_selectors:
                try:
                    p = self.page.locator(psel).first
                    if p.is_visible(timeout=1000):
                        for bsel in button_selectors:
                            try:
                                b = self.page.locator(bsel).first
                                if b.is_visible(timeout=1000):
                                    b.click()
                                    logger.info(f"Dismissed popup via {bsel}")
                                    return
                            except Exception:
                                continue
                except Exception:
                    continue
            # Fallback: click any visible OK button
            try:
                ok_btn = self.page.get_by_text("OK", exact=True)
                if ok_btn.is_visible(timeout=1000):
                    ok_btn.click()
                    logger.info("Dismissed popup via OK text")
            except Exception:
                pass
        except Exception as e:
            logger.debug(f"Popup dismiss failed: {e}")

    def _mute_and_stop_video(self):
        """Ensure microphone and camera are off."""
        try:
            controls = {
                'audio': [
                    'button[aria-label*="mute"]',
                    'button[aria-label*="Mute"]',
                    'button:has-text("Mute")',
                    'button[aria-label*="Unmute"]',  # when already muted, label often says Unmute
                ],
                'video': [
                    'button[aria-label*="stop video"]',
                    'button[aria-label*="Stop Video"]',
                    'button:has-text("Stop Video")',
                    'button[aria-label*="Start Video"]',  # when already off
                ],
            }

            def ensure_off(label, selectors):
                for selector in selectors:
                    try:
                        btn = self.page.locator(selector).first
                        if not btn.is_visible(timeout=1200):
                            continue

                        state = (btn.get_attribute('aria-label') or '' or '').lower()
                        state_text = ''
                        try:
                            state_text = (btn.inner_text() or '').lower()
                        except Exception:
                            pass
                        combined = state + ' ' + state_text

                        if label == 'video':
                            # If label says stop video, video is ON -> click to turn OFF.
                            if 'stop video' in combined:
                                btn.click()
                                logger.info(f"Turned video off via {selector}")
                                time.sleep(0.3)
                                return True
                            # If it says start video, it is already OFF.
                            if 'start video' in combined:
                                return True
                        else:  # audio
                            # If label says mute (and not unmute), audio is ON -> click to mute.
                            if 'mute' in combined and 'unmute' not in combined:
                                btn.click()
                                logger.info(f"Muted audio via {selector}")
                                time.sleep(0.3)
                                return True
                            # If it says unmute, it's already muted.
                            if 'unmute' in combined:
                                return True
                    except Exception:
                        continue
                return False

            # Attempt twice to ensure state sticks (Zoom sometimes ignores first click)
            for _ in range(2):
                ensure_off('video', controls['video'])
                ensure_off('audio', controls['audio'])
                time.sleep(0.2)
        except Exception as e:
            logger.debug(f"Mute/stop video failed: {e}")

    def _ensure_preview_controls_off(self):
        """On the pre-join screen, explicitly click the preview toolbar mute/stop buttons if present."""
        try:
            preview_controls = [
                ('audio', [
                    'button[aria-label*="Mute"]',
                    'button[aria-label*="mute"]',
                    'button:has-text("Mute")',
                ]),
                ('video', [
                    'button[aria-label*="Stop Video"]',
                    'button[aria-label*="stop video"]',
                    'button:has-text("Stop Video")',
                ]),
            ]

            for label, selectors in preview_controls:
                for selector in selectors:
                    try:
                        btn = self.page.locator(selector).first
                        if btn.is_visible(timeout=1200):
                            btn.click()
                            logger.info(f"Preview: turned off {label} via {selector}")
                            time.sleep(0.3)
                            break
                    except Exception:
                        continue
        except Exception as e:
            logger.debug(f"Preview control toggle failed: {e}")
    
    def _monitor_meeting(self):
        """Monitor the meeting and detect when it ends."""
        logger.info("Monitoring meeting...")
        
        end_indicators = [
            'text="This meeting has been ended"',
            'text="The host has ended this meeting"',
            'text="Meeting has ended"',
            'text="You have been removed"',
            'text="The meeting has ended"',
            'text="Join Meeting"',  # landing page after end
            '.meeting-ended',
            '#wc-footer:not(:visible)',  # Footer disappears when meeting ends
        ]

        check_interval = 3  # seconds (faster detection)
        max_duration = 8 * 3600  # 8 hours max
        elapsed = 0
        
        while elapsed < max_duration:
            try:
                # Clear any blocking popups
                self._dismiss_popups()

                # Check for meeting end indicators
                for selector in end_indicators:
                    try:
                        element = self.page.locator(selector).first
                        if element.is_visible(timeout=800):
                            logger.info(f"Meeting ended: {selector}")
                            try:
                                # Click OK/close if present to exit cleanly
                                ok_btn = self.page.get_by_text("OK", exact=False)
                                if ok_btn.is_visible(timeout=500):
                                    ok_btn.click()
                            except Exception:
                                pass
                            return
                    except Exception:
                        continue

                # If we already joined and now see a Join Meeting landing (no footer), treat as ended
                if self.joined:
                    try:
                        join_btn = self.page.get_by_text("Join Meeting", exact=False)
                        footer_visible = False
                        try:
                            footer = self.page.locator('#wc-footer').first
                            footer_visible = footer.is_visible(timeout=500)
                        except Exception:
                            footer_visible = False
                        if join_btn.is_visible(timeout=800) and not footer_visible:
                            logger.info("Meeting ended: redirected to join landing")
                            return
                    except Exception:
                        pass

                # Text scan fallback (handles modals or nested frames)
                try:
                    body_text = (self.page.inner_text('body') or '').lower()
                    if any(phrase in body_text for phrase in [
                        'meeting has been ended',
                        'host has ended this meeting',
                        'meeting has ended by host',
                        'meeting has ended',
                    ]):
                        logger.info("Meeting ended detected via text scan")
                        try:
                            ok_btn = self.page.get_by_text("OK", exact=False)
                            if ok_btn.is_visible(timeout=500):
                                ok_btn.click()
                        except Exception:
                            pass
                        return
                except Exception:
                    pass
                
                # Check if page has navigated away
                current_url = self.page.url
                if 'zoom.us' not in current_url:
                    logger.info("Navigated away from Zoom")
                    return
                
                time.sleep(check_interval)
                elapsed += check_interval
                
                if elapsed % 300 == 0:  # Log every 5 minutes
                    logger.info(f"Meeting still active. Elapsed: {elapsed // 60} minutes")
                    
            except Exception as e:
                logger.error(f"Error monitoring meeting: {e}")
                # Continue monitoring
                time.sleep(check_interval)
                elapsed += check_interval
        
        logger.info("Maximum recording duration reached")


def main():
    """Main entry point."""
    meeting_url = os.environ.get('MEETING_URL')
    display_name = os.environ.get('DISPLAY_NAME', 'ZoomRec Bot')
    
    if not meeting_url:
        logger.error("MEETING_URL environment variable not set")
        sys.exit(1)
    
    logger.info(f"Starting browser automation for: {meeting_url}")
    
    automation = ZoomBrowserAutomation(meeting_url, display_name)
    automation.join_meeting()


if __name__ == '__main__':
    main()
