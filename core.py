from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.error import URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

API_BASE = "https://db.ygoprodeck.com/api/v7"
DEFAULT_COLLECTION_FILE = Path("cache/collection.json")
DEFAULT_DECKS_FILE = Path("cache/decks.json")
DEFAULT_PHOTOS_DIR = Path("cache/images")
RARITY_CODE_PATTERN = re.compile(r"^\s*(?P<code>.+?)(?:\s*\((?P<rarity>[^()]+)\))?\s*$")


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
    normalized, _ = parse_set_code_and_rarity(set_identifier)
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


def get_card_by_name(card_name: str) -> dict[str, object]:
    normalized_name = card_name.strip()
    if normalized_name == "":
        raise ValueError("Card name cannot be empty.")
    encoded_name = quote(normalized_name)
    data = fetch_json(f"{API_BASE}/cardinfo.php?name={encoded_name}")
    if not isinstance(data, dict):
        raise RuntimeError("Unexpected card lookup response format.")
    cards = data.get("data")
    if not isinstance(cards, list) or not cards:
        raise ValueError(f"Card name '{card_name}' was not found.")
    card = cards[0]
    if not isinstance(card, dict):
        raise RuntimeError("Unexpected card lookup item format.")
    return card


def _is_int_text(value: str) -> bool:
    text = value.strip()
    return text != "" and text.lstrip("-").isdigit()


def _normalize_name(value: str) -> str:
    return value.strip().casefold()


def resolve_card_from_cards(
    cards: list[dict[str, object]], card_identifier: str | int
) -> dict[str, object]:
    if isinstance(card_identifier, int):
        target_id_text = str(card_identifier)
        target_name = ""
    else:
        raw_identifier = str(card_identifier).strip()
        if raw_identifier == "":
            raise ValueError("Card identifier cannot be empty.")
        target_id_text = raw_identifier if _is_int_text(raw_identifier) else ""
        target_name = _normalize_name(raw_identifier)

    if target_id_text:
        by_id = next(
            (card for card in cards if str(card.get("id")) == target_id_text),
            None,
        )
        if by_id is not None:
            return by_id

    by_name = [
        card
        for card in cards
        if _normalize_name(str(card.get("name", ""))) == target_name
    ]
    if len(by_name) == 1:
        return by_name[0]
    if len(by_name) > 1:
        choices = ", ".join(str(item.get("id", "unknown")) for item in by_name)
        raise ValueError(
            f"Multiple cards matched '{card_identifier}' in this set. Use card ID instead: {choices}."
        )

    raise ValueError(
        f"Card '{card_identifier}' was not found in this set. Use `search` to view valid card IDs/names."
    )


def resolve_saved_card_id(
    collection: dict[str, dict[str, object]], card_identifier: str | int
) -> int:
    if isinstance(card_identifier, int):
        return card_identifier

    raw_identifier = str(card_identifier).strip()
    if raw_identifier == "":
        raise ValueError("Card identifier cannot be empty.")
    if _is_int_text(raw_identifier):
        return int(raw_identifier)

    target_name = _normalize_name(raw_identifier)
    matches: list[int] = []
    for item in collection.values():
        if not isinstance(item, dict):
            continue
        if _normalize_name(str(item.get("name", ""))) != target_name:
            continue
        card_id = _as_int(item.get("card_id"), -1)
        if card_id >= 0:
            matches.append(card_id)

    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        choices = ", ".join(str(card_id) for card_id in sorted(set(matches)))
        raise ValueError(
            f"Multiple saved cards matched '{card_identifier}'. Use card ID instead: {choices}."
        )
    raise ValueError(f"Card '{card_identifier}' is not in your saved collection.")


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


def normalize_rarity_code(rarity_code: object) -> str | None:
    if rarity_code is None:
        return None
    normalized = str(rarity_code).strip().upper()
    if normalized.startswith("(") and normalized.endswith(")"):
        normalized = normalized[1:-1].strip()
    return normalized or None


