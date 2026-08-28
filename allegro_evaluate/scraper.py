"""Playwright-based scraper for Allegro search result pages.

Allegro is a heavily JS-driven site, so we drive real Chromium through
Playwright (sync API) instead of plain HTTP. The scraper is deliberately
testable: pass a ``browser`` instance into the constructor to skip the real
launch, and the extraction helpers operate on Playwright ``ElementHandle``-like
objects so tests can substitute fakes.

Behaviour notes:
- Pagination follows ``?p=N`` on :data:`SEARCH_URL`, up to ``max_pages``.
- The total number of returned listings is capped at ``settings.max_listings``.
- A random delay is applied between page requests (``scrape_delay_min`` /
  ``scrape_delay_max``) and the user agent is rotated from
  ``settings.user_agents``.
- Cookie-consent banners are dismissed when a known button is present.
- Anti-bot walls (Allegro "waiting room", captcha redirects) raise
  :class:`ScraperError`.
"""

from __future__ import annotations

import random
import re
import time
from urllib.parse import urlencode, urljoin

import structlog
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from allegro_evaluate.config import Settings
from allegro_evaluate.logging import get_logger
from allegro_evaluate.models import Listing
from allegro_evaluate.utils import clean_whitespace, parse_price_from_text

BASE_URL = "https://allegro.pl"
SEARCH_URL = "https://allegro.pl/listing"

# Primary selector for a single search-result card; Allegro marks these with
# a `data-listing-id` attribute. The fallbacks cover older layout variants.
LISTING_SELECTOR = "article[data-listing-id]"
LISTING_FALLBACK_SELECTORS = (
    "div[data-listing-id]",
    "article[class*='listing']",
    "div[class*='listing__item']",
)

TITLE_SELECTOR = "h2"
LINK_SELECTOR = "a[href*='/oferta/']"
PRICE_SELECTOR = "[data-testid*='price'], [class*='price'], span[class*='cennik']"
SNIPPET_SELECTOR = "[class*='snippet'], [class*='description']"
IMAGE_SELECTOR = "img"

# Known "accept" buttons on the cookie-consent dialog, tried in order.
COOKIE_SELECTORS = (
    '[data-role="accept-consent"]',
    'button:has-text("Akceptuję i przechodzę")',
    'button:has-text("Akceptuję")',
    'button:has-text("Zgadzam się")',
    'button:has-text("Akceptuj wszystkie")',
)

# URL fragments that indicate Allegro's anti-bot "waiting room" / login wall.
BLOCK_URL_FRAGMENTS = ("spoczekalnia", "captcha", "/logowanie")

# Allegro offer URLs end in `-<numeric id>`, e.g. `/oferta/laptop-1234567890`.
_ID_FROM_URL_RE = re.compile(r"-(\d{6,})$")


class ScraperError(RuntimeError):
    """Raised when the scraper hits an unrecoverable error (e.g. anti-bot wall)."""


