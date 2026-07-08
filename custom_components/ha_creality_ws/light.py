from __future__ import annotations

from homeassistant.components.light import (  # type: ignore[import]
    ATTR_BRIGHTNESS,
    ColorMode,
    LightEntity,
)

from .const import DOMAIN
from .entity import KEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coord = hass.data[DOMAIN][entry.entry_id]

    # Only expose if model supports light or if live data shows the field
    has_light = entry.data.get("_cached_has_light", True)
    if not has_light and "lightSw" in (coord.data or {}):
        has_light = True

    if not has_light:
        async_add_entities([])
        return

    async_add_entities([_KLight(coord)])


class _KLight(KEntity, LightEntity):
    _attr_name = "Light"
    _attr_icon = "mdi:lightbulb"
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_color_mode = ColorMode.BRIGHTNESS

    # Native light entity should be enabled by default
    _attr_entity_registry_enabled_default = True

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, self._attr_name, "light")
        # Telemetry only reports lightSw (0/1), not a level, so brightness is optimistic.
        self._optimistic_brightness: int | None = None

    @property
    def is_on(self) -> bool | None:
        if self._should_zero():
            return False
        val = self.coordinator.data.get("lightSw")
        return bool(val) if val is not None else False

    @property
    def brightness(self) -> int | None:
        if self._should_zero() or not self.is_on:
            return None
        return self._optimistic_brightness if self._optimistic_brightness is not None else 255

    async def async_turn_on(self, **kwargs):
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        if brightness is None:
            # Plain on: keep it simple and compatible across models.
            await self.coordinator.client.send_set_retry(lightSw=1)
        else:
            # Dim via Klipper: SET_PIN PIN=LED VALUE=<0..1>.
            value = round(max(0, min(255, int(brightness))) / 255, 2)
            await self.coordinator.client.send_set_retry(gcodeCmd=f"SET_PIN PIN=LED VALUE={value}")
            self._optimistic_brightness = int(brightness)
        # Optimistic state update; real telemetry will reconcile on next frame.
        self.coordinator.data["lightSw"] = 1
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        await self.coordinator.client.send_set_retry(lightSw=0)
        self.coordinator.data["lightSw"] = 0
        self.async_write_ha_state()