def parse_set_code_and_rarity(set_value: str) -> tuple[str, str | None]:
    raw = set_value.strip()
    if raw == "":
        return "", None
    match = RARITY_CODE_PATTERN.match(raw)
    if match is None:
        return normalize_set_code(raw), None
    code = normalize_set_code(match.group("code"))
    rarity = normalize_rarity_code(match.group("rarity"))
    return code, rarity


def format_set_display_code(set_code: str, rarity_code: str | None = None) -> str:
    normalized_code = normalize_set_code(set_code)
    normalized_rarity = normalize_rarity_code(rarity_code)
    if normalized_rarity is None:
        return normalized_code
    return f"{normalized_code} ({normalized_rarity})"


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
        key_code, key_rarity = parse_set_code_and_rarity(str(key))
        code = normalize_set_code(str(raw_set.get("set_code", key_code)))
        if code == "":
            continue
        rarity_code = normalize_rarity_code(
            raw_set.get("rarity_code", raw_set.get("set_rarity_code", key_rarity))
        )
        rarity_name = str(
            raw_set.get("rarity", raw_set.get("set_rarity", ""))
        ).strip()
        qty = _as_int(raw_set.get("quantity"), 0)
        if qty <= 0:
            continue
        set_name = str(raw_set.get("set_name", "Unknown Set"))
        display_code = format_set_display_code(code, rarity_code)
        if display_code in normalized_sets:
            normalized_sets[display_code]["quantity"] = _as_int(
                normalized_sets[display_code]["quantity"], 0
            ) + qty
        else:
            normalized_sets[display_code] = {
                "set_code": code,
                "set_name": set_name,
                "display_code": display_code,
                "rarity_code": rarity_code,
                "rarity": rarity_name,
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
                key_code, key_rarity = parse_set_code_and_rarity(str(set_key))
                code = normalize_set_code(str(set_value.get("set_code", key_code)))
                if code == "":
                    continue
                rarity_code = normalize_rarity_code(
                    set_value.get(
                        "rarity_code", set_value.get("set_rarity_code", key_rarity)
                    )
                )
                rarity_name = str(
                    set_value.get("rarity", set_value.get("set_rarity", ""))
                ).strip()
                display_code = format_set_display_code(code, rarity_code)
                qty = _as_int(set_value.get("quantity"), 0)
                if qty <= 0:
                    continue
                set_name = str(set_value.get("set_name", value.get("set_name", "Unknown Set")))
                existing_set = entry_sets.get(
                    display_code,
                    {
                        "set_code": code,
                        "set_name": set_name,
                        "display_code": display_code,
                        "rarity_code": rarity_code,
                        "rarity": rarity_name,
                        "quantity": 0,
                    },
                )
                existing_set["set_name"] = set_name
                existing_set["display_code"] = display_code
                existing_set["rarity_code"] = rarity_code
                existing_set["rarity"] = rarity_name
                existing_set["quantity"] = _as_int(existing_set.get("quantity"), 0) + qty
                entry_sets[display_code] = existing_set
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
    card_id: str | int,
    quantity: int = 1,
    rarity_code: str | None = None,
    collection_file: Path = DEFAULT_COLLECTION_FILE,
) -> dict[str, object]:
    selected_set_code, set_name, cards = resolve_cards_for_identifier(set_identifier)
    target_card = resolve_card_from_cards(cards, card_id)

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

    matching_prints = _get_matching_print_variants(
        target_card, selected_set_code, set_name
    )

    if rarity_code is not None:
        target_rarity = normalize_rarity_code(rarity_code)
        matching_prints = [
            print_info
            for print_info in matching_prints
            if normalize_rarity_code(print_info.get("rarity_code")) == target_rarity
        ]
        if not matching_prints:
            raise ValueError(
                f"Rarity '{rarity_code}' was not found for card id '{card_id}' in '{selected_set_code}'."
            )

    if len(matching_prints) > 1:
        options = ", ".join(str(item.get("display_code")) for item in matching_prints)
        raise ValueError(
            f"Multiple rarities found for this print. Choose one rarity code from: {options}."
        )

    if matching_prints:
        selected_print = matching_prints[0]
        set_code = str(selected_print.get("set_code", selected_set_code))
        set_name = str(selected_print.get("set_name", set_name))
        selected_rarity = normalize_rarity_code(selected_print.get("rarity_code"))
        selected_rarity_name = str(selected_print.get("rarity", ""))
    else:
        set_code = normalize_set_code(selected_set_code)
        selected_rarity = normalize_rarity_code(rarity_code)
        selected_rarity_name = ""

    display_code = format_set_display_code(set_code, selected_rarity)
    set_entry = entry_sets.get(display_code)
    if not isinstance(set_entry, dict):
        set_entry = {
            "set_code": set_code,
            "set_name": set_name,
            "display_code": display_code,
            "rarity_code": selected_rarity,
            "rarity": selected_rarity_name,
            "quantity": 0,
        }
    set_entry["set_name"] = set_name
    set_entry["display_code"] = display_code
    set_entry["rarity_code"] = selected_rarity
    set_entry["rarity"] = selected_rarity_name
    set_entry["quantity"] = _as_int(set_entry.get("quantity"), 0) + quantity
    entry_sets[display_code] = set_entry

    _recompute_totals(entry)

    save_collection(collection, collection_file)
    return entry


