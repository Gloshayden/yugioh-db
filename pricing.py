from __future__ import annotations

import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from core import get_card_by_id, normalize_set_code

CARDMARKET_BASE = "https://www.cardmarket.com/en/YuGiOh/Products/Singles"


def _slugify(text: str) -> str:
    value = re.sub(r"[/'\"]+", "", text.strip())
    value = re.sub(r"[^A-Za-z0-9 -]+", " ", value)
    value = re.sub(r"\s+", "-", value).strip("-")
    return value


def _extract_price_from_html(html: str) -> tuple[str, str] | None:
    patterns = [
        r"Price Trend</dt>\s*<dd[^>]*>\s*([€£$])\s*([0-9]+(?:[.,][0-9]+)?)",
        r"Average price</dt>\s*<dd[^>]*>\s*([€£$])\s*([0-9]+(?:[.,][0-9]+)?)",
        r'"price":"([0-9]+(?:\.[0-9]+)?)","currency":"([A-Z]{3})"',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            a = match.group(1)
            b = match.group(2)
            if a in {"€", "£", "$"}:
                return b.replace(",", "."), a
            return a, b
    return None


def _resolve_set_info(card: dict[str, object], set_code: str | None) -> tuple[str, str]:
    card_sets = card.get("card_sets")
    if not isinstance(card_sets, list):
        raise ValueError("Card does not include set data.")

    if set_code:
        target = normalize_set_code(set_code)
        for item in card_sets:
            if not isinstance(item, dict):
                continue
            code = normalize_set_code(str(item.get("set_code", "")))
            if code == target:
                return code, str(item.get("set_name", "Unknown Set"))
        raise ValueError(f"Set code '{set_code}' not found for this card.")

    first = next((item for item in card_sets if isinstance(item, dict)), None)
    if first is None:
        raise ValueError("Card does not include set data.")
    return normalize_set_code(str(first.get("set_code", ""))), str(first.get("set_name", "Unknown Set"))


def get_cardmarket_price_by_card_id(card_id: int, set_code: str | None = None) -> dict[str, object]:
    card = get_card_by_id(card_id)
    card_name = str(card.get("name", "Unknown Card"))
    resolved_set_code, set_name = _resolve_set_info(card, set_code)

    set_slug = _slugify(set_name)
    card_slug = _slugify(card_name)
    product_url = f"{CARDMARKET_BASE}/{set_slug}/{card_slug}?language=1"

    try:
        request = Request(
            product_url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "text/html",
            },
        )
        with urlopen(request, timeout=20) as response:
            html = response.read().decode("utf-8", "ignore")
        parsed = _extract_price_from_html(html)
        if parsed:
            amount, currency = parsed
            return {
                "card_id": int(card_id),
                "name": card_name,
                "set_code": resolved_set_code,
                "set_name": set_name,
                "price": amount,
                "currency": currency,
                "source": "cardmarket-scrape",
                "url": product_url,
            }
    except (HTTPError, URLError):
        pass

    card_prices = card.get("card_prices")
    if isinstance(card_prices, list) and card_prices and isinstance(card_prices[0], dict):
        market_price = card_prices[0].get("cardmarket_price")
        if market_price not in (None, ""):
            return {
                "card_id": int(card_id),
                "name": card_name,
                "set_code": resolved_set_code,
                "set_name": set_name,
                "price": str(market_price),
                "currency": "EUR",
                "source": "ygoprodeck-cardmarket",
                "url": product_url,
            }

    raise RuntimeError(f"Unable to get Cardmarket price for card id '{card_id}'.")
