"""Config flow for the JW Music integration."""

from __future__ import annotations

from typing import Any, override

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import NoContentError, UnknownLanguageError, async_validate_language
from .const import CONF_LANGUAGE, DEFAULT_LANGUAGE, DOMAIN, LOGGER, NAME

LANGUAGE_SCHEMA = vol.Schema({vol.Required(CONF_LANGUAGE): str})


async def _async_check_language(
    flow: ConfigFlow | OptionsFlowWithReload, code: str
) -> tuple[str | None, str | None]:
    """Validate ``code`` against jw.org. Returns (exact code, error key)."""
    session = async_get_clientsession(flow.hass)
    try:
        return await async_validate_language(session, code), None
    except UnknownLanguageError:
        return None, "invalid_language"
    except NoContentError:
        return None, "no_content"
    except (aiohttp.ClientError, TimeoutError):
        return None, "cannot_connect"
    except Exception:  # noqa: BLE001
        LOGGER.exception("JW Music: unexpected error while checking the language")
        return None, "unknown"


class JwMusicConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial setup."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> JwMusicOptionsFlow:
        """Return the options flow."""
        return JwMusicOptionsFlow()

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the jw.org language code."""
        errors: dict[str, str] = {}
        if user_input is not None:
            language, error = await _async_check_language(
                self, user_input[CONF_LANGUAGE]
            )
            if language:
                return self.async_create_entry(
                    title=NAME, data={}, options={CONF_LANGUAGE: language}
                )
            errors[CONF_LANGUAGE] = error or "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                LANGUAGE_SCHEMA, user_input or {CONF_LANGUAGE: DEFAULT_LANGUAGE}
            ),
            errors=errors,
        )


class JwMusicOptionsFlow(OptionsFlowWithReload):
    """Change the language later; the entry reloads automatically."""

    @override
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the jw.org language code."""
        errors: dict[str, str] = {}
        if user_input is not None:
            language, error = await _async_check_language(
                self, user_input[CONF_LANGUAGE]
            )
            if language:
                return self.async_create_entry(data={CONF_LANGUAGE: language})
            errors[CONF_LANGUAGE] = error or "unknown"

        current = self.config_entry.options.get(CONF_LANGUAGE, DEFAULT_LANGUAGE)
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                LANGUAGE_SCHEMA, user_input or {CONF_LANGUAGE: current}
            ),
            errors=errors,
        )
