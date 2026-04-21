# yugioh-db

Simple CLI app to search Yu-Gi-Oh cards by **set code** and track how many copies you own.

## Requirements

- Python 3.14+

## Usage

```bash
python main.py --help
```

## GUI

Launch the GUI:

```bash
python GUI.py
```

GUI sections:
- **Search**: enter set code/print code, search cards, select a row, add quantity to stock.
- **My Stock**: shows card name + total quantity; double-click a row to open details.
- **Stock details popup**: shows image on the left and name, full description, types, ATK, DEF on the right.

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

Get Cardmarket price by card ID:

```bash
python main.py price 37818794 --set-code RA02-EN021
```

Remove one copy (or use `--all` to remove the card entirely):

```bash
python main.py remove 85639257 --qty 1
```

If a card ID has multiple set/print quantities, specify the exact one:

```bash
python main.py remove 37818794 --set-code RA02-EN021 --all
```

Collection data is stored locally in `cache/collection.json`, grouped by `card_id` with shared details plus:

- `total_quantity` across all printings
- `sets` map keyed by `set_code`, each with its own `quantity`

## Reuse in a GUI

Core app logic now lives in `core.py` so a GUI can import it directly:

- `resolve_cards_for_identifier(set_identifier)`
- `add_card_to_collection(set_identifier, card_id, quantity)`
- `list_collection()`
- `remove_card_from_collection(card_id, set_code=None, quantity=1, remove_all=False)`
- `cache_low_res_card_image(card_id)` saves to `cache/images/{card_id}.jpg` (or source image extension)
- `get_cardmarket_price_by_card_id(card_id, set_code=None)` from `pricing.py`
