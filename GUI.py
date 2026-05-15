from __future__ import annotations

import os
import json
import io
from pathlib import Path
from pricing import get_cardmarket_price_by_card_id
import FreeSimpleGUI as sg
from PIL import Image

from core import (
    add_card_to_collection,
    add_card_to_deck,
    cache_low_res_card_image,
    create_deck,
    delete_deck,
    export_deck_to_ydk,
    format_set_display_code,
    get_card_by_name,
    get_deck,
    get_card_print_variants,
    import_deck_from_ydk,
    list_collection,
    list_decks,
    normalize_rarity_code,
    parse_set_code_and_rarity,
    remove_card_from_collection,
    remove_card_from_deck,
    resolve_cards_for_identifier,
    search_cards_by_name,
    set_deck_status,
)

SEARCH_INPUT_KEY = "-SEARCH-SET-"
SEARCH_BUTTON_KEY = "-SEARCH-BTN-"
SEARCH_RESULTS_KEY = "-SEARCH-RESULTS-"
ADD_QTY_KEY = "-ADD-QTY-"
ADD_BUTTON_KEY = "-ADD-BTN-"
REFRESH_TOTAL_AMOUNT = "-REFRESH-AMOUNT-"
STOCK_TABLE_KEY = "-STOCK-TABLE-"
STOCK_SEARCH_KEY = "-STOCK-SEARCH-"
REFRESH_STOCK_KEY = "-REFRESH-STOCK-"
STOCK_DOUBLE_CLICK_EVENT = f"{STOCK_TABLE_KEY}+DOUBLE-CLICK+"
SEARCH_DOUBLE_CLICK_EVENT = f"{SEARCH_RESULTS_KEY}+DOUBLE-CLICK+"
STOCK_TOTAL_VALUE_KEY = "-STOCK-TOTAL-VALUE-"
STOCK_TOP_FIVE_KEY = "-STOCK-TOP-FIVE-"
MAIN_TABS_KEY = "-MAIN-TABS-"
SEARCH_TAB_KEY = "-SEARCH-TAB-"
STOCK_TAB_KEY = "-STOCK-TAB-"
DECK_TAB_KEY = "-DECK-TAB-"
SETTINGS_TAB_KEY = "-SETTINGS-TAB-"
THEME_COMBO_KEY = "-THEME-COMBO-"
THEME_APPLY_KEY = "-THEME-APPLY-"
QUALITY_COMBO_KEY = "-QUALITY-COMBO-"
QUALITY_APPLY_KEY = "-QUALITY-APPLY-"
DECK_NAME_INPUT_KEY = "-DECK-NAME-"
DECK_STATUS_INPUT_KEY = "-DECK-STATUS-"
DECK_NOTES_INPUT_KEY = "-DECK-NOTES-"
DECK_CREATE_BUTTON_KEY = "-DECK-CREATE-"
DECK_LIST_KEY = "-DECK-LIST-"
DECK_REFRESH_BUTTON_KEY = "-DECK-REFRESH-"
DECK_DELETE_BUTTON_KEY = "-DECK-DELETE-"
DECK_SET_CURRENT_BUTTON_KEY = "-DECK-SET-CURRENT-"
DECK_SET_FUTURE_BUTTON_KEY = "-DECK-SET-FUTURE-"
DECK_IMPORT_YDK_BUTTON_KEY = "-DECK-IMPORT-YDK-"
DECK_EXPORT_YDK_BUTTON_KEY = "-DECK-EXPORT-YDK-"
DECK_CARD_INPUT_KEY = "-DECK-CARD-"
DECK_QTY_INPUT_KEY = "-DECK-QTY-"
DECK_SECTION_INPUT_KEY = "-DECK-SECTION-"
DECK_CARD_FILTER_KEY = "-DECK-CARD-FILTER-"
DECK_ADD_CARD_BUTTON_KEY = "-DECK-ADD-CARD-"
DECK_REMOVE_ONE_BUTTON_KEY = "-DECK-REMOVE-ONE-"
DECK_REMOVE_ALL_BUTTON_KEY = "-DECK-REMOVE-ALL-"
DECK_CARDS_TABLE_KEY = "-DECK-CARDS-"
DECK_CARDS_DOUBLE_CLICK_EVENT = f"{DECK_CARDS_TABLE_KEY}+DOUBLE-CLICK+"
DECK_SECTION_TOTALS_KEY = "-DECK-SECTION-TOTALS-"
IMAGE_CACHE_DIR = Path("cache/images")
DEFAULT_SETTINGS_FILE = Path("cache/settings.json")
_STOCK_PRICE_CACHE: dict[tuple[int, str], float | None] = {}
DETAIL_IMAGE_MAX_SIZE = (340, 440)


def _card_stats_text(card: dict[str, object]) -> str:
    atk = card.get("atk")
    card_def = card.get("def")
    atk_text = "-" if atk is None else str(atk)
    def_text = "-" if card_def is None else str(card_def)
    return f"ATK: {atk_text}   DEF: {def_text}"


def _types_text(card: dict[str, object]) -> str:
    raw_types = card.get("types")
    if isinstance(raw_types, list) and raw_types:
        return ", ".join(str(part) for part in raw_types)
    card_type = card.get("type")
    if isinstance(card_type, str) and card_type.strip():
        return card_type
    return "Unknown Type"


def _build_search_section() -> list[list[sg.Element]]:
    return [
        [sg.Text("Search (set code, print code, or card name):")],
        [
            sg.Input(key=SEARCH_INPUT_KEY, size=(24, 1)),
            sg.Button("Search", key=SEARCH_BUTTON_KEY),
        ],
        [
            sg.Table(
                values=[],
                headings=["Card ID", "Name", "Type", "Print"],
                auto_size_columns=False,
                col_widths=[10, 29, 18, 20],
                key=SEARCH_RESULTS_KEY,
                enable_events=True,
                justification="left",
                select_mode=sg.TABLE_SELECT_MODE_BROWSE,
                num_rows=12,
            )
        ],
        [
            sg.Text("Quantity:"),
            sg.Input("1", key=ADD_QTY_KEY, size=(6, 1)),
            sg.Button("Add Selected Card", key=ADD_BUTTON_KEY),
        ],
    ]


