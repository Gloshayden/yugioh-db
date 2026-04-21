from __future__ import annotations

import json
from pathlib import Path
from urllib.error import URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

API_BASE = "https://db.ygoprodeck.com/api/v7"
DEFAULT_COLLECTION_FILE = Path("cache/collection.json")
DEFAULT_PHOTOS_DIR = Path("cache/images")


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


def get_card_by_id(card_id: int) -> dict[str, object]:
    data = fetch_json(f"{API_BASE}/cardinfo.php?id={int(card_id)}")
    if not isinstance(data, dict):
        raise RuntimeError("Unexpected card lookup response format.")
    cards = data.get("data")
    if not isinstance(cards, list) or not cards:
        raise ValueError(f"Card id '{card_id}' was not found.")
    card = cards[0]
    if not isinstance(card, dict):
        raise RuntimeError("Unexpected card lookup item format.")
    return card


def cache_low_res_card_image(
    card_id: int,
    photos_dir: Path = DEFAULT_PHOTOS_DIR,
    overwrite: bool = False,
) -> Path:
    card = get_card_by_id(card_id)
    raw_images = card.get("card_images")
    if not isinstance(raw_images, list) or not raw_images:
        raise ValueError(f"Card id '{card_id}' does not include image data.")

    image_info = raw_images[0]
    if not isinstance(image_info, dict):
        raise RuntimeError("Unexpected card image data format.")

    image_url = image_info.get("image_url_small") or image_info.get("image_url")
    if not isinstance(image_url, str) or image_url.strip() == "":
        raise ValueError(f"Card id '{card_id}' does not include a valid image URL.")

    suffix = Path(urlparse(image_url).path).suffix or ".jpg"
    photos_dir.mkdir(parents=True, exist_ok=True)
    file_path = photos_dir / f"{int(card_id)}{suffix}"
    if file_path.exists() and not overwrite:
        return file_path

    try:
        request = Request(
            image_url,
            headers={
                "User-Agent": "yugioh-db-cli/0.1 (+https://github.com/)",
                "Accept": "image/*",
            },
        )
        with urlopen(request, timeout=20) as response:
            image_bytes = response.read()
    except URLError as exc:
        raise RuntimeError(f"Failed to download card image: {exc.reason}") from exc

    file_path.write_bytes(image_bytes)
    return file_path


def find_cards_by_print_code(
    cards: list[dict[str, object]], print_code: str
) -> list[dict[str, object]]:
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


def resolve_cards_for_identifier(
    set_identifier: str,
) -> tuple[str, str, list[dict[str, object]]]:
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


def normalize_set_code(set_code: str) -> str:
    return set_code.strip().upper()


def _as_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _empty_card_entry(card_id: int) -> dict[str, object]:
    return {
        "card_id": card_id,
        "name": "Unknown Card",
        "type": "Unknown Type",
        "types": [],
        "atk": None,
        "def": None,
        "description": "",
        "total_quantity": 0,
        "sets": {},
    }


def _merge_shared_fields(entry: dict[str, object], source: dict[str, object]) -> None:
    if source.get("name"):
        entry["name"] = str(source.get("name"))
    if source.get("type"):
        entry["type"] = str(source.get("type"))
    types = source.get("types", source.get("typeline", []))
    if isinstance(types, list):
        entry["types"] = [str(part) for part in types if isinstance(part, str)]
    entry["atk"] = source.get("atk")
    entry["def"] = source.get("def")
    if source.get("description") is not None:
        entry["description"] = str(source.get("description"))
    elif source.get("desc") is not None:
        entry["description"] = str(source.get("desc"))


def _recompute_totals(entry: dict[str, object]) -> None:
    raw_sets = entry.get("sets")
    if not isinstance(raw_sets, dict):
        raw_sets = {}

    normalized_sets: dict[str, dict[str, object]] = {}
    total = 0
    for key, raw_set in raw_sets.items():
        if not isinstance(raw_set, dict):
            continue
        code = normalize_set_code(str(raw_set.get("set_code", key)))
        if code == "":
            continue
        qty = _as_int(raw_set.get("quantity"), 0)
        if qty <= 0:
            continue
        set_name = str(raw_set.get("set_name", "Unknown Set"))
        if code in normalized_sets:
            normalized_sets[code]["quantity"] = _as_int(normalized_sets[code]["quantity"], 0) + qty
        else:
            normalized_sets[code] = {
                "set_code": code,
                "set_name": set_name,
                "quantity": qty,
            }
        total += qty

    entry["sets"] = normalized_sets
    entry["total_quantity"] = total


