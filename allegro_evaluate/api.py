"""Allegro REST API client with OAuth2 token management."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

from allegro_evaluate.models import Listing


@dataclass
class TokenData:
    access_token: str
    expires_at: float  # unix timestamp

    @property
    def is_expired(self) -> bool:
        return time.time() >= self.expires_at - 60  # 60s buffer


class AllegroAPIError(RuntimeError):
    """Raised when Allegro API returns an error."""


class AllegroAPIClient:
    """Client for Allegro REST API (offers/listing endpoint)."""

    TOKEN_URL = "https://allegro.pl/auth/oauth/token"
    API_BASE = "https://api.allegro.pl"
    LISTING_ENDPOINT = "/offers/listing"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        http_client: httpx.Client | None = None,
        logger: structlog.typing.FilteringBoundLogger | None = None,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.log = logger or structlog.get_logger("allegro_evaluate.api")
        self._http = http_client or httpx.Client(timeout=30.0)
        self._token: TokenData | None = None

    # -- public API ---------------------------------------------------------

    def search(
        self,
        phrase: str,
        limit: int = 30,
        offset: int = 0,
    ) -> list[Listing]:
        """Search Allegro offers by phrase."""
        if limit > 1000:
            limit = 1000
        if limit < 1:
            limit = 1

        token = self._get_token()
        headers = {
            "Authorization": f"Bearer {token.access_token}",
            "Accept": "application/vnd.allegro.public.v1+json",
            "Content-Type": "application/vnd.allegro.public.v1+json",
        }
        params = {
            "phrase": phrase,
            "limit": limit,
            "offset": offset,
        }

        self.log.info("allegro_api_search", phrase=phrase, limit=limit, offset=offset)
        response = self._http.get(
            f"{self.API_BASE}{self.LISTING_ENDPOINT}",
            headers=headers,
            params=params,
        )

        if response.status_code == 401:
            # Token might have expired, force refresh and retry once
            self._token = None
            token = self._get_token()
            headers["Authorization"] = f"Bearer {token.access_token}"
            response = self._http.get(
                f"{self.API_BASE}{self.LISTING_ENDPOINT}",
                headers=headers,
                params=params,
            )

        if response.status_code != 200:
            raise AllegroAPIError(
                f"Allegro API error {response.status_code}: {response.text}"
            )

        return self._parse_listings(response.json())

    def _get_token(self) -> TokenData:
        """Get valid access token, refreshing if needed."""
        if self._token and not self._token.is_expired:
            return self._token

        self.log.info("allegro_api_fetch_token")
        auth = httpx.BasicAuth(self.client_id, self.client_secret)
        data = {"grant_type": "client_credentials"}
        response = self._http.post(self.TOKEN_URL, auth=auth, data=data)

        if response.status_code != 200:
            raise AllegroAPIError(
                f"Token request failed {response.status_code}: {response.text}"
            )

        token_json = response.json()
        access_token = token_json["access_token"]
        expires_in = token_json.get("expires_in", 7200)  # default 2h
        self._token = TokenData(
            access_token=access_token,
            expires_at=time.time() + expires_in,
        )
        return self._token

    def _parse_listings(self, data: dict[str, Any]) -> list[Listing]:
        """Parse Allegro API response into Listing objects."""
        listings: list[Listing] = []
        for item in data.get("items", {}).get("promoted", []) + data.get("items", {}).get("regular", []):
            try:
                listing = self._item_to_listing(item)
                if listing:
                    listings.append(listing)
            except Exception as exc:  # noqa: BLE001
                self.log.warning("allegro_api_parse_failed", error=str(exc), item_id=item.get("id"))
        return listings

    def _item_to_listing(self, item: dict[str, Any]) -> Listing | None:
        """Convert a single offer item to Listing."""
        offer_id = str(item.get("id", ""))
        if not offer_id:
            return None

        title = item.get("name", "")
        url = f"https://allegro.pl/oferta/{offer_id}"

        # Price
        price = None
        selling_mode = item.get("sellingMode", {})
        price_data = selling_mode.get("price", {})
        if price_data:
            amount = price_data.get("amount")
            if amount is not None:
                price = float(amount)

        # Description snippet
        description = ""
        params = item.get("parameters", [])
        param_texts = []
        for p in params[:5]:  # first 5 params
            values = p.get("values", [])
            if values:
                param_texts.append(f"{p.get('name', '')}: {', '.join(str(v) for v in values)}")
        description = "; ".join(param_texts)

        # Image
        image_url = None
        images = item.get("images", [])
        if images:
            image_url = images[0].get("url")

        return Listing(
            id=offer_id,
            title=title,
            price=price,
            currency="PLN",
            description=description,
            url=url,
            image_url=image_url,
        )