def _get_matching_print_variants(
    card: dict[str, object], selected_set_code: str, selected_set_name: str
) -> list[dict[str, object]]:
    card_sets = card.get("card_sets")
    if not isinstance(card_sets, list):
        return []

    normalized_selected_code = normalize_set_code(selected_set_code)
    normalized_selected_name = selected_set_name.strip().lower()

    variants: list[dict[str, object]] = []
    seen: set[tuple[str, str | None]] = set()
    for item in card_sets:
        if not isinstance(item, dict):
            continue
        print_code = normalize_set_code(str(item.get("set_code", "")))
        if print_code == "":
            continue

        item_set_name = str(item.get("set_name", "")).strip().lower()
        code_matches = (
            print_code == normalized_selected_code
            or print_code.startswith(f"{normalized_selected_code}-")
        )
        if not code_matches and item_set_name != normalized_selected_name:
            continue

        item_rarity_code = normalize_rarity_code(item.get("set_rarity_code"))
        dedupe_key = (print_code, item_rarity_code)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        variants.append(
            {
                "set_code": print_code,
                "set_name": str(item.get("set_name", selected_set_name)),
                "rarity": str(item.get("set_rarity", "")).strip(),
                "rarity_code": item_rarity_code,
                "display_code": format_set_display_code(print_code, item_rarity_code),
            }
        )

    variants.sort(
        key=lambda item: (
            str(item.get("set_code", "")),
            str(item.get("rarity_code", "")),
        )
    )
    return variants


def get_card_print_variants(
    set_identifier: str, card_id: str | int
) -> list[dict[str, object]]:
    selected_set_code, set_name, cards = resolve_cards_for_identifier(set_identifier)
    target_card = resolve_card_from_cards(cards, card_id)
    return _get_matching_print_variants(target_card, selected_set_code, set_name)


def list_collection(
    collection_file: Path = DEFAULT_COLLECTION_FILE,
) -> list[dict[str, object]]:
    collection = load_collection(collection_file)
    return sorted(
        collection.values(), key=lambda item: str(item.get("name", "")).lower()
    )