def load_collection(
    collection_file: Path = DEFAULT_COLLECTION_FILE,
) -> dict[str, dict[str, object]]:
    if not collection_file.exists():
        return {}

    raw = collection_file.read_text(encoding="utf-8")
    if raw.strip() == "":
        return {}

    data = json.loads(raw)
    if not isinstance(data, dict):
        raise RuntimeError(f"{collection_file} must contain a JSON object.")

    normalized: dict[str, dict[str, object]] = {}
    for key, value in data.items():
        if not isinstance(value, dict):
            continue

        key_text = str(key)
        key_card_id = key_text.split("::")[-1] if "::" in key_text else key_text
        card_id = _as_int(value.get("card_id", key_card_id), -1)
        if card_id < 0:
            continue

        card_key = str(card_id)
        entry = normalized.get(card_key)
        if entry is None:
            entry = _empty_card_entry(card_id)
            normalized[card_key] = entry

        _merge_shared_fields(entry, value)

        entry_sets = entry.get("sets")
        if not isinstance(entry_sets, dict):
            entry_sets = {}
            entry["sets"] = entry_sets

        value_sets = value.get("sets")
        if isinstance(value_sets, dict):
            for set_key, set_value in value_sets.items():
                if not isinstance(set_value, dict):
                    continue
                code = normalize_set_code(str(set_value.get("set_code", set_key)))
                if code == "":
                    continue
                qty = _as_int(set_value.get("quantity"), 0)
                if qty <= 0:
                    continue
                set_name = str(set_value.get("set_name", value.get("set_name", "Unknown Set")))
                existing_set = entry_sets.get(code, {"set_code": code, "set_name": set_name, "quantity": 0})
                existing_set["set_name"] = set_name
                existing_set["quantity"] = _as_int(existing_set.get("quantity"), 0) + qty
                entry_sets[code] = existing_set
        else:
            old_set_code = value.get("set_code")
            if isinstance(old_set_code, str) and old_set_code.strip() != "":
                code = normalize_set_code(old_set_code)
                qty = _as_int(value.get("quantity", value.get("total_quantity")), 0)
                if qty > 0:
                    set_name = str(value.get("set_name", "Unknown Set"))
                    existing_set = entry_sets.get(code, {"set_code": code, "set_name": set_name, "quantity": 0})
                    existing_set["set_name"] = set_name
                    existing_set["quantity"] = _as_int(existing_set.get("quantity"), 0) + qty
                    entry_sets[code] = existing_set

        _recompute_totals(entry)

    normalized = {k: v for k, v in normalized.items() if _as_int(v.get("total_quantity"), 0) > 0}
    return normalized


def save_collection(
    collection: dict[str, dict[str, object]],
    collection_file: Path = DEFAULT_COLLECTION_FILE,
) -> None:
    collection_file.parent.mkdir(parents=True, exist_ok=True)
    collection_file.write_text(
        json.dumps(collection, indent=2, sort_keys=True), encoding="utf-8"
    )


def add_card_to_collection(
    set_identifier: str,
    card_id: int,
    quantity: int = 1,
    collection_file: Path = DEFAULT_COLLECTION_FILE,
) -> dict[str, object]:
    selected_set_code, set_name, cards = resolve_cards_for_identifier(set_identifier)
    target_card = next(
        (card for card in cards if str(card.get("id")) == str(card_id)), None
    )
    if target_card is None:
        raise ValueError(f"Card id '{card_id}' was not found in '{selected_set_code}'.")

    collection = load_collection(collection_file)
    card_id_value = int(target_card["id"])
    key = str(card_id_value)
    entry = collection.get(key)
    if entry is None:
        entry = _empty_card_entry(card_id_value)
        collection[key] = entry

    _merge_shared_fields(entry, target_card)
    entry["card_id"] = card_id_value
    entry["name"] = str(target_card.get("name", entry.get("name", "Unknown Card")))

    entry_sets = entry.get("sets")
    if not isinstance(entry_sets, dict):
        entry_sets = {}
        entry["sets"] = entry_sets

    set_code = normalize_set_code(selected_set_code)
    set_entry = entry_sets.get(set_code)
    if not isinstance(set_entry, dict):
        set_entry = {"set_code": set_code, "set_name": set_name, "quantity": 0}
    set_entry["set_name"] = set_name
    set_entry["quantity"] = _as_int(set_entry.get("quantity"), 0) + quantity
    entry_sets[set_code] = set_entry

    _recompute_totals(entry)

    save_collection(collection, collection_file)
    return entry


def list_collection(
    collection_file: Path = DEFAULT_COLLECTION_FILE,
) -> list[dict[str, object]]:
    collection = load_collection(collection_file)
    return sorted(
        collection.values(), key=lambda item: str(item.get("name", "")).lower()
    )


def remove_card_from_collection(
    card_id: int,
    set_code: str | None = None,
    quantity: int = 1,
    remove_all: bool = False,
    collection_file: Path = DEFAULT_COLLECTION_FILE,
) -> dict[str, object]:
    collection = load_collection(collection_file)
    key = str(card_id)
    card = collection.get(key)
    if card is None:
        raise ValueError(f"Card id '{card_id}' is not in your saved collection.")

    entry_sets = card.get("sets")
    if not isinstance(entry_sets, dict) or not entry_sets:
        raise ValueError(f"Card id '{card_id}' has no set quantity data.")

    if set_code is None:
        if remove_all:
            removed = dict(card)
            del collection[key]
            save_collection(collection, collection_file)
            return {"removed": True, "card": removed}
        if len(entry_sets) > 1:
            raise ValueError(
                f"Card id '{card_id}' exists under multiple set codes. Use --set-code to choose one."
            )
        selected_set_code = next(iter(entry_sets.keys()))
    else:
        selected_set_code = normalize_set_code(set_code)

    set_entry = entry_sets.get(selected_set_code)
    if not isinstance(set_entry, dict):
        raise ValueError(
            f"Card id '{card_id}' with set code '{selected_set_code}' is not in your collection."
        )

    current_set_qty = _as_int(set_entry.get("quantity"), 0)
    if remove_all or quantity >= current_set_qty:
        del entry_sets[selected_set_code]
        if not entry_sets:
            removed = dict(card)
            del collection[key]
            save_collection(collection, collection_file)
            return {"removed": True, "card": removed}
    else:
        set_entry["quantity"] = current_set_qty - quantity
        entry_sets[selected_set_code] = set_entry

    card["sets"] = entry_sets
    _recompute_totals(card)
    collection[key] = card
    save_collection(collection, collection_file)
    return {"removed": False, "card": card, "set_code": selected_set_code}
