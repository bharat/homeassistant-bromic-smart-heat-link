"""Test fixtures for Bromic Smart Heat Link."""

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Make HA discover the integration under custom_components/."""
    return