def _build_stock_section() -> list[list[sg.Element]]:
    return [
        [sg.Text("My Stock (double-click a row for details)")],
        [
            sg.Text("Search:"),
            sg.Input(key=STOCK_SEARCH_KEY, size=(25, 1), enable_events=True),
        ],
        [
            sg.Table(
                values=[],
                headings=["Card Name", "Total Quantity"],
                auto_size_columns=False,
                col_widths=[42, 14],
                key=STOCK_TABLE_KEY,
                enable_events=True,
                justification="left",
                select_mode=sg.TABLE_SELECT_MODE_BROWSE,
                num_rows=12,
            ),
            sg.Column(
                [
                    [sg.Button("Refresh", key=REFRESH_STOCK_KEY)],
                    [sg.Button("Refresh Total", key=REFRESH_TOTAL_AMOUNT)],
                    [sg.Text("Warning: may take a while\nwith a large stock")],
                ],
                pad=((10, 0), (0, 0)),
            ),
        ],
        [sg.Text("Total stock value: 0.00 EUR", key=STOCK_TOTAL_VALUE_KEY)],
        [sg.Text("Top 5 most expensive cards:")],
        [
            sg.Multiline(
                default_text="(No priced cards yet)",
                size=(68, 6),
                disabled=True,
                no_scrollbar=False,
                key=STOCK_TOP_FIVE_KEY,
            )
        ],
    ]


def _build_deck_section() -> list[list[sg.Element]]:
    return [
        [sg.Text("Deck Builder (track current and future decks)")],
        [
            sg.Text("Deck Name:"),
            sg.Input(key=DECK_NAME_INPUT_KEY, size=(22, 1)),
            sg.Text("Status:"),
            sg.Combo(
                values=["future", "current"],
                default_value="future",
                readonly=True,
                key=DECK_STATUS_INPUT_KEY,
                size=(10, 1),
            ),
            sg.Button("Create Deck", key=DECK_CREATE_BUTTON_KEY),
        ],
        [
            sg.Text("Notes:"),
            sg.Input(key=DECK_NOTES_INPUT_KEY, size=(60, 1)),
        ],
        [
            sg.Table(
                values=[],
                headings=["Deck", "Status", "Cards", "Unique", "Stock"],
                auto_size_columns=False,
                col_widths=[24, 10, 8, 8, 8],
                key=DECK_LIST_KEY,
                enable_events=True,
                justification="left",
                select_mode=sg.TABLE_SELECT_MODE_BROWSE,
                num_rows=6,
            ),
            sg.Column(
                [
                    [sg.Button("Refresh", key=DECK_REFRESH_BUTTON_KEY)],
                    [sg.Button("Set Current", key=DECK_SET_CURRENT_BUTTON_KEY)],
                    [sg.Button("Set Future", key=DECK_SET_FUTURE_BUTTON_KEY)],
                    [sg.Button("Import YDK", key=DECK_IMPORT_YDK_BUTTON_KEY)],
                    [sg.Button("Export YDK", key=DECK_EXPORT_YDK_BUTTON_KEY)],
                    [sg.Button("Delete Deck", key=DECK_DELETE_BUTTON_KEY)],
                ],
                pad=((10, 0), (0, 0)),
            ),
        ],
        [
            sg.Text("Card (ID or exact name):"),
            sg.Input(key=DECK_CARD_INPUT_KEY, size=(24, 1)),
            sg.Text("Section:"),
            sg.Combo(
                values=["auto", "main", "extra", "side"],
                default_value="auto",
                readonly=True,
                key=DECK_SECTION_INPUT_KEY,
                size=(8, 1),
            ),
            sg.Text("Qty:"),
            sg.Input("1", key=DECK_QTY_INPUT_KEY, size=(6, 1)),
            sg.Button("Add Card", key=DECK_ADD_CARD_BUTTON_KEY),
        ],
        [
            sg.Table(
                values=[],
                headings=["Card ID", "Name", "Type", "Section", "Qty", "Stock"],
                auto_size_columns=False,
                col_widths=[10, 30, 14, 8, 6, 8],
                key=DECK_CARDS_TABLE_KEY,
                enable_events=True,
                justification="left",
                select_mode=sg.TABLE_SELECT_MODE_BROWSE,
                num_rows=7,
            ),
            sg.Column(
                [
                    [sg.Text("Card Filter:")],
                    [
                        sg.Combo(
                            values=["all", "main", "extra", "side"],
                            default_value="all",
                            readonly=True,
                            enable_events=True,
                            key=DECK_CARD_FILTER_KEY,
                            size=(10, 1),
                        )
                    ],
                    [sg.Button("Remove 1", key=DECK_REMOVE_ONE_BUTTON_KEY)],
                    [sg.Button("Remove Card", key=DECK_REMOVE_ALL_BUTTON_KEY)],
                ],
                pad=((10, 0), (0, 0)),
            ),
        ],
        [sg.Text("Main: 0   Extra: 0   Side: 0", key=DECK_SECTION_TOTALS_KEY)],
    ]


def _build_settings_section() -> list[list[sg.Element]]:
    quality_list = ["small", "large"]
    available_themes = sg.theme_list()  # Gets all FreeSimpleGUI built-in themes
    return [
        [sg.Text("Theme:")],
        [
            sg.Combo(
                values=available_themes,
                default_value="DarkAmber",  # Match what's set in main()
                readonly=True,
                key=THEME_COMBO_KEY,
                size=(30, 1),
            ),
            sg.Button("Apply Theme", key=THEME_APPLY_KEY),
        ],
        [sg.Text("Note: applying a theme will restart the window.", text_color="gray")],
        [sg.Text("Image quality:")],
        [
            sg.Combo(
                values=quality_list,
                default_value="small",  # Match what's set in main()
                readonly=True,
                key=QUALITY_COMBO_KEY,
                size=(30, 1),
            ),
            sg.Button("Apply quality", key=QUALITY_APPLY_KEY),
        ],
    ]


def _save_settings(settings: dict, settings_path: Path = DEFAULT_SETTINGS_FILE) -> None:
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps(settings, indent=2, sort_keys=True), encoding="utf-8"
    )


def _layout() -> list[list[sg.Element]]:
    return [
        [
            sg.TabGroup(
                [
                    [
                        sg.Tab("Search", _build_search_section(), key=SEARCH_TAB_KEY),
                        sg.Tab("My Stock", _build_stock_section(), key=STOCK_TAB_KEY),
                        sg.Tab("Deck Builder", _build_deck_section(), key=DECK_TAB_KEY),
                        sg.Tab(
                            "Settings", _build_settings_section(), key=SETTINGS_TAB_KEY
                        ),
                    ]
                ],
                key=MAIN_TABS_KEY,
                expand_x=True,
                expand_y=True,
            )
        ]
    ]


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except TypeError, ValueError:
        return default


def _quality_setting_to_choice(value: object) -> str:
    normalized = str(value).strip().lower()
    if normalized in {"cards", "large"}:
        return "large"
    return "small"


