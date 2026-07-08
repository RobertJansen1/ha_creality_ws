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
    _attr_translation_key = "light"
    _attr_icon = "mdi:lightbulb"
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_color_mode = ColorMode.BRIGHTNESS

    # Native light entity should be enabled by default
    _attr_entity_registry_enabled_default = True

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, unique_id="light")
        # This firmware reports lightSw only as 0/1 (on/off), not the dim level,
        # so remember the last set brightness to report it back to HA.
        self._brightness: int | None = None

    def _is_on(self) -> bool:
        """Return whether the LED is on, based on the lightSw switch (0/1)."""
        val = self.coordinator.data.get("lightSw")
        if val is None:
            return False
        try:
            return float(val) > 0
        except (TypeError, ValueError):
            return False

    @property
    def is_on(self) -> bool | None:
        if self._should_zero():
            return False
        return self._is_on()

    @property
    def brightness(self) -> int | None:
        if self._should_zero() or not self._is_on():
            return None
        # This firmware never reports the dim level, so report the remembered
        # value (or full brightness if we never set one).
        return self._brightness if self._brightness is not None else 255

    async def async_turn_on(self, **kwargs):
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        if brightness is None:
            # Plain on: the lightSw switch turns the LED to full brightness.
            await self.coordinator.client.send_set_retry(lightSw=1)
            self._brightness = 255
            self.async_write_ha_state()
            return

        b = max(0, min(255, int(brightness)))
        if b <= 0:
            await self.async_turn_off()
            return

        # SET_PIN (Klipper) sets the real PWM level but does NOT update the
        # Creality lightSw state. Send lightSw=1 first so on/off telemetry stays
        # in sync, then apply the dim level. Telemetry never reports the level,
        # so remember it to report brightness back to HA.
        await self.coordinator.client.send_set_retry(lightSw=1)
        value = round(b / 255, 2)
        await self.coordinator.client.send_set_retry(gcodeCmd=f"SET_PIN PIN=LED VALUE={value}")
        self._brightness = b
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        await self.coordinator.client.send_set_retry(lightSw=0)
