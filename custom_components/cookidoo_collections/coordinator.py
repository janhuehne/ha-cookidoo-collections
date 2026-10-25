"""DataUpdateCoordinator for Cookidoo custom collections."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from typing import Any

from aiohttp import CookieJar
from cookidoo_api import (
    Cookidoo,
    CookidooAuthException,
    CookidooConfig,
    CookidooLocalizationConfig,
    CookidooRequestException,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_COUNTRY,
    CONF_EMAIL,
    CONF_LANGUAGE,
    CONF_PASSWORD,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    SOURCE_COOKIDOO,
)

_LOGGER = logging.getLogger(__name__)

# Cap parallel detail fetches so we don't hammer Cookidoo on each poll.
_THUMB_CONCURRENCY = 6


def _cookidoo_recipe_url(language: str, recipe_id: str, country: str) -> str:
    """Build a web deep link for a Cookidoo recipe."""
    tld = {
        "de": "de",
        "at": "at",
        "ch": "ch",
        "gb": "co.uk",
        "ie": "co.uk",
        "us": "com",
    }.get(country.lower(), "de")
    return f"https://cookidoo.{tld}/recipes/recipe/{language}/{recipe_id}"


def _prep_minutes(total_time: Any) -> int | None:
    if total_time is None or total_time == "":
        return None
    try:
        seconds = float(total_time)
    except (TypeError, ValueError):
        return None
    return int(seconds) // 60


def _normalize_rating(value: Any) -> float | int | None:
    """Round to one decimal; drop empty/zero ratings."""
    if value in (None, "", 0, "0"):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    rounded = round(number, 1)
    return int(rounded) if rounded == int(rounded) else rounded


def _recipe_card(
    *,
    recipe_id: str,
    title: str,
    preparation_time: int | None,
    image_url: str | None,
    app_url: str,
    folder_id: str | None = None,
    rating: float | int | None = None,
    rating_count: int | None = None,
) -> dict[str, Any]:
    card = {
        "recipe_id": recipe_id,
        "title": title,
        "preparation_time": preparation_time,
        "image_url": image_url,
        "app_url": app_url,
        "viewer_url": None,
        "source": SOURCE_COOKIDOO,
        "rating": rating,
        "rating_count": rating_count,
    }
    if folder_id:
        card["folder_id"] = folder_id
    return card


class CookidooCollectionsCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch custom collections (+ week) and normalize to FWL-like shapes."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
            config_entry=entry,
        )
        self.entry = entry
        # Cross-domain cookies required by cookidoo-api OAuth/login flow.
        self._session = async_create_clientsession(
            hass, cookie_jar=CookieJar(unsafe=True)
        )
        country = entry.data[CONF_COUNTRY]
        language = entry.data[CONF_LANGUAGE]
        self._country = country
        self._language = language
        self.client = Cookidoo(
            self._session,
            cfg=CookidooConfig(
                email=entry.data[CONF_EMAIL],
                password=entry.data[CONF_PASSWORD],
                localization=CookidooLocalizationConfig(
                    country_code=country.lower(),
                    language=language,
                ),
            ),
        )
        self._logged_in = False
        # recipe_id -> {image_url, app_url, rating, rating_count}
        self._detail_cache: dict[str, dict[str, Any]] = {}

    async def _async_ensure_login(self) -> None:
        if self._logged_in:
            return
        await self.client.login()
        self._logged_in = True

    async def _async_fetch_detail(self, recipe_id: str) -> dict[str, Any]:
        cached = self._detail_cache.get(recipe_id)
        if cached is not None and cached.get("_detail_loaded"):
            return cached
        prev = cached or {}
        try:
            details = await self.client.get_recipe_details(recipe_id)
        except Exception as err:  # noqa: BLE001 — keep list usable if one fails
            _LOGGER.debug("Cookidoo detail fetch failed for %s: %s", recipe_id, err)
            info: dict[str, Any] = {
                "image_url": prev.get("image_url"),
                "app_url": prev.get("app_url")
                or _cookidoo_recipe_url(self._language, recipe_id, self._country),
                "rating": prev.get("rating"),
                "rating_count": prev.get("rating_count"),
                "_detail_loaded": True,
            }
            self._detail_cache[recipe_id] = info
            return info
        thumb = getattr(details, "thumbnail", None) or getattr(details, "image", None)
        url = getattr(details, "url", None) or _cookidoo_recipe_url(
            self._language, recipe_id, self._country
        )
        info = {
            "image_url": thumb,
            "app_url": url,
            "rating": prev.get("rating"),
            "rating_count": prev.get("rating_count"),
            "_detail_loaded": True,
        }
        self._detail_cache[recipe_id] = info
        return info

    async def _async_enrich_images(self, recipe_ids: list[str]) -> None:
        missing = [
            rid
            for rid in recipe_ids
            if rid not in self._detail_cache
            or not self._detail_cache[rid].get("_detail_loaded")
        ]
        if not missing:
            return
        sem = asyncio.Semaphore(_THUMB_CONCURRENCY)

        async def _one(rid: str) -> None:
            async with sem:
                await self._async_fetch_detail(rid)

        await asyncio.gather(*(_one(rid) for rid in missing))

    async def _async_enrich_ratings(self, recipe_ids: list[str]) -> None:
        """Fill rating/rating_count via Cookidoo search ``ids=`` (batched)."""
        needed = [
            rid
            for rid in recipe_ids
            if rid
            and (
                rid not in self._detail_cache
                or "rating" not in self._detail_cache[rid]
            )
        ]
        if not needed:
            return
        try:
            await self._async_ensure_login()
            await self.client._ensure_endpoints()  # noqa: SLF001 — search path only
            locale = (self._language or "de").split("-")[0]
            url = self.client.api_endpoint / self.client._path(  # noqa: SLF001
                "search:home"
            ).format(locale=locale)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Cookidoo ratings setup failed: %s", err)
            return

        # Chunk defensively; a single request handled 181 ids in testing.
        chunk_size = 200
        for offset in range(0, len(needed), chunk_size):
            chunk = needed[offset : offset + chunk_size]
            try:
                raw = await self.client._request_json(  # noqa: SLF001
                    "get",
                    url,
                    "search recipes for ratings",
                    params={"ids": ",".join(chunk), "pageSize": str(len(chunk))},
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Cookidoo ratings fetch failed: %s", err)
                for rid in chunk:
                    self._detail_cache.setdefault(rid, {})
                    self._detail_cache[rid].setdefault("rating", None)
                    self._detail_cache[rid].setdefault("rating_count", None)
                continue
            rows = (raw or {}).get("data") if isinstance(raw, dict) else None
            by_id: dict[str, dict[str, Any]] = {}
            if isinstance(rows, list):
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    rid = str(row.get("id") or "")
                    if not rid:
                        continue
                    count_raw = row.get("numberOfRatings")
                    count: int | None = None
                    if count_raw not in (None, ""):
                        try:
                            parsed = int(float(count_raw))
                            count = parsed if parsed > 0 else None
                        except (TypeError, ValueError):
                            count = None
                    by_id[rid] = {
                        "rating": _normalize_rating(row.get("rating")),
                        "rating_count": count,
                    }
            for rid in chunk:
                info = self._detail_cache.setdefault(rid, {})
                got = by_id.get(rid) or {"rating": None, "rating_count": None}
                info["rating"] = got["rating"]
                info["rating_count"] = got["rating_count"]

    def _folders_from_collections(self, collections: list[Any]) -> list[dict[str, Any]]:
        folders: list[dict[str, Any]] = []
        for collection in collections:
            folder_id = getattr(collection, "id", None)
            recipes: list[dict[str, Any]] = []
            for chapter in getattr(collection, "chapters", None) or []:
                for recipe in getattr(chapter, "recipes", None) or []:
                    rid = getattr(recipe, "id", None)
                    if not rid:
                        continue
                    detail = self._detail_cache.get(rid) or {}
                    recipes.append(
                        _recipe_card(
                            recipe_id=rid,
                            title=getattr(recipe, "name", None) or rid,
                            preparation_time=_prep_minutes(
                                getattr(recipe, "total_time", None)
                            ),
                            image_url=detail.get("image_url"),
                            app_url=detail.get("app_url")
                            or _cookidoo_recipe_url(
                                self._language, rid, self._country
                            ),
                            folder_id=folder_id,
                            rating=detail.get("rating"),
                            rating_count=detail.get("rating_count"),
                        )
                    )
            recipes.sort(key=lambda r: (r.get("title") or "").lower())
            folders.append(
                {
                    "id": folder_id,
                    "name": getattr(collection, "name", None) or "Collection",
                    "count": len(recipes),
                    "recipes": recipes,
                    "source": SOURCE_COOKIDOO,
                }
            )
        folders.sort(key=lambda f: (f.get("name") or "").lower())
        return folders

    async def async_add_weekplan_meal(self, day: date, recipe_id: str) -> None:
        """Add a catalog recipe to the Cookidoo calendar day."""
        await self._async_ensure_login()
        await self.client.add_recipes_to_calendar(day, [recipe_id])

    async def async_remove_weekplan_meal(self, day: date, recipe_id: str) -> None:
        """Remove a catalog recipe from the Cookidoo calendar day."""
        await self._async_ensure_login()
        await self.client.remove_recipe_from_calendar(day, recipe_id)

    async def async_create_folder(self, name: str) -> str:
        """Create an empty custom collection; return its id."""
        await self._async_ensure_login()
        collection = await self.client.add_custom_collection(name)
        return str(getattr(collection, "id", "") or "")

    async def async_delete_folder(self, folder_id: str) -> None:
        """Delete a custom collection (API may require it empty)."""
        await self._async_ensure_login()
        # Refuse locally if we still see recipes in cached data.
        for folder in (self.data or {}).get("favorite_folders") or []:
            if folder.get("id") == folder_id and int(folder.get("count") or 0) > 0:
                raise ValueError("Folder is not empty")
        await self.client.remove_custom_collection(folder_id)

    async def async_move_favorite(
        self, recipe_id: str, *, to_folder_id: str | None
    ) -> None:
        """Move recipe into a collection, or out of all collections when None."""
        await self._async_ensure_login()
        folders = (self.data or {}).get("favorite_folders") or []
        current_ids: list[str] = []
        for folder in folders:
            fid = folder.get("id")
            if not fid:
                continue
            for recipe in folder.get("recipes") or []:
                if recipe.get("recipe_id") == recipe_id:
                    current_ids.append(str(fid))
                    break
        for fid in current_ids:
            if to_folder_id and fid == to_folder_id:
                continue
            await self.client.remove_recipe_from_custom_collection(fid, recipe_id)
        if to_folder_id and to_folder_id not in current_ids:
            await self.client.add_recipes_to_custom_collection(
                to_folder_id, [recipe_id]
            )
        elif to_folder_id and to_folder_id in current_ids and len(current_ids) > 1:
            # Already in target but also elsewhere — removals above cleaned others.
            pass
        elif to_folder_id and to_folder_id in current_ids:
            pass

    def _week_meals_from_calendar(self, calendar_days: list[Any]) -> list[dict[str, Any]]:
        meals: list[dict[str, Any]] = []
        for day in calendar_days:
            day_id = getattr(day, "id", None)
            for recipe in getattr(day, "recipes", None) or []:
                rid = getattr(recipe, "id", None)
                if not rid:
                    continue
                thumb = getattr(recipe, "thumbnail", None) or getattr(
                    recipe, "image", None
                )
                url = getattr(recipe, "url", None) or _cookidoo_recipe_url(
                    self._language, rid, self._country
                )
                detail = self._detail_cache.get(rid) or {}
                if thumb:
                    cached = self._detail_cache.setdefault(rid, {})
                    cached.setdefault("image_url", thumb)
                    cached.setdefault("app_url", url)
                meals.append(
                    {
                        **_recipe_card(
                            recipe_id=rid,
                            title=getattr(recipe, "name", None) or rid,
                            preparation_time=_prep_minutes(
                                getattr(recipe, "total_time", None)
                            ),
                            image_url=thumb or detail.get("image_url"),
                            app_url=url,
                            rating=detail.get("rating"),
                            rating_count=detail.get("rating_count"),
                        ),
                        "date": day_id,
                    }
                )
        return meals

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            await self._async_ensure_login()
            collections = await self.client.get_custom_collections()
            today = date.today()
            # Cookidoo's my-week endpoint is empty when anchored on Sunday;
            # always query from Monday of the ISO week.
            monday = today - timedelta(days=today.weekday())
            week_a = await self.client.get_recipes_in_calendar_week(monday)
            week_b = await self.client.get_recipes_in_calendar_week(
                monday + timedelta(days=7)
            )
        except CookidooAuthException as err:
            self._logged_in = False
            raise UpdateFailed(f"Cookidoo auth failed: {err}") from err
        except CookidooRequestException as err:
            raise UpdateFailed(f"Cookidoo request failed: {err}") from err
        except Exception as err:  # noqa: BLE001 — surface unexpected API breaks
            self._logged_in = False
            raise UpdateFailed(f"Cookidoo collections update failed: {err}") from err

        recipe_ids: list[str] = []
        for collection in collections:
            for chapter in getattr(collection, "chapters", None) or []:
                for recipe in getattr(chapter, "recipes", None) or []:
                    rid = getattr(recipe, "id", None)
                    if rid:
                        recipe_ids.append(rid)

        unique_ids = list(dict.fromkeys(recipe_ids))
        # Also rate week-plan recipes when possible.
        for day in [*week_a, *week_b]:
            for recipe in getattr(day, "recipes", None) or []:
                rid = getattr(recipe, "id", None)
                if rid:
                    unique_ids.append(rid)
        unique_ids = list(dict.fromkeys(unique_ids))
        await self._async_enrich_ratings(unique_ids)
        await self._async_enrich_images(unique_ids)

        folders = self._folders_from_collections(collections)
        week_meals = self._week_meals_from_calendar([*week_a, *week_b])
        # Dedupe week meals by date+id if weeks overlap.
        seen: set[tuple[str, str]] = set()
        unique_week: list[dict[str, Any]] = []
        for meal in week_meals:
            key = (str(meal.get("date") or ""), str(meal.get("recipe_id") or ""))
            if key in seen:
                continue
            seen.add(key)
            unique_week.append(meal)

        total = sum(int(f.get("count") or 0) for f in folders)
        return {
            "favorite_count": total,
            "favorite_folders": folders,
            "week_meals": unique_week,
            "source": SOURCE_COOKIDOO,
        }