def _quality_choice_to_setting(value: object) -> str:
    return "cards" if _quality_setting_to_choice(value) == "large" else "cards_small"


def _fuzzy_match(query: str, target: str) -> bool:
    """Check if query matches target (case-insensitive substring)."""
    return query.lower() in target.lower()


def _search_rows(search_entries: list[dict[str, object]]) -> list[list[str]]:
    rows: list[list[str]] = []
    for entry in search_entries:
        card = entry.get("card")
        if not isinstance(card, dict):
            continue
        rows.append(
            [
                str(card.get("id", "")),
                str(card.get("name", "Unknown Card")),
                str(card.get("type", "Unknown Type")),
                str(entry.get("display_code", "")),
            ]
        )
    return rows


def _search_entries_for_set(
    set_identifier: str, cards: list[dict[str, object]]
) -> list[dict[str, object]]:
    return [
        {
            "card": card,
            "set_identifier": set_identifier,
            "display_code": set_identifier,
        }
        for card in cards
        if isinstance(card, dict)
    ]


def _search_entries_for_card_name(card: dict[str, object]) -> list[dict[str, object]]:
    raw_sets = card.get("card_sets")
    if not isinstance(raw_sets, list):
        return []

    entries: list[dict[str, object]] = []
    seen_display_codes: set[str] = set()
    for item in raw_sets:
        if not isinstance(item, dict):
            continue
        set_code = str(item.get("set_code", "")).strip().upper()
        if set_code == "":
            continue
        rarity_code = normalize_rarity_code(item.get("set_rarity_code"))
        display_code = format_set_display_code(set_code, rarity_code)
        if display_code in seen_display_codes:
            continue
        seen_display_codes.add(display_code)
        entries.append(
            {
                "card": card,
                "set_identifier": display_code,
                "display_code": display_code,
            }
        )
    entries.sort(key=lambda entry: str(entry.get("display_code", "")))
    return entries


def _stock_rows(
    cards: list[dict[str, object]], search_query: str = ""
) -> list[list[str]]:
    rows: list[list[str]] = []
    search_lower = search_query.strip().lower()
    for card in cards:
        card_name = str(card.get("name", "Unknown Card")).lower()
        if search_lower and search_lower not in card_name:
            continue
        rows.append(
            [
                str(card.get("name", "Unknown Card")),
                str(_safe_int(card.get("total_quantity"), 0)),
            ]
        )
    return rows


def _as_float(value: object, default: float = 0.0) -> float:
    try:
        return float(str(value).strip().replace(",", "."))
    except TypeError, ValueError:
        return default


def _stock_total_value(
    cards: list[dict[str, object]],
) -> tuple[float, int, list[tuple[str, float]]]:
    total_value = 0.0
    missing_prices = 0
    card_totals: dict[int, float] = {}
    card_names: dict[int, str] = {}
    for card in cards:
        card_id = _safe_int(card.get("card_id"), -1)
        if card_id < 0:
            continue
        card_names[card_id] = str(card.get("name", "Unknown Card"))
        sets = card.get("sets")
        if not isinstance(sets, dict):
            continue
        for code, set_info in sets.items():
            if not isinstance(set_info, dict):
                continue
            quantity = _safe_int(set_info.get("quantity"), 0)
            if quantity <= 0:
                continue
            display_code = str(set_info.get("display_code", code))
            cache_key = (card_id, display_code)
            price = _STOCK_PRICE_CACHE.get(cache_key)
            if price is None and cache_key in _STOCK_PRICE_CACHE:
                missing_prices += 1
                continue
            if price is None:
                try:
                    price_info = get_cardmarket_price_by_card_id(
                        card_id, display_code, allow_scrape=False
                    )
                except RuntimeError, ValueError:
                    _STOCK_PRICE_CACHE[cache_key] = None
                    missing_prices += 1
                    continue
                parsed_price = _as_float(price_info.get("price"), -1.0)
                if parsed_price < 0:
                    _STOCK_PRICE_CACHE[cache_key] = None
                    missing_prices += 1
                    continue
                _STOCK_PRICE_CACHE[cache_key] = parsed_price
                price = parsed_price
            line_total = price * quantity
            total_value += line_total
            card_totals[card_id] = card_totals.get(card_id, 0.0) + line_total

    top_five = sorted(
        (
            (card_names.get(card_id, "Unknown Card"), value)
            for card_id, value in card_totals.items()
            if value > 0
        ),
        key=lambda item: item[1],
        reverse=True,
    )[:5]
    return total_value, missing_prices, top_five


def _refresh_stock(window: sg.Window) -> list[dict[str, object]]:
    cards = list_collection()
    window[STOCK_TABLE_KEY].update(values=_stock_rows(cards))
    return cards


def _refresh_total(window: sg.Window):
    cards = list_collection()
    sg.popup_no_titlebar(
        "Getting prices (this may take a while)",
        auto_close=True,
        auto_close_duration=1.2,
    )
    total_value, missing_prices, top_five = _stock_total_value(cards)
    value_text = f"Total stock value: {total_value:.2f} EUR"
    if missing_prices > 0:
        value_text += f" (missing price for {missing_prices} prints)"
    window[STOCK_TOTAL_VALUE_KEY].update(value_text)
    if top_five:
        lines = [
            f"{index}. {name} - {value:.2f} EUR"
            for index, (name, value) in enumerate(top_five, start=1)
        ]
        window[STOCK_TOP_FIVE_KEY].update("\n".join(lines))
    else:
        window[STOCK_TOP_FIVE_KEY].update("(No priced cards yet)")


def _deck_stock_count(
    deck: dict[str, object], stock_cards: list[dict[str, object]]
) -> int:
    """Calculate how many cards from the deck are in stock."""
    stock_count = 0
    deck_cards = deck.get("cards")
    if not isinstance(deck_cards, dict):
        return 0

    for stock_card in stock_cards:
        card_id = _safe_int(stock_card.get("card_id"), -1)
        if card_id < 0:
            continue
        sets = stock_card.get("sets")
        if not isinstance(sets, dict):
            continue
        if any(_safe_int(s.get("quantity"), 0) > 0 for s in sets.values()):
            for deck_card in deck_cards.values():
                if _safe_int(deck_card.get("card_id"), -1) == card_id:
                    stock_count += 1
                    break
    return stock_count


