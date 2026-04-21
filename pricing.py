from __future__ import annotations

import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from core import (
    get_card_by_id,
    normalize_rarity_code,
    normalize_set_code,
    parse_set_code_and_rarity,
)

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
        target, target_rarity = parse_set_code_and_rarity(set_code)
        matching_code_entries: list[dict[str, object]] = []
        for item in card_sets:
            if not isinstance(item, dict):
                continue
            code = normalize_set_code(str(item.get("set_code", "")))
            if code != target:
                continue
            matching_code_entries.append(item)
            rarity = normalize_rarity_code(item.get("set_rarity_code"))
            if code == target and (target_rarity is None or rarity == target_rarity):
                return code, str(item.get("set_name", "Unknown Set"))
        if matching_code_entries:
            fallback = matching_code_entries[0]
            return normalize_set_code(str(fallback.get("set_code", ""))), str(
                fallback.get("set_name", "Unknown Set")
            )
        raise ValueError(f"Set code '{set_code}' not found for this card.")

    first = next((item for item in card_sets if isinstance(item, dict)), None)
    if first is None:
        raise ValueError("Card does not include set data.")
    return normalize_set_code(str(first.get("set_code", ""))), str(first.get("set_name", "Unknown Set"))


def _resolve_set_entry(card: dict[str, object], set_code: str | None) -> dict[str, object]:
    card_sets = card.get("card_sets")
    if not isinstance(card_sets, list):
        raise ValueError("Card does not include set data.")

    if set_code:
        target, target_rarity = parse_set_code_and_rarity(set_code)
        matching_code_entries: list[dict[str, object]] = []
        for item in card_sets:
            if not isinstance(item, dict):
                continue
            code = normalize_set_code(str(item.get("set_code", "")))
            if code != target:
                continue
            matching_code_entries.append(item)
            rarity = normalize_rarity_code(item.get("set_rarity_code"))
            if target_rarity is not None and rarity == target_rarity:
                return item

        if target_rarity is not None:
            return matching_code_entries[0]
        if not matching_code_entries:
            raise ValueError(f"Set code '{set_code}' not found for this card.")
        return matching_code_entries[0]

    first = next((item for item in card_sets if isinstance(item, dict)), None)
    if first is None:
        raise ValueError("Card does not include set data.")
    return first


def _extract_set_price(set_entry: dict[str, object]) -> str | None:
    raw_price = set_entry.get("set_price")
    if raw_price is None:
        return None
    price_text = str(raw_price).strip()
    if price_text == "":
        return None
    try:
        if float(price_text) <= 0:
            return None
    except ValueError:
        pass
    return price_text


def get_cardmarket_price_by_card_id(card_id: int, set_code: str | None = None) -> dict[str, object]:
    card = get_card_by_id(card_id)
    card_name = str(card.get("name", "Unknown Card"))
    resolved_set_code, set_name = _resolve_set_info(card, set_code)
    resolved_set_entry = _resolve_set_entry(card, set_code)
    set_price = _extract_set_price(resolved_set_entry)

    if set_code is not None and set_price is not None:
        return {
            "card_id": int(card_id),
            "name": card_name,
            "set_code": resolved_set_code,
            "set_name": set_name,
            "price": set_price,
            "currency": "EUR",
            "source": "ygoprodeck-set-price",
            "url": "",
        }

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
