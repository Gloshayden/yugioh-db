from __future__ import annotations

import argparse

from core import (
    add_card_to_collection,
    list_collection,
    remove_card_from_collection,
    resolve_cards_for_identifier,
    search_set_codes,
)


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
    saved = add_card_to_collection(args.set_code, args.card_id, args.qty)
    print(f"Saved {saved['name']} from {saved['set_code']}. Quantity now: {saved['quantity']}.")
    return 0


def cmd_list(_: argparse.Namespace) -> int:
    cards = list_collection()
    if not cards:
        print("No cards saved yet.")
        return 0

    print("Saved cards:")
    for item in cards:
        stats = f"ATK {item.get('atk', '-')}/DEF {item.get('def', '-')}"
        print(
            f"- {item.get('name', 'Unknown Card')} "
            f"(id: {item.get('card_id', 'unknown')}, "
            f"set: {item.get('set_code', 'unknown')}, "
            f"type: {item.get('type', 'Unknown Type')}, "
            f"{stats}) x{item.get('quantity', 0)}"
        )
    return 0


def cmd_remove(args: argparse.Namespace) -> int:
    result = remove_card_from_collection(args.card_id, args.qty, args.all)
    if result["removed"]:
        print(f"Removed card id {args.card_id} from your collection.")
    else:
        print(f"Updated card id {args.card_id}. Quantity now: {result['card']['quantity']}.")
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
    add_parser.add_argument("card_id", type=int, help="Card ID from `search` output.")
    add_parser.add_argument("--qty", type=positive_int, default=1, help="Quantity to add.")
    add_parser.set_defaults(func=cmd_add)

    list_parser = subparsers.add_parser("list", help="Show saved cards and quantities.")
    list_parser.set_defaults(func=cmd_list)

    remove_parser = subparsers.add_parser("remove", help="Remove quantity or delete a saved card.")
    remove_parser.add_argument("card_id", type=int, help="Saved card ID.")
    remove_parser.add_argument("--qty", type=positive_int, default=1, help="Quantity to remove.")
    remove_parser.add_argument("--all", action="store_true", help="Remove this card entirely.")
    remove_parser.set_defaults(func=cmd_remove)

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