def _deck_rows(
    decks: list[dict[str, object]], stock_cards: list[dict[str, object]]
) -> list[list[str]]:
    rows: list[list[str]] = []
    for deck in decks:
        rows.append(
            [
                str(deck.get("name", "Unknown Deck")),
                str(deck.get("status", "future")),
                str(_safe_int(deck.get("total_cards"), 0)),
                str(_safe_int(deck.get("unique_cards"), 0)),
                str(_deck_stock_count(deck, stock_cards)),
            ]
        )
    return rows


def _deck_card_rows(
    deck: dict[str, object],
    section_filter: str = "all",
    stock_cards: list[dict[str, object]] | None = None,
) -> list[list[str]]:
    cards = deck.get("cards")
    if not isinstance(cards, dict):
        return []

    stock_by_id: dict[int, int] = {}
    if stock_cards:
        for stock_card in stock_cards:
            card_id = _safe_int(stock_card.get("card_id"), -1)
            if card_id < 0:
                continue
            sets = stock_card.get("sets")
            if not isinstance(sets, dict):
                continue
            total_qty = sum(_safe_int(s.get("quantity"), 0) for s in sets.values())
            stock_by_id[card_id] = total_qty

    selected_filter = section_filter.strip().lower()
    rows: list[list[str]] = []
    for card in sorted(
        cards.values(),
        key=lambda item: (
            str(item.get("section", "main")),
            str(item.get("name", "")).casefold(),
        ),
    ):
        if not isinstance(card, dict):
            continue
        section = str(card.get("section", "main")).strip().lower()
        if selected_filter != "all" and section != selected_filter:
            continue
        card_id = _safe_int(card.get("card_id"), -1)
        stock_qty = stock_by_id.get(card_id, 0) if card_id >= 0 else 0
        rows.append(
            [
                str(card.get("card_id", "")),
                str(card.get("name", "Unknown Card")),
                str(card.get("type", "Unknown Type")),
                section,
                str(_safe_int(card.get("quantity"), 0)),
                str(stock_qty),
            ]
        )
    return rows


def _deck_section_totals(deck: dict[str, object]) -> tuple[int, int, int]:
    cards = deck.get("cards")
    if not isinstance(cards, dict):
        return 0, 0, 0

    totals = {"main": 0, "extra": 0, "side": 0}
    for card in cards.values():
        if not isinstance(card, dict):
            continue
        section = str(card.get("section", "main")).strip().lower()
        if section not in totals:
            continue
        totals[section] += _safe_int(card.get("quantity"), 0)
    return totals["main"], totals["extra"], totals["side"]


def _select_deck_row(window: sg.Window, deck_row_index: int) -> None:
    if deck_row_index < 0:
        return
    try:
        widget = window[DECK_LIST_KEY].Widget
        children = widget.get_children()
        if deck_row_index >= len(children):
            return
        selected_item = children[deck_row_index]
        widget.selection_set(selected_item)
        widget.focus(selected_item)
        widget.see(selected_item)
    except AttributeError:
        return


def _refresh_decks(
    window: sg.Window,
    stock_cards: list[dict[str, object]],
    selected_deck_name: str | None = None,
) -> list[dict[str, object]]:
    decks = list_decks()
    window[DECK_LIST_KEY].update(values=_deck_rows(decks, stock_cards))
    if selected_deck_name is not None and selected_deck_name.strip() != "":
        target_name = selected_deck_name.strip().casefold()
        for index, deck in enumerate(decks):
            if str(deck.get("name", "")).strip().casefold() == target_name:
                _select_deck_row(window, index)
                break
    return decks


def _refresh_selected_deck(
    window: sg.Window,
    deck_name: str | None,
    section_filter: str = "all",
    stock_cards: list[dict[str, object]] | None = None,
) -> dict[str, object] | None:
    if deck_name is None or deck_name.strip() == "":
        window[DECK_CARDS_TABLE_KEY].update(values=[])
        window[DECK_SECTION_TOTALS_KEY].update("Main: 0   Extra: 0   Side: 0")
        return None
    deck = get_deck(deck_name)
    window[DECK_CARDS_TABLE_KEY].update(
        values=_deck_card_rows(deck, section_filter, stock_cards)
    )
    main_total, extra_total, side_total = _deck_section_totals(deck)
    window[DECK_SECTION_TOTALS_KEY].update(
        f"Main: {main_total}   Extra: {extra_total}   Side: {side_total}"
    )
    return deck


def _selected_deck_name(
    values: dict[str, object], decks: list[dict[str, object]]
) -> str | None:
    row_index = _selected_table_index(values, DECK_LIST_KEY)
    if row_index is None or row_index < 0 or row_index >= len(decks):
        return None
    return str(decks[row_index].get("name", "")).strip() or None


def _active_deck_name(
    values: dict[str, object],
    decks: list[dict[str, object]],
    selected_deck_name: str | None,
) -> str | None:
    from_table = _selected_deck_name(values, decks)
    if from_table is not None:
        return from_table
    return selected_deck_name


def _active_deck_filter(values: dict[str, object], selected_filter: str) -> str:
    raw_filter = str(values.get(DECK_CARD_FILTER_KEY, selected_filter)).strip().lower()
    if raw_filter in {"all", "main", "extra", "side"}:
        return raw_filter
    return selected_filter


