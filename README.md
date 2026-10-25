# Cookidoo Collections for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub release](https://img.shields.io/github/release/janhuehne/ha-cookidoo-collections.svg)](https://github.com/janhuehne/ha-cookidoo-collections/releases)
[![Validate](https://github.com/janhuehne/ha-cookidoo-collections/actions/workflows/validate.yml/badge.svg)](https://github.com/janhuehne/ha-cookidoo-collections/actions/workflows/validate.yml)

Unofficial Home Assistant integration that exposes **Cookidoo custom collections** (favorites folders) and the current week of planned meals as a sensor — with write services for week plan and folder management.

> Not affiliated with Vorwerk / Cookidoo. Uses the community [`cookidoo-api`](https://github.com/miaucl/cookidoo-api) library.
> For personal use only — respect Cookidoo ToS and recipe copyright.

## Why this exists

The official Home Assistant **Cookidoo** integration already provides:

- meal-plan calendar
- shopping list todos
- subscription sensors

It does **not** expose favorites / custom collections. This bridge fills that gap so you can build a joined favorites + week UI (for example with [ha-foodwithlove](https://github.com/janhuehne/ha-foodwithlove) Lovelace cards).

## Features

| Feature | Description |
|---|---|
| Favorites sensor | `sensor.cookidoo_collections_favoriten` — folders + recipes (FWL-shaped attributes) |
| Week meals | `week_meals` attribute on the same sensor (dates, titles, images, app URLs) |
| Add / remove week plan | Services `add_weekplan_meal` / `remove_weekplan_meal` |
| Folders | `create_favorite_folder`, `delete_favorite_folder` (empty only), `move_favorite` |

## Requirements

- Home Assistant **2025.1+** (Cookidoo / cookidoo-api era)
- A Cookidoo account
- Optional: core **Cookidoo** integration for calendar + shopping list
- Optional: [ha-foodwithlove](https://github.com/janhuehne/ha-foodwithlove) **≥ 0.5.8** for joined Lovelace cards

## Install (HACS)

### Custom repository

1. HACS → **Integrations** → ⋮ → **Custom repositories**
2. URL: `https://github.com/janhuehne/ha-cookidoo-collections` — category **Integration**
3. Download **Cookidoo Collections**, restart Home Assistant
4. Settings → Devices & services → **Add integration** → **Cookidoo Collections**

### Manual

Copy `custom_components/cookidoo_collections` into your HA `config/custom_components/` folder, restart, then add the integration.

## Setup

1. Enter Cookidoo email + password
2. Country (e.g. `DE`) and language (e.g. `de-DE`)

Uses a **separate** login session from the core Cookidoo integration (same credentials are fine).

## Joined Lovelace (with food with love)

```yaml
type: custom:fwl-week-card
entity: sensor.food_with_love_wochenuberblick
cookidoo_entity: sensor.cookidoo_collections_favoriten

type: custom:fwl-favorites-card
entity: sensor.food_with_love_favoriten
cookidoo_entity: sensor.cookidoo_collections_favoriten
```

## Services

| Service | Fields |
|---|---|
| `cookidoo_collections.add_weekplan_meal` | `date`, `recipe_id` |
| `cookidoo_collections.remove_weekplan_meal` | `date`, `recipe_id` |
| `cookidoo_collections.create_favorite_folder` | `name` |
| `cookidoo_collections.delete_favorite_folder` | `folder_id` |
| `cookidoo_collections.move_favorite` | `recipe_id`, optional `folder_id` |

## License

MIT — see [LICENSE](LICENSE).

Not affiliated with Vorwerk / Cookidoo.
