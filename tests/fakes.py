"""Shared fakes and helpers for the test suite.

Tests import these instead of hitting the network: Playwright elements/pages
are faked for the scraper, and httpx handlers are built from canned JSON for
the LLM client/evaluator/parser tests.
"""

from __future__ import annotations

import json
from typing import Any, Callable

import httpx

from allegro_evaluate.models import ChatMessage


# ------------------------------------------------------------------------- LLM


def llm_handler_from_resolver(
    resolver: Callable[[str], dict[str, Any] | None],
) -> Callable[[httpx.Request], httpx.Response]:
    """Build an httpx handler that returns canned JSON resolved from the prompt.

    ``resolver`` receives the user-message text (so a test can branch on
    whether it looks like a parser / stage-1 / stage-2 prompt) and returns the
    JSON payload to respond with, or ``None`` to trigger a 500.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        user_msg = next(m["content"] for m in body["messages"] if m["role"] == "user")
        payload = resolver(user_msg)
        if payload is None:
            return httpx.Response(500, json={"error": {"message": "no canned response"}})
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}}]},
        )

    return handler


def make_messages(*contents: str) -> list[ChatMessage]:
    """One user message per string, ready for ``chat_with_fallback``."""
    return [ChatMessage(role="user", content=text) for text in contents]


# --------------------------------------------------------------------- scraper


class FakeElement:
    """Minimal Playwright ``ElementHandle`` stand-in."""

    def __init__(
        self,
        attrs: dict[str, str] | None = None,
        text: str = "",
        children: dict[str, "FakeElement"] | None = None,
    ) -> None:
        self._attrs = attrs or {}
        self._text = text
        self._children = children or {}
        self.clicked = False

    def get_attribute(self, name: str) -> str | None:
        return self._attrs.get(name)

    def inner_text(self) -> str:
        return self._text

    def query_selector(self, selector: str) -> "FakeElement | None":
        return self._children.get(selector)

    def click(self) -> None:
        self.clicked = True


class FakePage:
    """Minimal Playwright ``Page`` stand-in for scraper tests."""

    def __init__(
        self,
        listing_elements: list[FakeElement] | None = None,
        url: str = "",
        title: str = "Allegro - oferty",
        cookie_elements: dict[str, FakeElement] | None = None,
    ) -> None:
        self._listing_elements = list(listing_elements or [])
        self.url = url
        self._title = title
        self._cookie_elements = cookie_elements or {}
        self.goto_calls: list[str] = []
        self.default_timeout: int | None = None

    def set_default_timeout(self, timeout: int) -> None:
        self.default_timeout = timeout

    def goto(self, url: str, **kwargs: Any) -> None:
        self.goto_calls.append(url)
        self.url = url

    def query_selector_all(self, selector: str) -> list[FakeElement]:
        return self._listing_elements

    def query_selector(self, selector: str) -> FakeElement | None:
        return self._cookie_elements.get(selector)

    def title(self) -> str:
        return self._title


class FakeContext:
    """Minimal Playwright ``BrowserContext`` stand-in."""

    def __init__(self, page: FakePage) -> None:
        self._page = page
        self.closed = False

    def new_page(self) -> FakePage:
        return self._page

    def close(self) -> None:
        self.closed = True


class FakeBrowser:
    """Minimal Playwright ``Browser`` stand-in wired to a single page."""

    def __init__(self, page: FakePage) -> None:
        self._page = page

    def new_context(self, **kwargs: Any) -> FakeContext:
        return FakeContext(self._page)