def _open_stock_detail_popup(card: dict[str, object], card_quality: str) -> bool:
    card_id = _safe_int(card.get("card_id"), -1)
    if card_id < 0:
        raise ValueError("Selected card does not have a valid card id.")

    detail_sets_key = "-DETAIL-SETS-"
    remove_one_key = "-DETAIL-REMOVE-ONE-"
    remove_set_key = "-DETAIL-REMOVE-SET-"
    delete_card_key = "-DETAIL-DELETE-CARD-"

    def _image_data_for_gui(
        image_path: Path, max_size: tuple[int, int] = DETAIL_IMAGE_MAX_SIZE
    ) -> bytes:
        with Image.open(image_path) as image:
            rgb_image = image.convert("RGB")
            rgb_image.thumbnail(max_size, Image.Resampling.LANCZOS)
            buffer = io.BytesIO()
            rgb_image.save(buffer, format="PNG")
            return buffer.getvalue()

    def _set_rows() -> list[list[str]]:
        rows: list[list[str]] = []
        raw_sets = card.get("sets")
        if isinstance(raw_sets, dict):
            for code, set_info in sorted(raw_sets.items()):
                if isinstance(set_info, dict):
                    display_code = str(set_info.get("display_code", code))
                    price_text = "N/A"
                    try:
                        price = get_cardmarket_price_by_card_id(card_id, display_code)
                        price_text = f"{price['price']} {price['currency']}"
                    except RuntimeError, ValueError:
                        pass
                    rows.append(
                        [
                            display_code,
                            str(_safe_int(set_info.get("quantity"), 0)),
                            price_text,
                        ]
                    )
        return rows

    def _detail_copy_layout() -> list[list[sg.Element]]:
        set_rows = _set_rows()

        description_text = str(card.get("description", "")).strip()
        if description_text == "":
            description_text = "No description available."

        return [
            [sg.Text(str(card.get("name", "Unknown Card")), font=("Any", 14, "bold"))],
            [sg.Text(_types_text(card))],
            [sg.Text(_card_stats_text(card))],
            [sg.Text(f"Total Quantity: {card.get('total_quantity', 0)}")],
            [sg.Text("Set copies (select one print to delete):")],
            [
                sg.Table(
                    values=set_rows,
                    headings=["Print", "Qty", "CM Price"],
                    auto_size_columns=False,
                    col_widths=[20, 7, 14],
                    key=detail_sets_key,
                    enable_events=True,
                    justification="left",
                    select_mode=sg.TABLE_SELECT_MODE_BROWSE,
                    num_rows=5,
                )
            ],
            [
                sg.Button("Remove 1 Copy", key=remove_one_key),
                sg.Button("Remove Selected Print", key=remove_set_key),
            ],
            [sg.Button("Delete Card", key=delete_card_key)],
            [sg.Text("Description:")],
            [
                sg.Multiline(
                    default_text=description_text,
                    size=(48, 9),
                    disabled=True,
                    no_scrollbar=False,
                )
            ],
            [sg.Button("Close")],
        ]

    image_element: sg.Element
    try:
        image_path = cache_low_res_card_image(
            card_id,
            photos_dir=IMAGE_CACHE_DIR / card_quality,
            quality=card_quality,
        )
        image_element = sg.Image(
            data=_image_data_for_gui(image_path), pad=((0, 14), (0, 0))
        )
    except RuntimeError, ValueError, OSError:
        image_element = sg.Text(
            "Image unavailable", size=(22, 20), justification="center"
        )

    layout = [
        [
            image_element,
            sg.Column(_detail_copy_layout(), pad=(0, 0), vertical_alignment="top"),
        ]
    ]
    detail_window = sg.Window(
        f"Card Details - {card_id}", layout, modal=True, finalize=True
    )

    changed = False
    while True:
        event, detail_values = detail_window.read()
        if event in (sg.WIN_CLOSED, "Close"):
            break
        if event in (remove_one_key, remove_set_key):
            row_index = _selected_table_index(detail_values, detail_sets_key)
            set_rows = _set_rows()
            if row_index is None or row_index < 0 or row_index >= len(set_rows):
                sg.popup_error("Select a print from the set list first.")
                continue
            selected_set_code = str(set_rows[row_index][0])
            try:
                remove_card_from_collection(
                    card_id,
                    set_code=selected_set_code,
                    quantity=1,
                    remove_all=(event == remove_set_key),
                )
                changed = True
                break
            except (RuntimeError, ValueError) as exc:
                sg.popup_error(str(exc))
                continue
        if event == delete_card_key:
            confirmation = sg.popup_yes_no(
                "Delete this card and all its print variants from your stock?",
                title="Confirm Delete",
            )
            if confirmation != "Yes":
                continue
            try:
                remove_card_from_collection(card_id, remove_all=True)
                changed = True
                break
            except (RuntimeError, ValueError) as exc:
                sg.popup_error(str(exc))
                continue
    detail_window.close()
    return changed


def _open_deck_card_detail_popup(
    deck_name: str, deck_card: dict[str, object], card_quality: str
) -> bool:
    card_id = _safe_int(deck_card.get("card_id"), -1)
    if card_id < 0:
        raise ValueError("Selected deck card does not have a valid card id.")

    remove_one_key = "-DECK-DETAIL-REMOVE-ONE-"
    remove_all_key = "-DECK-DETAIL-REMOVE-ALL-"

    def _image_data_for_gui(
        image_path: Path, max_size: tuple[int, int] = DETAIL_IMAGE_MAX_SIZE
    ) -> bytes:
        with Image.open(image_path) as image:
            rgb_image = image.convert("RGB")
            rgb_image.thumbnail(max_size, Image.Resampling.LANCZOS)
            buffer = io.BytesIO()
            rgb_image.save(buffer, format="PNG")
            return buffer.getvalue()

    image_element: sg.Element
    try:
        image_path = cache_low_res_card_image(
            card_id,
            photos_dir=IMAGE_CACHE_DIR / card_quality,
            quality=card_quality,
        )
        image_element = sg.Image(
            data=_image_data_for_gui(image_path), pad=((0, 14), (0, 0))
        )
    except RuntimeError, ValueError, OSError:
        image_element = sg.Text(
            "Image unavailable", size=(22, 20), justification="center"
        )

    layout = [
        [
            image_element,
            sg.Column(
                [
                    [
                        sg.Text(
                            str(deck_card.get("name", "Unknown Card")),
                            font=("Any", 14, "bold"),
                        )
                    ],
                    [sg.Text(str(deck_card.get("type", "Unknown Type")))],
                    [sg.Text(f"Card ID: {card_id}")],
                    [sg.Text(f"Section: {deck_card.get('section', 'main')}")],
                    [sg.Text(f"Quantity in Deck: {deck_card.get('quantity', 0)}")],
                    [
                        sg.Button("Remove 1", key=remove_one_key),
                        sg.Button("Remove Card", key=remove_all_key),
                    ],
                    [sg.Button("Close")],
                ],
                pad=(0, 0),
                vertical_alignment="top",
            ),
        ]
    ]

    detail_window = sg.Window(
        f"Deck Card - {card_id}", layout, modal=True, finalize=True
    )
    changed = False
    while True:
        event, _ = detail_window.read()
        if event in (sg.WIN_CLOSED, "Close"):
            break
        if event in (remove_one_key, remove_all_key):
            try:
                remove_card_from_deck(
                    deck_name,
                    card_id,
                    quantity=1,
                    remove_all=(event == remove_all_key),
                    section=str(deck_card.get("section", "main")),
                )
                changed = True
                break
            except (RuntimeError, ValueError) as exc:
                sg.popup_error(str(exc))
                continue

    detail_window.close()
    return changed


def _selected_table_index(values: dict[str, object], key: str) -> int | None:
    selected = values.get(key)
    if not isinstance(selected, list) or not selected:
        return None
    return _safe_int(selected[0], -1)


