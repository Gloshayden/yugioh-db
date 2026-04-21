from __future__ import annotations

import io
from pathlib import Path
from pricing import get_cardmarket_price_by_card_id
import FreeSimpleGUI as sg
from PIL import Image

from core import (
    add_card_to_collection,
    cache_low_res_card_image,
    format_set_display_code,
    get_card_by_name,
    get_card_print_variants,
    list_collection,
    normalize_rarity_code,
    parse_set_code_and_rarity,
    remove_card_from_collection,
    resolve_cards_for_identifier,
)

SEARCH_INPUT_KEY = "-SEARCH-SET-"
SEARCH_BUTTON_KEY = "-SEARCH-BTN-"
SEARCH_RESULTS_KEY = "-SEARCH-RESULTS-"
ADD_QTY_KEY = "-ADD-QTY-"
ADD_BUTTON_KEY = "-ADD-BTN-"

STOCK_TABLE_KEY = "-STOCK-TABLE-"
REFRESH_STOCK_KEY = "-REFRESH-STOCK-"
STOCK_DOUBLE_CLICK_EVENT = f"{STOCK_TABLE_KEY}+DOUBLE-CLICK+"
MAIN_TABS_KEY = "-MAIN-TABS-"
SEARCH_TAB_KEY = "-SEARCH-TAB-"
STOCK_TAB_KEY = "-STOCK-TAB-"
IMAGE_CACHE_DIR = Path("cache/images")


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
            sg.Button("Refresh", key=REFRESH_STOCK_KEY),
        ],
    ]


def _layout() -> list[list[sg.Element]]:
    return [
        [
            sg.TabGroup(
                [
                    [
                        sg.Tab("Search", _build_search_section(), key=SEARCH_TAB_KEY),
                        sg.Tab("My Stock", _build_stock_section(), key=STOCK_TAB_KEY),
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


def _stock_rows(cards: list[dict[str, object]]) -> list[list[str]]:
    rows: list[list[str]] = []
    for card in cards:
        rows.append(
            [
                str(card.get("name", "Unknown Card")),
                str(_safe_int(card.get("total_quantity"), 0)),
            ]
        )
    return rows


def _refresh_stock(window: sg.Window) -> list[dict[str, object]]:
    cards = list_collection()
    window[STOCK_TABLE_KEY].update(values=_stock_rows(cards))
    return cards


def _open_stock_detail_popup(card: dict[str, object]) -> bool:
    card_id = _safe_int(card.get("card_id"), -1)
    if card_id < 0:
        raise ValueError("Selected card does not have a valid card id.")

    detail_sets_key = "-DETAIL-SETS-"
    remove_one_key = "-DETAIL-REMOVE-ONE-"
    remove_set_key = "-DETAIL-REMOVE-SET-"
    delete_card_key = "-DETAIL-DELETE-CARD-"

    def _image_data_for_gui(image_path: Path) -> bytes:
        with Image.open(image_path) as image:
            rgb_image = image.convert("RGB")
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
                    except (RuntimeError, ValueError):
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
        image_path = cache_low_res_card_image(card_id, photos_dir=IMAGE_CACHE_DIR)
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
            if (
                row_index is None
                or row_index < 0
                or row_index >= len(set_rows)
            ):
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


def main() -> None:
    sg.theme("DarkAmber")

    window = sg.Window("Yu-Gi-Oh Collection", _layout(), finalize=True, resizable=True)
    window[STOCK_TABLE_KEY].bind("<Double-1>", "+DOUBLE-CLICK+")

    search_entries: list[dict[str, object]] = []
    stock_cards = _refresh_stock(window)

    while True:
        event, values = window.read()

        if event == sg.WIN_CLOSED:
            break

        if event == SEARCH_BUTTON_KEY:
            search_text = str(values.get(SEARCH_INPUT_KEY, "")).strip()
            if not search_text:
                sg.popup_error(
                    "Enter a set code, print code, or card name."
                )
                continue
            try:
                resolved_identifier, _, cards = resolve_cards_for_identifier(search_text)
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
                    window[SEARCH_RESULTS_KEY].update(values=_search_rows(search_entries))
                except (RuntimeError, ValueError):
                    sg.popup_error(str(exc))
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
            continue

        if event == STOCK_DOUBLE_CLICK_EVENT:
            row_index = _selected_stock_index(window, values)
            if row_index is None or row_index < 0 or row_index >= len(stock_cards):
                continue
            try:
                changed = _open_stock_detail_popup(stock_cards[row_index])
                if changed:
                    stock_cards = _refresh_stock(window)
            except (RuntimeError, ValueError) as exc:
                sg.popup_error(str(exc))

    window.close()


if __name__ == "__main__":
    main()
