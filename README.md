# yugioh-db

Simple CLI app to search Yu-Gi-Oh cards by **set code** and track how many copies you own.

## Requirements

- Python 3.14+
- Tkinter runtime (required by FreeSimpleGUI GUI)

Install project dependencies:

```bash
uv sync
```

If Tkinter is missing on Linux:

```bash
sudo apt-get install python3-tk
```

## Usage

```bash
python CLI.py --help
```

## GUI

Launch the GUI:

```bash
python GUI.py
```

GUI sections:
- **Search tab**: enter set code/print code/card name, search cards, select a row, add quantity to stock.
- **My Stock tab**: shows card name + total quantity, total stock value, and top 5 most expensive cards; double-click a row to open details.
- **Stock details popup**: image on the left, with copy/details on the right (name, full description, types, ATK, DEF, set copies, total quantity) plus delete actions (`Remove 1 Copy`, `Remove Selected Print`, `Delete Card`).
- **Deck Builder tab**: create decks, mark them as `current`/`future`, add/remove cards by ID or name, filter deck cards by section (`all/main/extra/side`), and import/export `.ydk` files.

Find a set code (if you only know part of the set name):

```bash
python CLI.py sets "blue eyes"
```

Search cards in a set:

```bash
python CLI.py search YS15
```

Search using a full print code:

```bash
python CLI.py search RA02-EN021
```

Save a card and quantity:

```bash
python CLI.py add YS15 85639257 --qty 2

# You can also add by exact card name:
python CLI.py add YS15 "Dark Magician" --qty 1

# If a print has multiple rarities, you'll be prompted.
# You can also pass the rarity directly:
python CLI.py add RA05-EN127 12345678 --rarity SR --qty 1
```

You can also add by full print code:

```bash
python CLI.py add RA02-EN021 37818794 --qty 1
```

Show your saved collection:

```bash
python CLI.py list
```

Get Cardmarket price by card ID:

```bash
python CLI.py price 37818794 --set-code RA02-EN021

# Or by exact card name:
python CLI.py price "Red-Eyes Dark Dragoon" --set-code RA02-EN021
```

Remove one copy (or use `--all` to remove the card entirely):

```bash
python CLI.py remove 85639257 --qty 1

# You can remove by exact saved card name as well:
python CLI.py remove "Dark Magician" --qty 1
```

If a card ID has multiple set/print quantities, specify the exact one:

```bash
python CLI.py remove 37818794 --set-code RA02-EN021 --all

# Includes rarity-specific variants:
python CLI.py remove 37818794 --set-code "RA05-EN127 (SR)" --all
```

Collection data is stored locally in `cache/collection.json`, grouped by `card_id` with shared details plus:

- `total_quantity` across all printings
- `sets` map keyed by `set_code`, each with its own `quantity`

Deck data is stored locally in `cache/decks.json`, with:

- deck `name`, `status` (`current` or `future`), and `notes`
- per-deck card list with `card_id`, `name`, `type`, `section`, and `quantity`
- computed `total_cards` and `unique_cards`

Create/list/update decks from the CLI:

```bash
python CLI.py deck-create "Blue-Eyes Current" --status current
python CLI.py deck-create "Branded Next" --status future --notes "Need 2x Cartesia"
python CLI.py deck-list
python CLI.py deck-show "Blue-Eyes Current"
python CLI.py deck-add "Blue-Eyes Current" "Blue-Eyes White Dragon" --qty 3
python CLI.py deck-add "Blue-Eyes Current" "Blue-Eyes Tyrant Dragon" --section extra --qty 1
python CLI.py deck-remove "Blue-Eyes Current" "Blue-Eyes White Dragon" --qty 1
python CLI.py deck-remove "Blue-Eyes Current" "Blue-Eyes White Dragon" --section side --all
python CLI.py deck-status "Branded Next" current
python CLI.py deck-import-ydk "Sky Striker" "/path/to/sky_striker.ydk" --status future --overwrite
python CLI.py deck-export-ydk "Blue-Eyes Current" "/path/to/blue_eyes_current.ydk"
python CLI.py deck-delete "Branded Next"
```

## Reuse in a GUI

Core app logic now lives in `core.py` so a GUI can import it directly:

- `resolve_cards_for_identifier(set_identifier)`
- `add_card_to_collection(set_identifier, card_id, quantity)`
- `list_collection()`
- `remove_card_from_collection(card_id, set_code=None, quantity=1, remove_all=False)`
- `cache_low_res_card_image(card_id)` saves to `cache/images/{card_id}.jpg` (or source image extension)
- `get_cardmarket_price_by_card_id(card_id, set_code=None)` from `pricing.py`
- deck helpers: `create_deck`, `list_decks`, `get_deck`, `add_card_to_deck`, `remove_card_from_deck`, `set_deck_status`, `delete_deck`, `import_deck_from_ydk`, `export_deck_to_ydk`