def _selected_stock_index(window: sg.Window, values: dict[str, object]) -> int | None:
    row_index = _selected_table_index(values, STOCK_TABLE_KEY)
    if row_index is not None and row_index >= 0:
        return row_index

    try:
        widget = window[STOCK_TABLE_KEY].Widget
        selected_items = widget.selection()
        if selected_items:
            return _safe_int(widget.index(selected_items[0]), -1)
    except AttributeError, TypeError, ValueError:
        return None
    return None


def _selected_deck_card_index(
    window: sg.Window, values: dict[str, object]
) -> int | None:
    row_index = _selected_table_index(values, DECK_CARDS_TABLE_KEY)
    if row_index is not None and row_index >= 0:
        return row_index

    try:
        widget = window[DECK_CARDS_TABLE_KEY].Widget
        selected_items = widget.selection()
        if selected_items:
            return _safe_int(widget.index(selected_items[0]), -1)
    except AttributeError, TypeError, ValueError:
        return None
    return None


def main() -> None:
    if not DEFAULT_SETTINGS_FILE.exists():
        sg.theme("DarkAmber")
        DEFAULT_SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        DEFAULT_SETTINGS_FILE.write_text(
            json.dumps(
                {"theme": "DarkAmber", "quality": "cards_small"}, sort_keys=True
            ),
            encoding="utf-8",
        )

    raw = DEFAULT_SETTINGS_FILE.read_text(encoding="utf-8")
    settings = json.loads(raw)
    sg.theme(settings["theme"])
    card_quality = _quality_choice_to_setting(settings.get("quality", "small"))
    quality_choice = _quality_setting_to_choice(card_quality)
    window = sg.Window("Yu-Gi-Oh Collection", _layout(), finalize=True, resizable=True)
    window[STOCK_TABLE_KEY].bind("<Double-1>", "+DOUBLE-CLICK+")
    window[DECK_CARDS_TABLE_KEY].bind("<Double-1>", "+DOUBLE-CLICK+")
    window[SEARCH_RESULTS_KEY].bind("<Double-1>", "+DOUBLE-CLICK+")
    window[QUALITY_COMBO_KEY].update(value=quality_choice)

    search_entries: list[dict[str, object]] = []
    stock_cards = _refresh_stock(window)
    decks = _refresh_decks(window, stock_cards)
    selected_deck_name: str | None = None
    selected_deck_filter = "all"

    while True:
        event, values = window.read()

        if event == sg.WIN_CLOSED:
            break

        if event == QUALITY_APPLY_KEY:
            chosen_quality = _quality_choice_to_setting(
                values.get(QUALITY_COMBO_KEY, "small")
            )
            card_quality = chosen_quality
            settings = {"theme": settings["theme"], "quality": card_quality}
            _save_settings(settings)
            window[QUALITY_COMBO_KEY].update(
                value=_quality_setting_to_choice(card_quality)
            )
            continue

        if event == THEME_APPLY_KEY:
            chosen_theme = str(values.get(THEME_COMBO_KEY, "DarkAmber")).strip()
            if chosen_theme not in sg.theme_list():
                sg.popup_error("Invalid theme selected.")
                continue

            settings = {"theme": chosen_theme, "quality": card_quality}
            _save_settings(settings)

            sg.theme(chosen_theme)
            window.close()

            window = sg.Window(
                "Yu-Gi-Oh Collection", _layout(), finalize=True, resizable=True
            )
            window[STOCK_TABLE_KEY].bind("<Double-1>", "+DOUBLE-CLICK+")
            window[DECK_CARDS_TABLE_KEY].bind("<Double-1>", "+DOUBLE-CLICK+")
            window[SEARCH_RESULTS_KEY].bind("<Double-1>", "+DOUBLE-CLICK+")
            window[QUALITY_COMBO_KEY].update(
                value=_quality_setting_to_choice(card_quality)
            )

            stock_cards = _refresh_stock(window)
            decks = _refresh_decks(window, stock_cards, selected_deck_name)
            _refresh_selected_deck(
                window, selected_deck_name, selected_deck_filter, stock_cards
            )
            continue

        if event == SEARCH_BUTTON_KEY:
            search_text = str(values.get(SEARCH_INPUT_KEY, "")).strip()
            if not search_text:
                sg.popup_error("Enter a set code, print code, or card name.")
                continue
            try:
                resolved_identifier, _, cards = resolve_cards_for_identifier(
                    search_text
                )
                search_entries = _search_entries_for_set(resolved_identifier, cards)
                window[SEARCH_RESULTS_KEY].update(values=_search_rows(search_entries))
            except (RuntimeError, ValueError) as exc:
                try:
                    card = get_card_by_name(search_text)
                    search_entries = _search_entries_for_card_name(card)
                    if not search_entries:
                        raise ValueError(
                            f"Card '{search_text}' was found but has no printable set data."
                        )
                    window[SEARCH_RESULTS_KEY].update(
                        values=_search_rows(search_entries)
                    )
                except RuntimeError, ValueError:
                    cards = search_cards_by_name(search_text)
                    if cards:
                        search_entries = [
                            {
                                "card": card,
                                "set_identifier": str(card.get("name", "")),
                                "display_code": str(card.get("name", "")),
                            }
                            for card in cards
                        ]
                        window[SEARCH_RESULTS_KEY].update(
                            values=_search_rows(search_entries)
                        )
                    else:
                        sg.popup_error(f"Could not find card: {search_text}")
            continue

        if event == ADD_BUTTON_KEY:
            row_index = _selected_table_index(values, SEARCH_RESULTS_KEY)
            if row_index is None or row_index < 0 or row_index >= len(search_entries):
                sg.popup_error("Select a card from search results first.")
                continue

            qty = _safe_int(values.get(ADD_QTY_KEY), 0)
            if qty <= 0:
                sg.popup_error("Quantity must be greater than 0.")
                continue

            selected_entry = search_entries[row_index]
            selected_card = selected_entry.get("card")
            if not isinstance(selected_card, dict):
                sg.popup_error("Selected search result is invalid.")
                continue
            card_id = _safe_int(selected_card.get("id"), -1)
            if card_id < 0:
                sg.popup_error("Selected result does not include a valid card ID.")
                continue

            set_identifier = str(selected_entry.get("set_identifier", "")).strip()
            if set_identifier == "":
                sg.popup_error("Selected result does not include a valid print code.")
                continue

            try:
                variants = get_card_print_variants(set_identifier, card_id)
                _, selected_row_rarity = parse_set_code_and_rarity(set_identifier)
                selected_rarity = normalize_rarity_code(selected_row_rarity)
                if selected_rarity is None and len(variants) > 1:
                    options = ", ".join(
                        str(item.get("display_code")) for item in variants
                    )
                    user_input = sg.popup_get_text(
                        "Multiple rarities found.\n"
                        f"Available: {options}\n\n"
                        "Enter rarity code (for example: SR):",
                        title="Choose Rarity",
                    )
                    selected_rarity = normalize_rarity_code(user_input)
                    if selected_rarity is None:
                        raise ValueError("Rarity selection is required.")

                add_card_to_collection(
                    set_identifier, card_id, qty, rarity_code=selected_rarity
                )
                stock_cards = _refresh_stock(window)
                sg.popup_no_titlebar(
                    "Card added to stock.", auto_close=True, auto_close_duration=1.2
                )
            except (RuntimeError, ValueError) as exc:
                sg.popup_error(str(exc))
            continue

        if event == REFRESH_STOCK_KEY:
            stock_cards = _refresh_stock(window)
            window[STOCK_SEARCH_KEY].update(value="")
            continue

        if event == STOCK_SEARCH_KEY:
            search_query = str(values.get(STOCK_SEARCH_KEY, "")).strip()
            window[STOCK_TABLE_KEY].update(
                values=_stock_rows(stock_cards, search_query)
            )
            continue

        if event == REFRESH_TOTAL_AMOUNT:
            _refresh_total(window)
            continue

        if event == DECK_REFRESH_BUTTON_KEY:
            selected_deck_name = _active_deck_name(values, decks, selected_deck_name)
            selected_deck_filter = _active_deck_filter(values, selected_deck_filter)
            decks = _refresh_decks(window, selected_deck_name)
            _refresh_selected_deck(
                window, selected_deck_name, selected_deck_filter, stock_cards
            )
            stock_cards = _refresh_stock(window)
            decks = _refresh_decks(window, stock_cards, selected_deck_name)
            _refresh_selected_deck(window, selected_deck_name, selected_deck_filter)
            continue

        if event == DECK_LIST_KEY:
            selected_deck_name = _selected_deck_name(values, decks)
            _refresh_selected_deck(
                window, selected_deck_name, selected_deck_filter, stock_cards
            )
            continue

        if event == DECK_CARD_FILTER_KEY:
            selected_deck_filter = _active_deck_filter(values, selected_deck_filter)
            _refresh_selected_deck(
                window, selected_deck_name, selected_deck_filter, stock_cards
            )
            continue

        if event == DECK_CREATE_BUTTON_KEY:
            deck_name = str(values.get(DECK_NAME_INPUT_KEY, "")).strip()
            status = str(values.get(DECK_STATUS_INPUT_KEY, "future")).strip().lower()
            notes = str(values.get(DECK_NOTES_INPUT_KEY, "")).strip()
            if deck_name == "":
                sg.popup_error("Deck name is required.")
                continue
            try:
                create_deck(deck_name, status=status, notes=notes)
                selected_deck_name = deck_name
                decks = _refresh_decks(window, selected_deck_name)
                _refresh_selected_deck(
                    window, selected_deck_name, selected_deck_filter, stock_cards
                )
                stock_cards = _refresh_stock(window)
                decks = _refresh_decks(window, stock_cards, selected_deck_name)
                _refresh_selected_deck(window, selected_deck_name, selected_deck_filter)
                sg.popup_no_titlebar(
                    "Deck created.", auto_close=True, auto_close_duration=1.2
                )
            except (RuntimeError, ValueError) as exc:
                sg.popup_error(str(exc))
            continue

        if event in (DECK_SET_CURRENT_BUTTON_KEY, DECK_SET_FUTURE_BUTTON_KEY):
            selected_deck_name = _active_deck_name(values, decks, selected_deck_name)
            if selected_deck_name is None:
                sg.popup_error("Select a deck first.")
                continue
            status = "current" if event == DECK_SET_CURRENT_BUTTON_KEY else "future"
            try:
                set_deck_status(selected_deck_name, status)
                decks = _refresh_decks(window, selected_deck_name)
                _refresh_selected_deck(
                    window, selected_deck_name, selected_deck_filter, stock_cards
                )
                stock_cards = _refresh_stock(window)
                decks = _refresh_decks(window, stock_cards, selected_deck_name)
                _refresh_selected_deck(window, selected_deck_name, selected_deck_filter)
            except (RuntimeError, ValueError) as exc:
                sg.popup_error(str(exc))
            continue

        if event == DECK_IMPORT_YDK_BUTTON_KEY:
            ydk_path = sg.popup_get_file(
                "Select a .ydk file to import",
                title="Import YDK",
                file_types=(("YDK Files", "*.ydk"), ("All Files", "*.*")),
            )
            if ydk_path in (None, ""):
                continue
            selected_path = Path(str(ydk_path))
            typed_name = str(values.get(DECK_NAME_INPUT_KEY, "")).strip()
            target_deck_name = typed_name if typed_name else selected_path.stem
            if target_deck_name == "":
                sg.popup_error("Enter a deck name first.")
                continue

            try:
                import_deck_from_ydk(
                    target_deck_name,
                    selected_path,
                    status=str(values.get(DECK_STATUS_INPUT_KEY, "future")),
                    notes=str(values.get(DECK_NOTES_INPUT_KEY, "")),
                    overwrite=True,
                )
                selected_deck_name = target_deck_name
                decks = _refresh_decks(window, selected_deck_name)
                _refresh_selected_deck(
                    window, selected_deck_name, selected_deck_filter, stock_cards
                )
                stock_cards = _refresh_stock(window)
                decks = _refresh_decks(window, stock_cards, selected_deck_name)
                _refresh_selected_deck(window, selected_deck_name, selected_deck_filter)
                window[DECK_NAME_INPUT_KEY].update(value=selected_deck_name)
                sg.popup_no_titlebar(
                    "Deck imported from YDK.", auto_close=True, auto_close_duration=1.2
                )
            except (RuntimeError, ValueError) as exc:
                sg.popup_error(str(exc))
            continue

        if event == DECK_EXPORT_YDK_BUTTON_KEY:
            selected_deck_name = _active_deck_name(values, decks, selected_deck_name)
            if selected_deck_name is None:
                sg.popup_error("Select a deck first.")
                continue
            ydk_path = sg.popup_get_file(
                "Choose where to save the .ydk file",
                title="Export YDK",
                save_as=True,
                default_extension=".ydk",
                default_path=f"{selected_deck_name}.ydk",
                file_types=(("YDK Files", "*.ydk"), ("All Files", "*.*")),
            )
            if ydk_path in (None, ""):
                continue
            try:
                export_deck_to_ydk(selected_deck_name, str(ydk_path))
                sg.popup_no_titlebar(
                    "Deck exported to YDK.", auto_close=True, auto_close_duration=1.2
                )
            except (RuntimeError, ValueError) as exc:
                sg.popup_error(str(exc))
            continue

        if event == DECK_DELETE_BUTTON_KEY:
            selected_deck_name = _active_deck_name(values, decks, selected_deck_name)
            if selected_deck_name is None:
                sg.popup_error("Select a deck first.")
                continue
            confirmation = sg.popup_yes_no(
                f"Delete deck '{selected_deck_name}'?", title="Confirm Delete"
            )
            if confirmation != "Yes":
                continue
            try:
                delete_deck(selected_deck_name)
                stock_cards = _refresh_stock(window)
                decks = _refresh_decks(window, stock_cards)
                selected_deck_name = None
                _refresh_selected_deck(
                    window, selected_deck_name, selected_deck_filter, stock_cards
                )
            except (RuntimeError, ValueError) as exc:
                sg.popup_error(str(exc))
            continue

        if event == DECK_ADD_CARD_BUTTON_KEY:
            selected_deck_name = _active_deck_name(values, decks, selected_deck_name)
            if selected_deck_name is None:
                sg.popup_error("Select a deck first.")
                continue
            card_identifier = str(values.get(DECK_CARD_INPUT_KEY, "")).strip()
            if card_identifier == "":
                sg.popup_error("Enter a card ID or card name.")
                continue
            qty = _safe_int(values.get(DECK_QTY_INPUT_KEY), 0)
            if qty <= 0:
                sg.popup_error("Quantity must be greater than 0.")
                continue
            selected_section = (
                str(values.get(DECK_SECTION_INPUT_KEY, "auto")).strip().lower()
            )
            section_arg = None if selected_section in {"", "auto"} else selected_section
            try:
                add_card_to_deck(
                    selected_deck_name,
                    card_identifier,
                    quantity=qty,
                    section=section_arg,
                )
                _refresh_selected_deck(
                    window, selected_deck_name, selected_deck_filter, stock_cards
                )
                stock_cards = _refresh_stock(window)
                decks = _refresh_decks(window, stock_cards, selected_deck_name)
                sg.popup_no_titlebar(
                    "Card added to deck.", auto_close=True, auto_close_duration=1.2
                )
            except (RuntimeError, ValueError) as exc:
                sg.popup_error(str(exc))
            continue

        if event in (DECK_REMOVE_ONE_BUTTON_KEY, DECK_REMOVE_ALL_BUTTON_KEY):
            selected_deck_name = _active_deck_name(values, decks, selected_deck_name)
            if selected_deck_name is None:
                sg.popup_error("Select a deck first.")
                continue
            deck = _refresh_selected_deck(
                window, selected_deck_name, selected_deck_filter
            )
            if deck is None:
                sg.popup_error("Select a deck first.")
                continue
            row_index = _selected_table_index(values, DECK_CARDS_TABLE_KEY)
            card_rows = _deck_card_rows(deck, selected_deck_filter)
            if row_index is None or row_index < 0 or row_index >= len(card_rows):
                sg.popup_error("Select a deck card first.")
                continue
            card_id = card_rows[row_index][0]
            section = card_rows[row_index][3]
            try:
                remove_card_from_deck(
                    selected_deck_name,
                    card_id,
                    quantity=1,
                    remove_all=(event == DECK_REMOVE_ALL_BUTTON_KEY),
                    section=section,
                )
                _refresh_selected_deck(
                    window, selected_deck_name, selected_deck_filter, stock_cards
                )
                decks = _refresh_decks(window, selected_deck_name)
                _refresh_selected_deck(window, selected_deck_name, selected_deck_filter)
                stock_cards = _refresh_stock(window)
                decks = _refresh_decks(window, stock_cards, selected_deck_name)
            except (RuntimeError, ValueError) as exc:
                sg.popup_error(str(exc))
            continue

        if event == DECK_CARDS_DOUBLE_CLICK_EVENT:
            selected_deck_name = _active_deck_name(values, decks, selected_deck_name)
            if selected_deck_name is None:
                continue
            deck = get_deck(selected_deck_name)
            card_rows = _deck_card_rows(deck, selected_deck_filter)
            row_index = _selected_deck_card_index(window, values)
            if row_index is None or row_index < 0 or row_index >= len(card_rows):
                continue
            card_id = _safe_int(card_rows[row_index][0], -1)
            section = str(card_rows[row_index][3]).strip().lower()
            if card_id < 0:
                continue
            cards_map = deck.get("cards")
            if not isinstance(cards_map, dict):
                continue
            deck_card = next(
                (
                    item
                    for item in cards_map.values()
                    if isinstance(item, dict)
                    and _safe_int(item.get("card_id"), -1) == card_id
                    and str(item.get("section", "main")).strip().lower() == section
                ),
                None,
            )
            if deck_card is None:
                continue
            try:
                changed = _open_deck_card_detail_popup(
                    selected_deck_name, deck_card, card_quality
                )
                if changed:
                    _refresh_selected_deck(
                        window, selected_deck_name, selected_deck_filter
                    )
                    stock_cards = _refresh_stock(window)
                    decks = _refresh_decks(window, stock_cards, selected_deck_name)
            except (RuntimeError, ValueError) as exc:
                sg.popup_error(str(exc))
            continue

        if event == STOCK_DOUBLE_CLICK_EVENT:
            row_index = _selected_stock_index(window, values)
            if row_index is None or row_index < 0 or row_index >= len(stock_cards):
                continue
            try:
                changed = _open_stock_detail_popup(stock_cards[row_index], card_quality)
                if changed:
                    stock_cards = _refresh_stock(window)
            except (RuntimeError, ValueError) as exc:
                sg.popup_error(str(exc))
            continue

        if event == SEARCH_DOUBLE_CLICK_EVENT:
            row_index = _selected_table_index(values, SEARCH_RESULTS_KEY)
            if row_index is None or row_index < 0 or row_index >= len(search_entries):
                continue
            try:
                search_entry = search_entries[row_index]
                card_id = _safe_int(search_entry.get("card", {}).get("id"), -1)
                if card_id > 0:
                    stock_card = next(
                        (
                            c
                            for c in stock_cards
                            if _safe_int(c.get("card_id")) == card_id
                        ),
                        None,
                    )
                    if stock_card:
                        changed = _open_stock_detail_popup(stock_card, card_quality)
                    else:
                        sg.popup_error("Card not in collection yet.")
            except (RuntimeError, ValueError) as exc:
                sg.popup_error(str(exc))
            continue

    window.close()


if __name__ == "__main__":
    main()
