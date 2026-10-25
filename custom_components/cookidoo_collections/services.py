"""Home Assistant services for Cookidoo Collections."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .coordinator import CookidooCollectionsCoordinator

_LOGGER = logging.getLogger(__name__)

SERVICE_REMOVE_WEEKPLAN_MEAL = "remove_weekplan_meal"
SERVICE_ADD_WEEKPLAN_MEAL = "add_weekplan_meal"
SERVICE_CREATE_FAVORITE_FOLDER = "create_favorite_folder"
SERVICE_DELETE_FAVORITE_FOLDER = "delete_favorite_folder"
SERVICE_MOVE_FAVORITE = "move_favorite"
_DATA_SERVICES = f"{DOMAIN}_services"

SERVICE_WEEKPLAN_SCHEMA = vol.Schema(
    {
        vol.Required("date"): cv.date,
        vol.Required("recipe_id"): cv.string,
    }
)
SERVICE_CREATE_FOLDER_SCHEMA = vol.Schema({vol.Required("name"): cv.string})
SERVICE_DELETE_FOLDER_SCHEMA = vol.Schema({vol.Required("folder_id"): cv.string})
SERVICE_MOVE_FAVORITE_SCHEMA = vol.Schema(
    {
        vol.Required("recipe_id"): cv.string,
        vol.Optional("folder_id"): vol.Any(None, cv.string),
    }
)


def _primary_coordinator(hass: HomeAssistant) -> CookidooCollectionsCoordinator:
    for entry in hass.config_entries.async_entries(DOMAIN):
        coordinator = getattr(entry, "runtime_data", None)
        if isinstance(coordinator, CookidooCollectionsCoordinator):
            return coordinator
    raise HomeAssistantError("Cookidoo Collections is not configured")


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register domain services once."""
    if hass.data.get(_DATA_SERVICES):
        return
    hass.data[_DATA_SERVICES] = True

    async def _handle_add(call: ServiceCall) -> None:
        await _async_set_weekplan(hass, call.data, enabled=True)

    async def _handle_remove(call: ServiceCall) -> None:
        await _async_set_weekplan(hass, call.data, enabled=False)

    async def _handle_create_folder(call: ServiceCall) -> None:
        coordinator = _primary_coordinator(hass)
        name = str(call.data["name"]).strip()
        if not name:
            raise HomeAssistantError("Folder name is required")
        try:
            await coordinator.async_create_folder(name)
        except Exception as err:  # noqa: BLE001
            raise HomeAssistantError(f"Could not create Cookidoo folder: {err}") from err
        await coordinator.async_request_refresh()

    async def _handle_delete_folder(call: ServiceCall) -> None:
        coordinator = _primary_coordinator(hass)
        folder_id = str(call.data["folder_id"])
        try:
            await coordinator.async_delete_folder(folder_id)
        except Exception as err:  # noqa: BLE001
            raise HomeAssistantError(f"Could not delete Cookidoo folder: {err}") from err
        await coordinator.async_request_refresh()

    async def _handle_move(call: ServiceCall) -> None:
        coordinator = _primary_coordinator(hass)
        recipe_id = str(call.data["recipe_id"])
        folder_id = call.data.get("folder_id")
        try:
            await coordinator.async_move_favorite(
                recipe_id, to_folder_id=folder_id or None
            )
        except Exception as err:  # noqa: BLE001
            raise HomeAssistantError(f"Could not move Cookidoo favorite: {err}") from err
        await coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN, SERVICE_ADD_WEEKPLAN_MEAL, _handle_add, schema=SERVICE_WEEKPLAN_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REMOVE_WEEKPLAN_MEAL,
        _handle_remove,
        schema=SERVICE_WEEKPLAN_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CREATE_FAVORITE_FOLDER,
        _handle_create_folder,
        schema=SERVICE_CREATE_FOLDER_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DELETE_FAVORITE_FOLDER,
        _handle_delete_folder,
        schema=SERVICE_DELETE_FOLDER_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_MOVE_FAVORITE,
        _handle_move,
        schema=SERVICE_MOVE_FAVORITE_SCHEMA,
    )


@callback
def async_unload_services(hass: HomeAssistant) -> None:
    """Unregister services when the last config entry unloads."""
    if not hass.data.pop(_DATA_SERVICES, None):
        return
    for name in (
        SERVICE_REMOVE_WEEKPLAN_MEAL,
        SERVICE_ADD_WEEKPLAN_MEAL,
        SERVICE_CREATE_FAVORITE_FOLDER,
        SERVICE_DELETE_FAVORITE_FOLDER,
        SERVICE_MOVE_FAVORITE,
    ):
        hass.services.async_remove(DOMAIN, name)


async def _async_set_weekplan(
    hass: HomeAssistant, data: dict[str, Any], *, enabled: bool
) -> None:
    coordinator = _primary_coordinator(hass)
    day: date = data["date"]
    recipe_id = str(data["recipe_id"])
    try:
        if enabled:
            await coordinator.async_add_weekplan_meal(day, recipe_id)
        else:
            await coordinator.async_remove_weekplan_meal(day, recipe_id)
    except Exception as err:  # noqa: BLE001
        action = "add" if enabled else "remove"
        raise HomeAssistantError(
            f"Could not {action} Cookidoo weekplan meal: {err}"
        ) from err
    await coordinator.async_request_refresh()
