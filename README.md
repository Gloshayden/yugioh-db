# yugioh-db

Simple CLI app to search Yu-Gi-Oh cards by **set code** and track how many copies you own.

## Requirements

- Python 3.14+

## Usage

```bash
python main.py --help
```

Find a set code (if you only know part of the set name):

```bash
python main.py sets "blue eyes"
```

Search cards in a set:

```bash
python main.py search YS15
```

Search using a full print code:

```bash
python main.py search RA02-EN021
```

Save a card and quantity:

```bash
python main.py add YS15 85639257 --qty 2
```

You can also add by full print code:

```bash
python main.py add RA02-EN021 37818794 --qty 1
```

Show your saved collection:

```bash
python main.py list
```

Remove one copy (or use `--all` to remove the card entirely):

```bash
python main.py remove 85639257 --qty 1
```

Collection data is stored locally in `collection.json`, including cached card details (`type`, `types`, `atk`, `def`, and `description`) so your GUI can load them without extra API calls.

## Reuse in a GUI

Core app logic now lives in `core.py` so a GUI can import it directly:

- `resolve_cards_for_identifier(set_identifier)`
- `add_card_to_collection(set_identifier, card_id, quantity)`
- `list_collection()`
- `remove_card_from_collection(card_id, quantity, remove_all)`
