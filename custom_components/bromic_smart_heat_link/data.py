"""Custom types for integration_blueprint."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.loader import Integration

    from .api import BromicSmartHeatLinkApiClient
    from .coordinator import BromicSmartHeatLinkDataUpdateCoordinator


type BromicSmartHeatLinkConfigEntry = ConfigEntry[BromicSmartHeatLinkData]


@dataclass
class BromicSmartHeatLinkData:
    """Data for the BromicSmartHeatLink integration."""

    client: BromicSmartHeatLinkApiClient
    coordinator: BromicSmartHeatLinkDataUpdateCoordinator
    integration: Integration
