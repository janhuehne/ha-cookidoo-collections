"""Sensors for Cookidoo Collections."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import CookidooCollectionsConfigEntry
from .const import (
    ATTR_FAVORITE_COUNT,
    ATTR_FAVORITE_FOLDERS,
    ATTR_SOURCE,
    DOMAIN,
    SOURCE_COOKIDOO,
)
from .coordinator import CookidooCollectionsCoordinator

SENSOR_FAVORITES = SensorEntityDescription(
    key="favorites",
    name="Favoriten",
    icon="mdi:heart-multiple",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CookidooCollectionsConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors from a config entry."""
    _ = hass
    coordinator = entry.runtime_data
    async_add_entities([CookidooCollectionsFavoritesSensor(coordinator, entry.entry_id)])


class CookidooCollectionsFavoritesSensor(
    CoordinatorEntity[CookidooCollectionsCoordinator], SensorEntity
):
    """Favorites-shaped sensor for custom Cookidoo collections."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: CookidooCollectionsCoordinator, entry_id: str
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = SENSOR_FAVORITES
        self._attr_unique_id = f"{entry_id}_favorites"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": "Cookidoo Collections",
            "manufacturer": "Vorwerk (unofficial bridge)",
            "model": "Custom collections",
        }
        self._update_from_coordinator()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_from_coordinator()
        self.async_write_ha_state()

    def _update_from_coordinator(self) -> None:
        data = self.coordinator.data or {}
        self._attr_native_value = data.get("favorite_count", 0)
        self._attr_extra_state_attributes = {
            ATTR_FAVORITE_COUNT: data.get("favorite_count", 0),
            ATTR_FAVORITE_FOLDERS: data.get("favorite_folders") or [],
            "week_meals": data.get("week_meals") or [],
            ATTR_SOURCE: SOURCE_COOKIDOO,
        }
