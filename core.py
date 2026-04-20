from __future__ import annotations

import json
from pathlib import Path
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

API_BASE = "https://db.ygoprodeck.com/api/v7"
DEFAULT_COLLECTION_FILE = Path("collection.json")


def fetch_json(url: str) -> object:
    try:
        request = Request(
            url,
            headers={
                "User-Agent": "yugioh-db-cli/0.1 (+https://github.com/)",
                "Accept": "application/json",
            },
        )
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except URLError as exc:
        raise RuntimeError(f"Failed to reach YGOPRODeck API: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("Received invalid JSON from YGOPRODeck API.") from exc


def get_all_sets() -> list[dict[str, object]]:
    data = fetch_json(f"{API_BASE}/cardsets.php")
    if not isinstance(data, list):
        raise RuntimeError("Unexpected card set response format.")
    return [item for item in data if isinstance(item, dict)]


def parse_set_identifier(set_identifier: str) -> tuple[str, str | None]:
    normalized = set_identifier.strip().upper()
    if "-" not in normalized:
        return normalized, None
    set_prefix, _, _print_suffix = normalized.partition("-")
    if set_prefix == "":
        raise ValueError(f"Invalid set identifier '{set_identifier}'.")
    return set_prefix, normalized


def find_set_by_code(set_code: str) -> dict[str, object]:
    target = set_code.strip().upper()
    for set_info in get_all_sets():
        code = str(set_info.get("set_code", "")).upper()
        if code == target:
            return set_info
    raise ValueError(f"Set code '{set_code}' was not found.")


def get_cards_for_set_name(set_name: str) -> list[dict[str, object]]:
    encoded_name = quote(set_name)
    data = fetch_json(f"{API_BASE}/cardinfo.php?cardset={encoded_name}")
    if not isinstance(data, dict):
        raise RuntimeError("Unexpected card search response format.")
    cards = data.get("data")
    if not isinstance(cards, list):
        raise ValueError(f"No cards found for set '{set_name}'.")
    return [item for item in cards if isinstance(item, dict)]


def find_cards_by_print_code(cards: list[dict[str, object]], print_code: str) -> list[dict[str, object]]:
    target = print_code.strip().upper()
    matches: list[dict[str, object]] = []
    for card in cards:
        card_sets = card.get("card_sets")
        if not isinstance(card_sets, list):
            continue
        for print_info in card_sets:
            if not isinstance(print_info, dict):
                continue
            if str(print_info.get("set_code", "")).upper() == target:
                matches.append(card)
                break
    return matches


def resolve_cards_for_identifier(set_identifier: str) -> tuple[str, str, list[dict[str, object]]]:
    set_code, print_code = parse_set_identifier(set_identifier)
    set_info = find_set_by_code(set_code)
    set_name = str(set_info.get("set_name", "Unknown Set"))
    normalized_set_code = str(set_info.get("set_code", set_code)).upper()
    cards = get_cards_for_set_name(set_name)
    if print_code is not None:
        cards = find_cards_by_print_code(cards, print_code)
        if not cards:
            raise ValueError(f"No cards found for print code '{print_code}'.")
    return print_code or normalized_set_code, set_name, cards


def search_set_codes(query: str, limit: int = 20) -> list[tuple[str, str]]:
    term = query.strip().lower()
    matches: list[tuple[str, str]] = []
    for set_info in get_all_sets():
        set_code = str(set_info.get("set_code", ""))
        set_name = str(set_info.get("set_name", ""))
        if term in set_code.lower() or term in set_name.lower():
            matches.append((set_code, set_name))
    return matches[:limit]


def load_collection(collection_file: Path = DEFAULT_COLLECTION_FILE) -> dict[str, dict[str, object]]:
    if not collection_file.exists():
        return {}

    raw = collection_file.read_text(encoding="utf-8")
    if raw.strip() == "":
        return {}

    data = json.loads(raw)
    if not isinstance(data, dict):
        raise RuntimeError(f"{collection_file} must contain a JSON object.")
    return {str(key): value for key, value in data.items() if isinstance(value, dict)}


def save_collection(
    collection: dict[str, dict[str, object]],
    collection_file: Path = DEFAULT_COLLECTION_FILE,
) -> None:
    collection_file.write_text(json.dumps(collection, indent=2, sort_keys=True), encoding="utf-8")


def add_card_to_collection(
    set_identifier: str,
    card_id: int,
    quantity: int = 1,
    collection_file: Path = DEFAULT_COLLECTION_FILE,
) -> dict[str, object]:
    selected_set_code, set_name, cards = resolve_cards_for_identifier(set_identifier)
    target_card = next((card for card in cards if str(card.get("id")) == str(card_id)), None)
    if target_card is None:
        raise ValueError(f"Card id '{card_id}' was not found in '{selected_set_code}'.")

    collection = load_collection(collection_file)
    key = str(target_card.get("id"))
    existing = collection.get(key)
    if existing is None:
        existing = {
            "card_id": int(target_card["id"]),
            "name": str(target_card.get("name", "Unknown Card")),
            "set_code": selected_set_code,
            "set_name": set_name,
            "quantity": 0,
        }
    existing["type"] = str(target_card.get("type", "Unknown Type"))
    existing["types"] = [str(part) for part in target_card.get("typeline", []) if isinstance(part, str)]
    existing["atk"] = target_card.get("atk")
    existing["def"] = target_card.get("def")
    existing["description"] = str(target_card.get("desc", ""))
    existing["quantity"] = int(existing.get("quantity", 0)) + quantity
    collection[key] = existing
    save_collection(collection, collection_file)
    return existing


def list_collection(collection_file: Path = DEFAULT_COLLECTION_FILE) -> list[dict[str, object]]:
    collection = load_collection(collection_file)
    return sorted(collection.values(), key=lambda item: str(item.get("name", "")).lower())


def remove_card_from_collection(
    card_id: int,
    quantity: int = 1,
    remove_all: bool = False,
    collection_file: Path = DEFAULT_COLLECTION_FILE,
) -> dict[str, object]:
    collection = load_collection(collection_file)
    key = str(card_id)
    card = collection.get(key)
    if card is None:
        raise ValueError(f"Card id '{card_id}' is not in your saved collection.")

    if remove_all or quantity >= int(card.get("quantity", 0)):
        removed = dict(card)
        del collection[key]
        save_collection(collection, collection_file)
        return {"removed": True, "card": removed}

    card["quantity"] = int(card.get("quantity", 0)) - quantity
    collection[key] = card
    save_collection(collection, collection_file)
    return {"removed": False, "card": card}
