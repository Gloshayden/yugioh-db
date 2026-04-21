from __future__ import annotations

import argparse

from core import (
    add_card_to_collection,
    format_set_display_code,
    get_card_by_name,
    get_card_print_variants,
    list_collection,
    normalize_rarity_code,
    remove_card_from_collection,
    resolve_cards_for_identifier,
    search_set_codes,
)
from pricing import get_cardmarket_price_by_card_id


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("Value must be greater than 0.")
    return parsed


def cmd_sets(args: argparse.Namespace) -> int:
    matches = search_set_codes(args.query, args.limit)
    if not matches:
        print(f"No set matches for '{args.query}'.")
        return 0

    print("Matching sets:")
    for set_code, set_name in matches:
        print(f"- {set_code}: {set_name}")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    set_identifier, set_name, cards = resolve_cards_for_identifier(args.set_code)
    print(f"{set_identifier} - {set_name}")
    for card in cards[: args.limit]:
        print(f"- {card.get('id', 'unknown')}: {card.get('name', 'Unknown Card')} ({card.get('type', 'Unknown Type')})")
    print(f"Showing {min(len(cards), args.limit)} of {len(cards)} cards.")
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    variants = get_card_print_variants(args.set_code, args.card)
    selected_rarity = normalize_rarity_code(args.rarity)
    selected_display_code = args.set_code.strip().upper()

    if variants:
        chosen_variant: dict[str, object] | None = None
        if selected_rarity is not None:
            chosen_variant = next(
                (
                    variant
                    for variant in variants
                    if normalize_rarity_code(variant.get("rarity_code")) == selected_rarity
                ),
                None,
            )
            if chosen_variant is None:
                options = ", ".join(str(item.get("display_code")) for item in variants)
                raise ValueError(
                    f"Rarity '{args.rarity}' is not available. Choose one of: {options}."
                )
        elif len(variants) > 1:
            print("Multiple rarities found for this print:")
            for variant in variants:
                print(f"- {variant.get('display_code')}")
            chosen_input = input("Enter rarity code (for example SR): ").strip()
            selected_rarity = normalize_rarity_code(chosen_input)
            if selected_rarity is None:
                raise ValueError("Rarity code is required when multiple rarities exist.")
            chosen_variant = next(
                (
                    variant
                    for variant in variants
                    if normalize_rarity_code(variant.get("rarity_code")) == selected_rarity
                ),
                None,
            )
            if chosen_variant is None:
                options = ", ".join(str(item.get("display_code")) for item in variants)
                raise ValueError(
                    f"Rarity '{chosen_input}' is not available. Choose one of: {options}."
                )
        else:
            chosen_variant = variants[0]

        if chosen_variant is not None:
            selected_rarity = normalize_rarity_code(chosen_variant.get("rarity_code"))
            selected_display_code = str(chosen_variant.get("display_code", selected_display_code))
        elif selected_rarity is not None:
            selected_display_code = format_set_display_code(
                args.set_code.strip().upper(), selected_rarity
            )
    elif selected_rarity is not None:
        selected_display_code = format_set_display_code(
            args.set_code.strip().upper(), selected_rarity
        )

    saved = add_card_to_collection(
        args.set_code, args.card, args.qty, rarity_code=selected_rarity
    )

    sets = saved.get("sets", {})
    set_qty = 0
    if isinstance(sets, dict):
        set_entry = sets.get(selected_display_code)
        if isinstance(set_entry, dict):
            set_qty = int(set_entry.get("quantity", 0))
    print(
        f"Saved {saved['name']} from {selected_display_code}. "
        f"Set quantity: {set_qty}. Total quantity: {saved.get('total_quantity', 0)}."
    )
    return 0


