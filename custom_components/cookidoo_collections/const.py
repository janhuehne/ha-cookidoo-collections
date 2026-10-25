"""Constants for Cookidoo Collections (favorites bridge)."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "cookidoo_collections"

CONF_EMAIL: Final = "email"
CONF_PASSWORD: Final = "password"
CONF_COUNTRY: Final = "country"
CONF_LANGUAGE: Final = "language"

DEFAULT_COUNTRY: Final = "DE"
DEFAULT_LANGUAGE: Final = "de-DE"
DEFAULT_SCAN_INTERVAL: Final = timedelta(minutes=30)

ATTR_FAVORITE_COUNT: Final = "favorite_count"
ATTR_FAVORITE_FOLDERS: Final = "favorite_folders"
ATTR_SOURCE: Final = "source"

SOURCE_COOKIDOO: Final = "cookidoo"
