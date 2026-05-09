"""
Support for water heaters connected to Bosch thermostat.

For more details about this platform, please refer to the documentation at...
"""
from __future__ import annotations
from bosch_thermostat_client.const import GATEWAY, SELECT
from homeassistant.components.select import SelectEntity
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .bosch_entity import BoschEntity
from .const import (
    CIRCUITS,
    DOMAIN,
    GATEWAY,
    SIGNAL_BOSCH,
    SIGNAL_SELECT,
    UUID,
)


def _is_select_bosch_object(bosch_object) -> bool:
    # Check if object has options (preferred way)
    if hasattr(bosch_object, "options") and bool(getattr(bosch_object, "options", [])):
        return getattr(bosch_object, "writeable", 0) and hasattr(bosch_object, "set_value")

    # Fallback: check for allowedValues in raw properties
    try:
        props = bosch_object.get_property(bosch_object.attr_id) if hasattr(bosch_object, 'get_property') else {}
        if isinstance(props, dict) and 'allowedValues' in props and props.get('writeable', 0):
            return bool(props['allowedValues'])
    except Exception:
        pass

    return False


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the Bosch Select from a config entry."""
    uuid = config_entry.data[UUID]
    data = hass.data[DOMAIN][uuid]
    enabled = config_entry.data.get(SELECT, [])
    data[SELECT] = []
    select_ids = set()
    candidates: list[tuple[str, object]] = []

    gateway = data[GATEWAY]
    selects = getattr(gateway.switches, "selects", [])
    for select in selects:
        candidates.append(("Select", select))
        select_ids.add(select.attr_id)

    for switch in getattr(gateway, "regular_switches", []):
        if _is_select_bosch_object(switch) and switch.attr_id not in select_ids:
            candidates.append(("Select", switch))
            select_ids.add(switch.attr_id)

    for circ_type in CIRCUITS:
        circuits = gateway.get_circuits(circ_type)
        for circuit in circuits:
            for switch in getattr(circuit, "regular_switches", []):
                if _is_select_bosch_object(switch) and switch.attr_id not in select_ids:
                    candidates.append((f"Select{circuit.name}", switch))
                    select_ids.add(switch.attr_id)

    for domain_name, select in candidates:
        data[SELECT].append(
            BoschSelect(
                hass=hass,
                uuid=uuid,
                bosch_object=select,
                gateway=data[GATEWAY],
                name=select.name,
                attr_uri=select.attr_id,
                domain_name=domain_name,
                is_enabled=select.attr_id in enabled,
            )
        )
    async_add_entities(data[SELECT])
    async_dispatcher_send(hass, SIGNAL_BOSCH)
    return True


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the Bosch Thermostat Platform."""
    pass


class BoschSelect(BoschEntity, SelectEntity):
    """Representation of a Bosch switch."""

    signal = SIGNAL_SELECT

    def __init__(
        self,
        hass,
        uuid,
        bosch_object,
        gateway,
        name,
        attr_uri,
        domain_name,
        is_enabled=False,
    ):
        """Set up device and add update callback to get data from websocket."""
        super().__init__(
            hass=hass, uuid=uuid, bosch_object=bosch_object, gateway=gateway
        )
        self._domain_name = domain_name
        self._name = name
        self._attr_uri = attr_uri
        self._state = bosch_object.state
        self._update_init = True
        self._attr_unique_id = f"{self._domain_name}{self._name}{self._uuid}"
        self._attrs = {}
        self._attr_entity_registry_enabled_default = is_enabled

    @property
    def device_name(self):
        """Return device name."""
        return "Bosch selects"

    @property
    def current_option(self) -> str:
        """Return current selected option."""
        return self._state

    @property
    def options(self) -> list[str]:
        """Options list."""
        # Try preferred way first
        if hasattr(self._bosch_object, "options") and self._bosch_object.options:
            return self._bosch_object.options

        # Fallback: get from raw properties
        try:
            props = self._bosch_object.get_property(self._attr_uri)
            if isinstance(props, dict) and 'allowedValues' in props:
                return props['allowedValues']
        except Exception:
            pass

        return []

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        await self._bosch_object.set_value(value=option)

    async def async_update(self) -> None:
        """Update entity state."""
        if self._state != self._bosch_object.state:
            self._state = self._bosch_object.state
            self.schedule_update_ha_state()

    @property
    def should_poll(self):
        """Don't poll."""
        return False