def cmd_list(_: argparse.Namespace) -> int:
    cards = list_collection()
    if not cards:
        print("No cards saved yet.")
        return 0

    print("Saved cards:")
    for item in cards:
        stats = f"ATK {item.get('atk', '-')}/DEF {item.get('def', '-')}"
        sets = item.get("sets", {})
        set_summary = ""
        if isinstance(sets, dict):
            parts = []
            for code, set_entry in sorted(sets.items()):
                if isinstance(set_entry, dict):
                    display = str(set_entry.get("display_code", code))
                    parts.append(f"{display} x{set_entry.get('quantity', 0)}")
            set_summary = ", ".join(parts)
        print(
            f"- {item.get('name', 'Unknown Card')} "
            f"(id: {item.get('card_id', 'unknown')}, "
            f"type: {item.get('type', 'Unknown Type')}, "
            f"{stats}, "
            f"total: {item.get('total_quantity', 0)})"
        )
        if set_summary:
            print(f"  sets: {set_summary}")
    return 0


def cmd_remove(args: argparse.Namespace) -> int:
    result = remove_card_from_collection(
        args.card,
        set_code=args.set_code,
        quantity=args.qty,
        remove_all=args.all,
    )
    if result["removed"]:
        print(f"Removed card {args.card} from your collection.")
    else:
        updated = result["card"]
        print(
            f"Updated card {args.card}. "
            f"Total quantity now: {updated.get('total_quantity', 0)}."
        )
    return 0


def cmd_price(args: argparse.Namespace) -> int:
    if str(args.card).strip().lstrip("-").isdigit():
        card_id = int(str(args.card).strip())
    else:
        card = get_card_by_name(args.card)
        card_id = int(card["id"])
    result = get_cardmarket_price_by_card_id(card_id, args.set_code)
    print(
        f"{result['name']} ({result['set_code']}): "
        f"{result['price']} {result['currency']} [{result['source']}]"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Search Yu-Gi-Oh cards by set code and track your collection.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    sets_parser = subparsers.add_parser("sets", help="Find set codes by name or code fragment.")
    sets_parser.add_argument("query", help="Text to match in set code or set name.")
    sets_parser.add_argument("--limit", type=positive_int, default=20, help="Max matches to print.")
    sets_parser.set_defaults(func=cmd_sets)

    search_parser = subparsers.add_parser("search", help="List cards in a set code or full print code.")
    search_parser.add_argument("set_code", help="Set code (YS15) or full print code (RA02-EN021).")
    search_parser.add_argument("--limit", type=positive_int, default=20, help="Max cards to print.")
    search_parser.set_defaults(func=cmd_search)

    add_parser = subparsers.add_parser("add", help="Save a card from a set to your collection.")
    add_parser.add_argument("set_code", help="Set code or full print code containing the card.")
    add_parser.add_argument(
        "card",
        help="Card ID or exact card name from `search` output.",
    )
    add_parser.add_argument("--qty", type=positive_int, default=1, help="Quantity to add.")
    add_parser.add_argument(
        "--rarity",
        help="Optional rarity code (for example: SR, UR). If omitted and multiple rarities exist, you'll be prompted.",
    )
    add_parser.set_defaults(func=cmd_add)

    list_parser = subparsers.add_parser("list", help="Show saved cards and quantities.")
    list_parser.set_defaults(func=cmd_list)

    remove_parser = subparsers.add_parser("remove", help="Remove quantity or delete a saved card.")
    remove_parser.add_argument("card", help="Saved card ID or exact card name.")
    remove_parser.add_argument(
        "--set-code",
        help="Set/print code for selecting one printing under the same card ID.",
    )
    remove_parser.add_argument("--qty", type=positive_int, default=1, help="Quantity to remove.")
    remove_parser.add_argument("--all", action="store_true", help="Remove this card entirely.")
    remove_parser.set_defaults(func=cmd_remove)

    price_parser = subparsers.add_parser("price", help="Get Cardmarket price by card ID.")
    price_parser.add_argument("card", help="Card ID or exact card name.")
    price_parser.add_argument("--set-code", help="Optional set/print code (for example: RA02-EN021).")
    price_parser.set_defaults(func=cmd_price)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except (RuntimeError, ValueError) as exc:
        print(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
