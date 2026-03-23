# scraper/base.py
# ─────────────────────────────────────────────────────────────────────────────
# Shared browser setup with anti-bot measures for all scrapers.
#
# HOW SITES TRY TO BLOCK SCRAPERS:
# 1. Detect navigator.webdriver = true (Playwright's fingerprint)
# 2. Check user-agent for "HeadlessChrome" or "Playwright"
# 3. Monitor mouse movements — bots don't move mice
# 4. Check canvas fingerprints, fonts, WebGL
# 5. Rate-limit by IP after too many requests
# 6. CAPTCHAs (rare on gov sites, common on commercial)
#
# OUR COUNTERMEASURES:
# 1. Patch navigator.webdriver to undefined via JS injection
# 2. Realistic user-agent string
# 3. Random delays between requests (1.5-4 seconds)
# 4. Realistic viewport and language settings
# 5. Disable automation flags in Chromium args
# ─────────────────────────────────────────────────────────────────────────────

import asyncio
import random
from playwright.async_api import Browser, BrowserContext, Page

# Realistic user agents — rotate these to avoid fingerprinting
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.130 Safari/537.36 Edg/120.0.0.0",
]

# Chromium launch args that disable automation detection
STEALTH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-dev-shm-usage",
    "--no-sandbox",
    "--disable-infobars",
    "--disable-extensions",
    "--disable-gpu",
    "--window-size=1366,768",
    "--disable-web-security",
    "--disable-features=IsolateOrigins,site-per-process",
]

# JavaScript to inject — patches common bot-detection checks
STEALTH_JS = """
// Hide webdriver flag (most important — checked by every anti-bot system)
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined,
});

// Fake plugins array (real browsers have plugins, headless has none)
Object.defineProperty(navigator, 'plugins', {
    get: () => [1, 2, 3, 4, 5],
});

// Fake language (headless Chrome often has empty languages)
Object.defineProperty(navigator, 'languages', {
    get: () => ['en-IN', 'en-US', 'en'],
});

// Fix chrome object (headless doesn't have window.chrome)
window.chrome = {
    runtime: {},
    loadTimes: function() {},
    csi: function() {},
    app: {},
};

// Prevent detection via permissions API
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications' ?
        Promise.resolve({ state: Notification.permission }) :
        originalQuery(parameters)
);
"""


async def create_stealth_context(browser: Browser) -> BrowserContext:
    """
    Create a browser context with anti-bot measures applied.
    Call this instead of browser.new_context() in every scraper.
    """
    context = await browser.new_context(
        user_agent=random.choice(USER_AGENTS),
        viewport={"width": 1366, "height": 768},
        locale="en-IN",
        timezone_id="Asia/Kolkata",
        # Pretend to accept common content types
        extra_http_headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-IN,en-US;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Upgrade-Insecure-Requests": "1",
        }
    )

    # Inject stealth JS before every page load
    await context.add_init_script(STEALTH_JS)
    return context


async def human_delay(min_s: float = 1.5, max_s: float = 4.0):
    """
    Wait a random amount of time between requests.
    Mimics human reading/thinking time — prevents rate limiting.
    """
    await asyncio.sleep(random.uniform(min_s, max_s))


async def safe_goto(
    page: Page,
    url: str,
    timeout: int = 45000,
    wait: str = "domcontentloaded"
) -> bool:
    """
    Navigate to a URL with error handling.
    Returns True if successful, False if failed.

    WHY domcontentloaded INSTEAD OF networkidle:
    networkidle waits until no network requests for 500ms — but modern
    sites constantly poll for analytics, ads, etc. so it NEVER fires.
    domcontentloaded fires when the main HTML is parsed and ready,
    which is all we need to extract text.
    """
    try:
        await page.goto(url, wait_until=wait, timeout=timeout)
        return True
    except Exception as e:
        print(f"    ⚠️  Navigation failed for {url[-60:]}: {type(e).__name__}")
        return False
