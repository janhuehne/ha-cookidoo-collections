"""Config flow for Cookidoo Collections."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from aiohttp import CookieJar
from cookidoo_api import (
    Cookidoo,
    CookidooAuthException,
    CookidooConfig,
    CookidooLocalizationConfig,
    CookidooRequestException,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.selector import (
    CountrySelector,
    CountrySelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_COUNTRY,
    CONF_EMAIL,
    CONF_LANGUAGE,
    CONF_PASSWORD,
    DEFAULT_COUNTRY,
    DEFAULT_LANGUAGE,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): TextSelector(
            TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="email")
        ),
        vol.Required(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(
                type=TextSelectorType.PASSWORD, autocomplete="current-password"
            )
        ),
        vol.Required(CONF_COUNTRY, default=DEFAULT_COUNTRY): CountrySelector(
            CountrySelectorConfig(
                countries=[
                    "DE",
                    "AT",
                    "CH",
                    "NL",
                    "BE",
                    "FR",
                    "IT",
                    "ES",
                    "PT",
                    "PL",
                    "GB",
                    "IE",
                    "US",
                ]
            )
        ),
        vol.Required(CONF_LANGUAGE, default=DEFAULT_LANGUAGE): TextSelector(
            TextSelectorConfig(type=TextSelectorType.TEXT)
        ),
    }
)


class CookidooCollectionsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Cookidoo Collections."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect credentials and verify login."""
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_EMAIL].lower())
            self._abort_if_unique_id_configured()

            session = async_create_clientsession(
                self.hass, cookie_jar=CookieJar(unsafe=True)
            )
            client = Cookidoo(
                session,
                cfg=CookidooConfig(
                    email=user_input[CONF_EMAIL],
                    password=user_input[CONF_PASSWORD],
                    localization=CookidooLocalizationConfig(
                        country_code=user_input[CONF_COUNTRY].lower(),
                        language=user_input[CONF_LANGUAGE],
                    ),
                ),
            )
            try:
                await client.login()
                await client.get_custom_collections()
            except CookidooAuthException:
                errors["base"] = "invalid_auth"
            except CookidooRequestException:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected Cookidoo Collections setup error")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=f"Cookidoo Collections ({user_input[CONF_EMAIL]})",
                    data={
                        CONF_EMAIL: user_input[CONF_EMAIL],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_COUNTRY: user_input[CONF_COUNTRY],
                        CONF_LANGUAGE: user_input[CONF_LANGUAGE],
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
