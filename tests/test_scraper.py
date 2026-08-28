"""Tests for the Playwright scraper using faked pages/elements."""

from __future__ import annotations

import pytest

from allegro_evaluate.scraper import SEARCH_URL, AllegroScraper, ScraperError
from tests.fakes import FakeBrowser, FakeElement, FakePage


def _card(
    listing_id: str,
    title: str,
    price_text: str = "1 999,00 zł",
    href: str = "",
    image_src: str = "https://img.allegro.example/p.jpg",
) -> FakeElement:
    href = href or f"/oferta/{title.lower().replace(' ', '-')}-{listing_id}"
    return FakeElement(
        attrs={"data-listing-id": listing_id},
        children={
            "h2": FakeElement(text=title),
            "a[href*='/oferta/']": FakeElement(attrs={"href": href}),
            "[data-testid*='price'], [class*='price'], span[class*='cennik']": FakeElement(text=price_text),
            "[class*='snippet'], [class*='description']": FakeElement(text="Stan: nowy, gwarancja 24 mies."),
            "img": FakeElement(attrs={"src": image_src}),
        },
    )


# ---------------------------------------------------------------- url building


def test_search_url_builds_query(settings):
    scraper = AllegroScraper(settings)
    assert scraper._search_url("laptop") == f"{SEARCH_URL}?string=laptop"


def test_search_url_adds_page_param(settings):
    scraper = AllegroScraper(settings)
    assert scraper._search_url("laptop", 2) == f"{SEARCH_URL}?string=laptop&p=2"


def test_search_url_urlencodes_query(settings):
    scraper = AllegroScraper(settings)
    assert scraper._search_url("laptop 16GB RAM") == f"{SEARCH_URL}?string=laptop+16GB+RAM"


# --------------------------------------------------------------- extraction


def test_listing_from_element_extracts_fields(settings):
    scraper = AllegroScraper(settings)
    element = _card("1234567890", "Laptop Lenovo 16GB RAM", price_text="2 999,00 zł")

    listing = scraper._listing_from_element(element)

    assert listing is not None
    assert listing.id == "1234567890"
    assert listing.title == "Laptop Lenovo 16GB RAM"
    assert listing.price == 2999.0
    assert listing.description == "Stan: nowy, gwarancja 24 mies."
    assert listing.url == "https://allegro.pl/oferta/laptop-lenovo-16gb-ram-1234567890"
    assert listing.image_url == "https://img.allegro.example/p.jpg"


def test_listing_id_falls_back_to_url_tail(settings):
    scraper = AllegroScraper(settings)
    element = FakeElement(
        attrs={},
        children={
            "h2": FakeElement(text="Dell XPS 13"),
            "a[href*='/oferta/']": FakeElement(attrs={"href": "/oferta/dell-xps-9876543210"}),
            "img": FakeElement(attrs={"src": "//img.allegro.example/p.jpg"}),
        },
    )

    listing = scraper._listing_from_element(element)

    assert listing is not None
    assert listing.id == "9876543210"
    assert listing.image_url == "https://img.allegro.example/p.jpg"


def test_listing_without_id_or_url_is_skipped(settings):
    scraper = AllegroScraper(settings)
    element = FakeElement(attrs={}, children={"h2": FakeElement(text="No id here")})

    assert scraper._listing_from_element(element) is None


def test_extract_listings_from_page(settings):
    scraper = AllegroScraper(settings)
    page = FakePage(listing_elements=[_card("1", "A"), _card("2", "B")])

    listings = scraper._extract_listings_from_page(page)

    assert [listing.id for listing in listings] == ["1", "2"]


# ------------------------------------------------------------------- scraping


def test_scrape_with_fake_browser(settings):
    page = FakePage(listing_elements=[_card("1", "Laptop A"), _card("2", "Laptop B")])
    scraper = AllegroScraper(settings, browser=FakeBrowser(page))

    listings = scraper.scrape("laptop", max_pages=1)

    assert [listing.id for listing in listings] == ["1", "2"]
    assert listings[0].title == "Laptop A"
    assert page.goto_calls == [f"{SEARCH_URL}?string=laptop"]


def test_scrape_stops_when_no_listings_found(settings):
    page = FakePage(listing_elements=[])
    scraper = AllegroScraper(settings, browser=FakeBrowser(page))

    assert scraper.scrape("nothing", max_pages=5) == []
    assert len(page.goto_calls) == 1


def test_scrape_caps_at_max_listings(settings):
    settings.max_listings = 4
    page = FakePage(
        listing_elements=[_card(str(i), f"Item {i}") for i in range(5)]
    )
    scraper = AllegroScraper(settings, browser=FakeBrowser(page))

    listings = scraper.scrape("laptop", max_pages=2)

    assert len(listings) == 4


def test_scrape_empty_query_raises(settings):
    scraper = AllegroScraper(settings)
    with pytest.raises(ValueError):
        scraper.scrape("   ")


# --------------------------------------------------------- consent and blocks


def test_cookie_consent_button_is_clicked(settings):
    button = FakeElement(text="Akceptuję")
    page = FakePage(cookie_elements={'button:has-text("Akceptuję")': button})
    scraper = AllegroScraper(settings)

    scraper._try_accept_cookies(page)

    assert button.clicked


def test_cookie_consent_absent_is_ok(settings):
    scraper = AllegroScraper(settings)
    scraper._try_accept_cookies(FakePage())  # should not raise


def test_detect_block_raises_on_waiting_room(settings):
    page = FakePage(url="https://allegro.pl/spoczekalnia/?redirect=%2Flisting")
    scraper = AllegroScraper(settings)

    with pytest.raises(ScraperError):
        scraper._detect_block(page, f"{SEARCH_URL}?string=laptop")


def test_detect_block_passes_on_normal_page(settings):
    page = FakePage(url=f"{SEARCH_URL}?string=laptop")
    scraper = AllegroScraper(settings)

    scraper._detect_block(page, f"{SEARCH_URL}?string=laptop")  # should not raise