class AllegroScraper:
    """Scrape Allegro search results with Playwright."""

    def __init__(
        self,
        settings: Settings,
        browser: object | None = None,
        logger: structlog.typing.FilteringBoundLogger | None = None,
    ) -> None:
        """Args:
            settings: Runtime configuration (delays, pagination, user agents).
            browser: Optional pre-launched Playwright ``Browser``. When given,
                the scraper does not launch or close it (used by tests).
        """
        self.settings = settings
        self.log = logger or get_logger("allegro_evaluate.scraper")
        self._browser = browser
        self._playwright = None

    # -- public API ---------------------------------------------------------

    def scrape(self, query: str, max_pages: int | None = None) -> list[Listing]:
        """Search Allegro and return up to ``settings.max_listings`` listings.

        Args:
            query: Core search string for the Allegro search box.
            max_pages: Page limit override (defaults to ``settings.max_pages``).

        Raises:
            ValueError: if ``query`` is empty.
            ScraperError: if an anti-bot wall is detected.
        """
        query = query.strip()
        if not query:
            raise ValueError("query must not be empty")
        max_pages = max_pages or self.settings.max_pages

        browser = self._browser
        owns_browser = browser is None
        if browser is None:
            self._playwright = sync_playwright().start()
            browser = self._playwright.chromium.launch(headless=self.settings.headless)

        try:
            return self._scrape_with_browser(browser, query, max_pages)
        finally:
            if owns_browser:
                try:
                    browser.close()
                finally:
                    self._playwright.stop()
                    self._playwright = None

    # -- internals ----------------------------------------------------------

    def _scrape_with_browser(self, browser: object, query: str, max_pages: int) -> list[Listing]:
        user_agent = random.choice(self.settings.user_agents) if self.settings.user_agents else None
        context_kwargs: dict[str, object] = {
            "locale": "pl-PL",
            "viewport": {"width": 1366, "height": 900},
        }
        if user_agent:
            context_kwargs["user_agent"] = user_agent

        context = browser.new_context(**context_kwargs)
        page = context.new_page()
        page.set_default_timeout(self.settings.page_load_timeout)

        listings: list[Listing] = []
        seen: set[str] = set()
        try:
            for page_num in range(1, max_pages + 1):
                if len(listings) >= self.settings.max_listings:
                    break

                url = self._search_url(query, page_num)
                self.log.info("fetch_page", url=url, page=page_num)
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=self.settings.page_load_timeout)
                except (PlaywrightTimeoutError, PlaywrightError) as exc:
                    self.log.warning("page_load_failed", page=page_num, error=str(exc))
                    continue

                if page_num == 1:
                    self._try_accept_cookies(page)
                self._detect_block(page, url)

                found = self._extract_listings_from_page(page)
                fresh = [listing for listing in found if listing.id not in seen]
                for listing in fresh:
                    seen.add(listing.id)
                listings.extend(fresh)
                self.log.info("page_scraped", page=page_num, found=len(found), fresh=len(fresh))

                if not found:
                    break
                if page_num < max_pages and len(listings) < self.settings.max_listings:
                    self._sleep()
        finally:
            context.close()

        return listings[: self.settings.max_listings]

    def _search_url(self, query: str, page_num: int = 1) -> str:
        """Build a ``/listing`` search URL with optional pagination."""
        params: dict[str, str] = {"string": query}
        if page_num > 1:
            params["p"] = str(page_num)
        return f"{SEARCH_URL}?{urlencode(params)}"

    def _try_accept_cookies(self, page: object) -> None:
        """Click the cookie-consent accept button if one is present."""
        for selector in COOKIE_SELECTORS:
            button = page.query_selector(selector)
            if button is not None:
                try:
                    button.click()
                except Exception:  # noqa: BLE001 - never fail the scrape over a banner
                    self.log.debug("cookie_click_failed", selector=selector)
                else:
                    self.log.info("cookie_consent_accepted", selector=selector)
                return
        self.log.debug("no_cookie_consent_button_found")

    def _detect_block(self, page: object, url: str) -> None:
        """Raise :class:`ScraperError` when an anti-bot wall redirected us."""
        current_url = (page.url or "") if hasattr(page, "url") else ""
        for fragment in BLOCK_URL_FRAGMENTS:
            if fragment in current_url.lower():
                raise ScraperError(
                    f"anti-bot wall detected at {url} (redirected to {current_url})"
                )

    def _sleep(self) -> None:
        """Randomised delay between page requests (skipped when zeroed)."""
        if self.settings.scrape_delay_max <= 0 and self.settings.scrape_delay_min <= 0:
            return
        delay = random.uniform(self.settings.scrape_delay_min, self.settings.scrape_delay_max)
        self.log.debug("rate_limit_delay", seconds=round(delay, 2))
        time.sleep(delay)

    # -- extraction ---------------------------------------------------------

    def _extract_listings_from_page(self, page: object) -> list[Listing]:
        elements = page.query_selector_all(LISTING_SELECTOR)
        if not elements:
            for selector in LISTING_FALLBACK_SELECTORS:
                elements = page.query_selector_all(selector)
                if elements:
                    break

        listings: list[Listing] = []
        for element in elements:
            listing = self._listing_from_element(element)
            if listing is not None:
                listings.append(listing)
        return listings

    def _listing_from_element(self, element: object) -> Listing | None:
        """Build a :class:`Listing` from a single search-result card element."""
        listing_id = element.get_attribute("data-listing-id") or ""

        title_el = element.query_selector(TITLE_SELECTOR)
        if title_el is None:
            title_el = element.query_selector(LINK_SELECTOR)
        title = title_el.inner_text().strip() if title_el is not None else ""

        link_el = element.query_selector(LINK_SELECTOR)
        href = link_el.get_attribute("href") or "" if link_el is not None else ""
        url = urljoin(BASE_URL, href) if href else ""

        if not listing_id:
            listing_id = _id_from_url(url)
        if not listing_id:
            return None

        price_el = element.query_selector(PRICE_SELECTOR)
        price = parse_price_from_text(price_el.inner_text()) if price_el is not None else None

        snippet_el = element.query_selector(SNIPPET_SELECTOR)
        snippet = clean_whitespace(snippet_el.inner_text()) if snippet_el is not None else ""

        image_url = None
        img_el = element.query_selector(IMAGE_SELECTOR)
        if img_el is not None:
            image_url = img_el.get_attribute("src") or img_el.get_attribute("data-src")
        if image_url and image_url.startswith("//"):
            image_url = "https:" + image_url

        return Listing(
            id=listing_id,
            title=title,
            price=price,
            description=snippet,
            url=url,
            image_url=image_url,
        )


def _id_from_url(url: str) -> str:
    """Best-effort listing id extraction from an offer URL tail."""
    match = _ID_FROM_URL_RE.search(url)
    return match.group(1) if match else ""
