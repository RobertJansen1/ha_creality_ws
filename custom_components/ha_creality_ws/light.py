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

    def _light_level(self) -> float | None:
        """Return the reported LED level as a float, or None if unknown.

        The printer may report ``lightSw`` as an int switch (0/1), a float PWM
        level (0..1, matching Klipper ``SET_PIN PIN=LED VALUE=<0..1>``), or a
        numeric string. Parse all of these into a float so state feedback is
        reliable instead of relying on ``bool()`` truthiness.
        """
        val = self.coordinator.data.get("lightSw")
        if val is None:
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    @property
    def is_on(self) -> bool | None:
        if self._should_zero():
            return False
        level = self._light_level()
        if level is None:
            return False
        return level > 0

    @property
    def brightness(self) -> int | None:
        if self._should_zero():
            return None
        level = self._light_level()
        if level is None or level <= 0:
            return None
        # 0..1 PWM level (incl. a plain "1" switch) -> 1..255 scale.
        if level <= 1:
            return max(1, round(level * 255))
        # Already reported on a larger scale (e.g. 0..255) or a plain flag.
        return min(255, round(level))

    async def async_turn_on(self, **kwargs):
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        if brightness is None:
            # Plain on: keep it simple and compatible across models.
            await self.coordinator.client.send_set_retry(lightSw=1)
        else:
            # Dim via Klipper: SET_PIN PIN=LED VALUE=<0..1>.
            b = max(0, min(255, int(brightness)))
            value = round(b / 255, 2)
            await self.coordinator.client.send_set_retry(gcodeCmd=f"SET_PIN PIN=LED VALUE={value}")

    async def async_turn_off(self, **kwargs):
        await self.coordinator.client.send_set_retry(lightSw=0)