def remove_card_from_collection(
    card_id: str | int,
    set_code: str | None = None,
    quantity: int = 1,
    remove_all: bool = False,
    collection_file: Path = DEFAULT_COLLECTION_FILE,
) -> dict[str, object]:
    collection = load_collection(collection_file)
    resolved_card_id = resolve_saved_card_id(collection, card_id)
    key = str(resolved_card_id)
    card = collection.get(key)
    if card is None:
        raise ValueError(f"Card id '{resolved_card_id}' is not in your saved collection.")

    entry_sets = card.get("sets")
    if not isinstance(entry_sets, dict) or not entry_sets:
        raise ValueError(f"Card id '{resolved_card_id}' has no set quantity data.")

    if set_code is None:
        if remove_all:
            removed = dict(card)
            del collection[key]
            save_collection(collection, collection_file)
            return {"removed": True, "card": removed}
        if len(entry_sets) > 1:
            raise ValueError(
                f"Card id '{resolved_card_id}' exists under multiple print variants. Use --set-code (for example: RA05-EN127 (SR)) to choose one."
            )
        selected_set_code = next(iter(entry_sets.keys()))
    else:
        parsed_code, parsed_rarity = parse_set_code_and_rarity(set_code)
        exact_key = format_set_display_code(parsed_code, parsed_rarity)
        if exact_key in entry_sets:
            selected_set_code = exact_key
        else:
            matching_keys: list[str] = []
            for key_name, set_value in entry_sets.items():
                if not isinstance(set_value, dict):
                    continue
                stored_code = normalize_set_code(str(set_value.get("set_code", "")))
                if stored_code == parsed_code:
                    matching_keys.append(key_name)
            if len(matching_keys) == 1:
                selected_set_code = matching_keys[0]
            elif len(matching_keys) > 1:
                raise ValueError(
                    f"Card id '{resolved_card_id}' has multiple rarities for '{parsed_code}'. Use full set code with rarity (for example: {matching_keys[0]})."
                )
            else:
                raise ValueError(
                    f"Card id '{resolved_card_id}' with set code '{exact_key}' is not in your collection."
                )

    set_entry = entry_sets.get(selected_set_code)
    if not isinstance(set_entry, dict):
        raise ValueError(
            f"Card id '{resolved_card_id}' with set code '{selected_set_code}' is not in your collection."
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


def _normalize_deck_status(status: str) -> str:
    normalized = status.strip().lower()
    if normalized not in {"current", "future"}:
        raise ValueError("Deck status must be either 'current' or 'future'.")
    return normalized


def _normalize_deck_section(section: str) -> str:
    normalized = section.strip().lower()
    if normalized not in {"main", "extra", "side"}:
        raise ValueError("Deck section must be one of: main, extra, side.")
    return normalized


def _normalize_deck_name(deck_name: str) -> str:
    normalized = deck_name.strip()
    if normalized == "":
        raise ValueError("Deck name cannot be empty.")
    return normalized


def _deck_card_summary(card: dict[str, object]) -> dict[str, object]:
    return {
        "card_id": _as_int(card.get("id"), -1),
        "name": str(card.get("name", "Unknown Card")),
        "type": str(card.get("type", "Unknown Type")),
    }


def _infer_deck_section(card_type: str) -> str:
    normalized = card_type.strip().lower()
    extra_markers = (
        "fusion monster",
        "synchro monster",
        "xyz monster",
        "link monster",
    )
    if any(marker in normalized for marker in extra_markers):
        return "extra"
    return "main"


def _resolve_any_card(card_identifier: str | int) -> dict[str, object]:
    if isinstance(card_identifier, int):
        return get_card_by_id(card_identifier)
    raw_identifier = str(card_identifier).strip()
    if raw_identifier == "":
        raise ValueError("Card identifier cannot be empty.")
    if _is_int_text(raw_identifier):
        return get_card_by_id(int(raw_identifier))
    return get_card_by_name(raw_identifier)


def _empty_deck(name: str, status: str = "future", notes: str = "") -> dict[str, object]:
    return {
        "name": name,
        "status": _normalize_deck_status(status),
        "notes": notes.strip(),
        "cards": {},
    }


def _recompute_deck_totals(deck: dict[str, object]) -> None:
    raw_cards = deck.get("cards")
    if not isinstance(raw_cards, dict):
        raw_cards = {}

    normalized_cards: dict[str, dict[str, object]] = {}
    total_cards = 0
    unique_cards = 0
    for key, raw_card in raw_cards.items():
        if not isinstance(raw_card, dict):
            continue
        card_id = _as_int(raw_card.get("card_id", key), -1)
        if card_id < 0:
            continue
        quantity = _as_int(raw_card.get("quantity"), 0)
        if quantity <= 0:
            continue
        card_key = str(card_id)
        if card_key in normalized_cards:
            normalized_cards[card_key]["quantity"] = (
                _as_int(normalized_cards[card_key]["quantity"], 0) + quantity
            )
        else:
            card_type = str(raw_card.get("type", "Unknown Type"))
            section = str(raw_card.get("section", "")).strip().lower()
            if section not in {"main", "extra", "side"}:
                section = _infer_deck_section(card_type)
            normalized_cards[card_key] = {
                "card_id": card_id,
                "name": str(raw_card.get("name", "Unknown Card")),
                "type": card_type,
                "section": section,
                "quantity": quantity,
            }
            unique_cards += 1
        total_cards += quantity

    deck["cards"] = normalized_cards
    deck["total_cards"] = total_cards
    deck["unique_cards"] = unique_cards


def load_decks(decks_file: Path = DEFAULT_DECKS_FILE) -> dict[str, dict[str, object]]:
    if not decks_file.exists():
        return {}

    raw = decks_file.read_text(encoding="utf-8")
    if raw.strip() == "":
        return {}

    data = json.loads(raw)
    if not isinstance(data, dict):
        raise RuntimeError(f"{decks_file} must contain a JSON object.")

    normalized: dict[str, dict[str, object]] = {}
    for key, value in data.items():
        if not isinstance(value, dict):
            continue
        name = _normalize_deck_name(str(value.get("name", key)))
        status = _normalize_deck_status(str(value.get("status", "future")))
        notes = str(value.get("notes", ""))
        deck = _empty_deck(name, status, notes)
        cards = value.get("cards")
        if isinstance(cards, dict):
            deck["cards"] = cards
        _recompute_deck_totals(deck)
        normalized[name.casefold()] = deck

    return normalized


def save_decks(
    decks: dict[str, dict[str, object]],
    decks_file: Path = DEFAULT_DECKS_FILE,
) -> None:
    decks_file.parent.mkdir(parents=True, exist_ok=True)
    by_name: dict[str, dict[str, object]] = {}
    for deck in sorted(decks.values(), key=lambda item: str(item.get("name", "")).casefold()):
        if not isinstance(deck, dict):
            continue
        name = str(deck.get("name", "")).strip()
        if name == "":
            continue
        by_name[name] = deck
    decks_file.write_text(
        json.dumps(by_name, indent=2, sort_keys=True), encoding="utf-8"
    )


def create_deck(
    deck_name: str,
    status: str = "future",
    notes: str = "",
    decks_file: Path = DEFAULT_DECKS_FILE,
) -> dict[str, object]:
    normalized_name = _normalize_deck_name(deck_name)
    normalized_status = _normalize_deck_status(status)
    decks = load_decks(decks_file)
    key = normalized_name.casefold()
    if key in decks:
        raise ValueError(f"Deck '{normalized_name}' already exists.")
    deck = _empty_deck(normalized_name, normalized_status, notes)
    _recompute_deck_totals(deck)
    decks[key] = deck
    save_decks(decks, decks_file)
    return deck


def list_decks(
    status: str | None = None,
    decks_file: Path = DEFAULT_DECKS_FILE,
) -> list[dict[str, object]]:
    decks = load_decks(decks_file)
    normalized_status = _normalize_deck_status(status) if status is not None else None
    items = []
    for deck in decks.values():
        if normalized_status is not None and str(deck.get("status")) != normalized_status:
            continue
        items.append(deck)
    return sorted(items, key=lambda item: str(item.get("name", "")).casefold())


def get_deck(deck_name: str, decks_file: Path = DEFAULT_DECKS_FILE) -> dict[str, object]:
    normalized_name = _normalize_deck_name(deck_name)
    decks = load_decks(decks_file)
    deck = decks.get(normalized_name.casefold())
    if deck is None:
        raise ValueError(f"Deck '{normalized_name}' was not found.")
    return deck


def set_deck_status(
    deck_name: str,
    status: str,
    decks_file: Path = DEFAULT_DECKS_FILE,
) -> dict[str, object]:
    normalized_name = _normalize_deck_name(deck_name)
    normalized_status = _normalize_deck_status(status)
    decks = load_decks(decks_file)
    key = normalized_name.casefold()
    deck = decks.get(key)
    if deck is None:
        raise ValueError(f"Deck '{normalized_name}' was not found.")
    deck["status"] = normalized_status
    _recompute_deck_totals(deck)
    decks[key] = deck
    save_decks(decks, decks_file)
    return deck


def delete_deck(deck_name: str, decks_file: Path = DEFAULT_DECKS_FILE) -> None:
    normalized_name = _normalize_deck_name(deck_name)
    decks = load_decks(decks_file)
    key = normalized_name.casefold()
    if key not in decks:
        raise ValueError(f"Deck '{normalized_name}' was not found.")
    del decks[key]
    save_decks(decks, decks_file)


def _resolve_deck_card_id(deck: dict[str, object], card_identifier: str | int) -> int:
    cards = deck.get("cards")
    if not isinstance(cards, dict):
        cards = {}
    if isinstance(card_identifier, int):
        return card_identifier
    raw_identifier = str(card_identifier).strip()
    if raw_identifier == "":
        raise ValueError("Card identifier cannot be empty.")
    if _is_int_text(raw_identifier):
        return int(raw_identifier)
    target_name = _normalize_name(raw_identifier)
    matches: list[int] = []
    for item in cards.values():
        if not isinstance(item, dict):
            continue
        if _normalize_name(str(item.get("name", ""))) != target_name:
            continue
        card_id = _as_int(item.get("card_id"), -1)
        if card_id >= 0:
            matches.append(card_id)
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        choices = ", ".join(str(card_id) for card_id in sorted(set(matches)))
        raise ValueError(
            f"Multiple deck cards matched '{card_identifier}'. Use card ID instead: {choices}."
        )
    raise ValueError(f"Card '{card_identifier}' is not in this deck.")


def add_card_to_deck(
    deck_name: str,
    card_identifier: str | int,
    quantity: int = 1,
    section: str | None = None,
    decks_file: Path = DEFAULT_DECKS_FILE,
) -> dict[str, object]:
    normalized_name = _normalize_deck_name(deck_name)
    if quantity <= 0:
        raise ValueError("Quantity must be greater than 0.")

    decks = load_decks(decks_file)
    key = normalized_name.casefold()
    deck = decks.get(key)
    if deck is None:
        raise ValueError(f"Deck '{normalized_name}' was not found.")

    card = _resolve_any_card(card_identifier)
    summary = _deck_card_summary(card)
    card_id = _as_int(summary.get("card_id"), -1)
    if card_id < 0:
        raise ValueError(f"Card '{card_identifier}' did not resolve to a valid card ID.")
    target_section = (
        _normalize_deck_section(section)
        if section is not None
        else _infer_deck_section(str(summary.get("type", "")))
    )
    cards = deck.get("cards")
    if not isinstance(cards, dict):
        cards = {}
        deck["cards"] = cards
    card_key = str(card_id)
    entry = cards.get(card_key)
    if not isinstance(entry, dict):
        entry = {**summary, "quantity": 0}
    entry["name"] = summary["name"]
    entry["type"] = summary["type"]
    entry["section"] = target_section
    entry["quantity"] = _as_int(entry.get("quantity"), 0) + quantity
    cards[card_key] = entry

    _recompute_deck_totals(deck)
    decks[key] = deck
    save_decks(decks, decks_file)
    return deck


def _parse_ydk_file(ydk_file: Path) -> dict[str, list[int]]:
    if not ydk_file.exists():
        raise ValueError(f"YDK file '{ydk_file}' was not found.")

    lines = ydk_file.read_text(encoding="utf-8").splitlines()
    sections: dict[str, list[int]] = {"main": [], "extra": [], "side": []}
    current_section = "main"
    for raw_line in lines:
        line = raw_line.strip()
        if line == "":
            continue
        lowered = line.lower()
        if lowered == "#main":
            current_section = "main"
            continue
        if lowered == "#extra":
            current_section = "extra"
            continue
        if lowered == "!side":
            current_section = "side"
            continue
        if line.startswith("#"):
            continue
        if not line.lstrip("-").isdigit():
            continue
        sections[current_section].append(int(line))
    return sections


def import_deck_from_ydk(
    deck_name: str,
    ydk_path: str | Path,
    status: str = "future",
    notes: str = "",
    overwrite: bool = False,
    decks_file: Path = DEFAULT_DECKS_FILE,
) -> dict[str, object]:
    normalized_name = _normalize_deck_name(deck_name)
    normalized_status = _normalize_deck_status(status)
    ydk_file = Path(ydk_path)
    sections = _parse_ydk_file(ydk_file)

    decks = load_decks(decks_file)
    key = normalized_name.casefold()
    if key in decks and not overwrite:
        raise ValueError(
            f"Deck '{normalized_name}' already exists. Use overwrite=True to replace it."
        )

    deck = _empty_deck(normalized_name, normalized_status, notes)
    for section_name in ("main", "extra", "side"):
        for card_id in sections[section_name]:
            card = get_card_by_id(card_id)
            summary = _deck_card_summary(card)
            resolved_id = _as_int(summary.get("card_id"), -1)
            if resolved_id < 0:
                continue
            card_key = str(resolved_id)
            entry = deck["cards"].get(card_key)
            if isinstance(entry, dict):
                entry["quantity"] = _as_int(entry.get("quantity"), 0) + 1
                if section_name != "main":
                    entry["section"] = section_name
                deck["cards"][card_key] = entry
            else:
                deck["cards"][card_key] = {
                    "card_id": resolved_id,
                    "name": summary["name"],
                    "type": summary["type"],
                    "section": section_name,
                    "quantity": 1,
                }

    _recompute_deck_totals(deck)
    decks[key] = deck
    save_decks(decks, decks_file)
    return deck


def export_deck_to_ydk(
    deck_name: str,
    ydk_path: str | Path,
    created_by: str = "yugioh-db",
    decks_file: Path = DEFAULT_DECKS_FILE,
) -> Path:
    deck = get_deck(deck_name, decks_file=decks_file)
    cards = deck.get("cards")
    if not isinstance(cards, dict):
        cards = {}

    sections: dict[str, list[int]] = {"main": [], "extra": [], "side": []}
    for entry in cards.values():
        if not isinstance(entry, dict):
            continue
        card_id = _as_int(entry.get("card_id"), -1)
        if card_id < 0:
            continue
        quantity = _as_int(entry.get("quantity"), 0)
        if quantity <= 0:
            continue
        section = str(entry.get("section", "")).strip().lower()
        if section not in {"main", "extra", "side"}:
            section = _infer_deck_section(str(entry.get("type", "")))
        for _ in range(quantity):
            sections[section].append(card_id)

    for section_name in sections:
        sections[section_name].sort()

    output_path = Path(ydk_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"#created by {created_by}", "#main"]
    lines.extend(str(card_id) for card_id in sections["main"])
    lines.append("#extra")
    lines.extend(str(card_id) for card_id in sections["extra"])
    lines.append("!side")
    lines.extend(str(card_id) for card_id in sections["side"])
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path


def remove_card_from_deck(
    deck_name: str,
    card_identifier: str | int,
    quantity: int = 1,
    remove_all: bool = False,
    decks_file: Path = DEFAULT_DECKS_FILE,
) -> dict[str, object]:
    normalized_name = _normalize_deck_name(deck_name)
    if quantity <= 0:
        raise ValueError("Quantity must be greater than 0.")

    decks = load_decks(decks_file)
    key = normalized_name.casefold()
    deck = decks.get(key)
    if deck is None:
        raise ValueError(f"Deck '{normalized_name}' was not found.")
    cards = deck.get("cards")
    if not isinstance(cards, dict) or not cards:
        raise ValueError(f"Deck '{normalized_name}' has no cards.")

    card_id = _resolve_deck_card_id(deck, card_identifier)
    card_key = str(card_id)
    entry = cards.get(card_key)
    if not isinstance(entry, dict):
        raise ValueError(f"Card '{card_identifier}' is not in this deck.")

    current_qty = _as_int(entry.get("quantity"), 0)
    if remove_all or quantity >= current_qty:
        del cards[card_key]
    else:
        entry["quantity"] = current_qty - quantity
        cards[card_key] = entry

    _recompute_deck_totals(deck)
    decks[key] = deck
    save_decks(decks, decks_file)
    return deck
